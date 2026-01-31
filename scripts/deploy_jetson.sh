#!/bin/bash
# Depth Anything V3 - Jetson Deployment Script
# Requires: JetPack 6.2+ (L4T R36.4.x) with TensorRT 10.3
#
# Usage: bash scripts/deploy_jetson.sh [--build-only|--run-only]
#
# This script:
# 1. Verifies TensorRT 10.3 is available on host
# 2. Downloads ONNX model if missing
# 3. Builds TensorRT FP16 engine using host TRT (not container)
# 4. Starts Docker container with mounted engine
#
# Performance: 35.3 FPS @ 518x518 (6.8x speedup over PyTorch)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# Paths
ONNX_DIR="models/onnx"
TRT_DIR="models/tensorrt"
ONNX_MODEL="$ONNX_DIR/da3-small-embedded.onnx"
TRT_ENGINE="$TRT_DIR/da3-small-fp16.engine"
TRTEXEC="/usr/src/tensorrt/bin/trtexec"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================"
echo "Depth Anything V3 - Jetson Deployment"
echo "========================================"
echo ""

# Parse arguments
BUILD_ONLY=false
RUN_ONLY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --build-only) BUILD_ONLY=true; shift ;;
        --run-only) RUN_ONLY=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Step 1: Verify TensorRT 10.3
echo -e "${YELLOW}[1/4] Checking TensorRT version...${NC}"
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
echo -e "${YELLOW}[2/4] Checking ONNX model...${NC}"
mkdir -p "$ONNX_DIR" "$TRT_DIR"

if [ ! -f "$ONNX_MODEL" ]; then
    echo "       Downloading from HuggingFace..."
    
    # Check for huggingface-cli
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
        echo -e "${RED}ERROR: huggingface-cli not found${NC}"
        echo "       Install with: pip install huggingface_hub"
        echo "       Or manually download ONNX model to: $ONNX_MODEL"
        exit 1
    fi
fi

ONNX_SIZE=$(du -h "$ONNX_MODEL" | cut -f1)
echo -e "${GREEN}       ONNX model ready: $ONNX_MODEL ($ONNX_SIZE)${NC}"

# Step 3: Build TensorRT engine
if [ "$RUN_ONLY" = false ]; then
    echo -e "${YELLOW}[3/4] Building TensorRT FP16 engine...${NC}"
    
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
    echo -e "${YELLOW}[3/4] Skipping engine build (--run-only)${NC}"
fi

if [ "$BUILD_ONLY" = true ]; then
    echo ""
    echo -e "${GREEN}Build complete. Run with: bash scripts/deploy_jetson.sh --run-only${NC}"
    exit 0
fi

# Step 4: Start container
echo -e "${YELLOW}[4/4] Starting Docker container...${NC}"

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
echo "Expected:   ~35 FPS"
echo ""
echo "Inside container, run:"
echo "  ros2 launch depth_anything_3_ros2 depth_inference.launch.py"
echo ""

docker compose up depth-anything-3-jetson
