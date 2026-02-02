#!/bin/bash
# Depth Anything V3 - Jetson Deployment Script
# Requires: JetPack 6.2+ (L4T R36.4.x) with TensorRT 10.3
#
# Usage: bash scripts/deploy_jetson.sh [options]
#
# Options:
#   --build-only    Build engine only, don't start container
#   --run-only      Skip engine build, just start container
#   --host-trt      Use host-container split architecture (recommended)
#                   Runs TRT inference on host, ROS2 in container
#
# Architecture (--host-trt):
#   [Container: ROS2 Node] <-- /tmp/da3_shared --> [Host: TRT Service]
#        |                                              |
#        v                                              v
#   /image_raw (sub)                           TRT 10.3 engine
#   /depth (pub)                               ~30 FPS inference
#
# Performance: 35.3 FPS @ 518x518 (6.8x speedup over PyTorch)

set -e

# Ensure ~/.local/bin is in PATH (pip installs CLI tools there)
export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# Paths
ONNX_DIR="models/onnx"
TRT_DIR="models/tensorrt"
ONNX_MODEL="$ONNX_DIR/da3-small-embedded.onnx"
TRT_ENGINE="$TRT_DIR/da3-small-fp16.engine"
TRTEXEC="/usr/src/tensorrt/bin/trtexec"
SHARED_DIR="/tmp/da3_shared"
TRT_SERVICE_PID=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo "========================================"
echo "Depth Anything V3 - Jetson Deployment"
echo "========================================"
echo ""

# Parse arguments
BUILD_ONLY=false
RUN_ONLY=false
HOST_TRT=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --build-only) BUILD_ONLY=true; shift ;;
        --run-only) RUN_ONLY=true; shift ;;
        --host-trt) HOST_TRT=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--build-only|--run-only|--host-trt]"
            echo ""
            echo "Options:"
            echo "  --build-only  Build TRT engine only"
            echo "  --run-only    Skip engine build, start container"
            echo "  --host-trt    Use host-container split (recommended)"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Cleanup function
cleanup() {
    if [ -n "$TRT_SERVICE_PID" ] && kill -0 "$TRT_SERVICE_PID" 2>/dev/null; then
        echo ""
        echo -e "${YELLOW}Stopping TRT inference service...${NC}"
        kill "$TRT_SERVICE_PID" 2>/dev/null || true
        wait "$TRT_SERVICE_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Step 1: Verify TensorRT 10.3
echo -e "${YELLOW}[1/5] Checking TensorRT version...${NC}"
if [ ! -f "$TRTEXEC" ]; then
    echo -e "${RED}ERROR: trtexec not found at $TRTEXEC${NC}"
    echo "       JetPack 6.2+ required. Current system missing TensorRT."
    exit 1
fi

TRT_VERSION=$($TRTEXEC --help 2>&1 | grep -oP 'TensorRT v\K[0-9]+' | head -1)
if [ "$TRT_VERSION" -lt 10 ]; then
    echo -e "${RED}ERROR: TensorRT $TRT_VERSION found, but 10.3+ required${NC}"
    echo "       DA3 uses DINOv2 backbone which requires TRT 10.x"
    exit 1
fi
echo -e "${GREEN}       TensorRT 10.x detected${NC}"

# Step 2: Check/Download ONNX model
echo -e "${YELLOW}[2/5] Checking ONNX model...${NC}"
mkdir -p "$ONNX_DIR" "$TRT_DIR"

if [ ! -f "$ONNX_MODEL" ]; then
    echo "       Downloading from HuggingFace..."

    # Auto-install huggingface_hub if not available
    if ! command -v huggingface-cli &> /dev/null; then
        echo "       Installing huggingface_hub..."
        pip3 install huggingface_hub 2>&1 | tail -1
    fi

    # Auto-install onnx if not available
    if ! python3 -c "import onnx" 2>/dev/null; then
        echo "       Installing onnx..."
        pip3 install onnx 2>&1 | tail -1
    fi

    # Download model
    if command -v huggingface-cli &> /dev/null; then
        huggingface-cli download onnx-community/depth-anything-v3-small \
            --local-dir "$ONNX_DIR/hf-download" \
            --include "*.onnx" "*.onnx_data"

        # Embed external weights into single file
        echo "       Embedding weights into single ONNX file..."
        python3 -c "
import onnx
model = onnx.load('$ONNX_DIR/hf-download/onnx/model.onnx')
onnx.save(model, '$ONNX_MODEL', save_as_external_data=False)
print('       Created: $ONNX_MODEL')
"
    else
        echo -e "${RED}ERROR: Failed to install huggingface_hub${NC}"
        echo "       Try manually: pip3 install huggingface_hub"
        exit 1
    fi
fi

ONNX_SIZE=$(du -h "$ONNX_MODEL" | cut -f1)
echo -e "${GREEN}       ONNX model ready: $ONNX_MODEL ($ONNX_SIZE)${NC}"

# Step 3: Build TensorRT engine
if [ "$RUN_ONLY" = false ]; then
    echo -e "${YELLOW}[3/5] Building TensorRT FP16 engine...${NC}"

    if [ -f "$TRT_ENGINE" ]; then
        ENGINE_SIZE=$(du -h "$TRT_ENGINE" | cut -f1)
        echo "       Engine exists: $TRT_ENGINE ($ENGINE_SIZE)"
        read -p "       Rebuild? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "       Skipping rebuild"
        else
            rm -f "$TRT_ENGINE"
        fi
    fi

    if [ ! -f "$TRT_ENGINE" ]; then
        echo "       This takes ~2 minutes..."
        echo ""

        $TRTEXEC \
            --onnx="$ONNX_MODEL" \
            --saveEngine="$TRT_ENGINE" \
            --fp16 \
            --memPoolSize=workspace:2048MiB \
            --optShapes=pixel_values:1x1x3x518x518 \
            2>&1 | tee /tmp/trtexec_build.log | grep -E "(Building|Serializing|SUCCESS|ERROR|Throughput)"

        if [ ! -f "$TRT_ENGINE" ]; then
            echo -e "${RED}ERROR: Engine build failed${NC}"
            echo "       Check /tmp/trtexec_build.log for details"
            exit 1
        fi

        ENGINE_SIZE=$(du -h "$TRT_ENGINE" | cut -f1)
        echo -e "${GREEN}       Engine built: $TRT_ENGINE ($ENGINE_SIZE)${NC}"
    fi
else
    echo -e "${YELLOW}[3/5] Skipping engine build (--run-only)${NC}"
fi

if [ "$BUILD_ONLY" = true ]; then
    echo ""
    echo -e "${GREEN}Build complete. Run with: bash scripts/deploy_jetson.sh --run-only${NC}"
    exit 0
fi

# Step 4: Setup shared memory directory and start host TRT service
if [ "$HOST_TRT" = true ]; then
    echo -e "${YELLOW}[4/5] Starting host TRT inference service...${NC}"

    # Create shared directory with proper permissions
    mkdir -p "$SHARED_DIR"
    chmod 777 "$SHARED_DIR"

    # Check for required Python packages
    if ! python3 -c "import tensorrt; import pycuda.driver" 2>/dev/null; then
        echo -e "${RED}ERROR: Host Python missing tensorrt or pycuda${NC}"
        echo "       Install with: pip3 install pycuda"
        echo "       TensorRT Python bindings should be available via JetPack"
        exit 1
    fi

    # Start TRT inference service in background
    echo "       Starting inference service..."
    python3 "$SCRIPT_DIR/trt_inference_service.py" \
        --engine "$TRT_ENGINE" \
        --poll-interval 0.001 \
        > /tmp/trt_service.log 2>&1 &
    TRT_SERVICE_PID=$!

    # Wait for service to initialize
    sleep 2
    if ! kill -0 "$TRT_SERVICE_PID" 2>/dev/null; then
        echo -e "${RED}ERROR: TRT service failed to start${NC}"
        echo "       Check /tmp/trt_service.log for details"
        cat /tmp/trt_service.log
        exit 1
    fi

    # Verify service is ready
    if [ -f "$SHARED_DIR/status" ]; then
        STATUS=$(cat "$SHARED_DIR/status")
        echo -e "${GREEN}       TRT service running (PID: $TRT_SERVICE_PID, status: $STATUS)${NC}"
    else
        echo -e "${YELLOW}       TRT service starting...${NC}"
    fi
else
    echo -e "${YELLOW}[4/5] Skipping host TRT service (use --host-trt to enable)${NC}"
fi

# Step 5: Start container
echo -e "${YELLOW}[5/5] Starting Docker container...${NC}"

# Build image if needed
if ! docker images | grep -q "depth_anything_3_ros2.*jetson"; then
    echo "       Building Docker image (first time only, ~20 min)..."
    docker compose build depth-anything-3-jetson
fi

echo ""
echo "========================================"
echo "Starting Depth Anything V3 container"
echo "========================================"
echo ""
echo "Engine:     $TRT_ENGINE"
echo "Resolution: 518x518 FP16"

if [ "$HOST_TRT" = true ]; then
    echo -e "Mode:       ${CYAN}Host-Container Split (TRT on host)${NC}"
    echo "Expected:   ~30-35 FPS"
    echo ""
    echo "TRT Service: PID $TRT_SERVICE_PID (log: /tmp/trt_service.log)"
    echo "Shared Dir:  $SHARED_DIR"
else
    echo "Mode:       Container-only (PyTorch fallback)"
    echo "Expected:   ~5 FPS (TRT unavailable in container)"
fi
echo ""
echo "Inside container, run:"
echo "  ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \\"
echo "    image_topic:=/camera/image_raw"
echo ""

# Export environment for docker-compose
export DA3_ENGINE_PATH="$TRT_ENGINE"
export DA3_HOST_TRT="$HOST_TRT"

docker compose up depth-anything-3-jetson
