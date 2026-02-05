#!/bin/bash
#
# Depth Anything 3 ROS2 - One-Click Demo
#
# This script handles everything needed to run the depth estimation demo:
#   1. Builds Docker image (if not already built)
#   2. Downloads ONNX model and builds TensorRT engine (first run only)
#   3. Starts TensorRT inference service on host (20-30 FPS with shared memory IPC)
#   4. Auto-detects camera (USB or CSI)
#   5. Starts ROS2 container with camera and depth nodes
#   6. Opens depth visualization window
#
# Usage:
#   ./run.sh                           # Auto-detect everything
#   ./run.sh --camera /dev/video0      # Specify camera
#   ./run.sh --no-display              # Headless mode (SSH)
#   ./run.sh --rebuild                 # Force rebuild Docker
#   ./run.sh --help                    # Show all options
#
# Requirements:
#   - Jetson with JetPack 6.x (TensorRT 10.3+)
#   - Docker with nvidia runtime
#   - USB or CSI camera (auto-detected)
#   - ~20GB disk space for Docker image
#
# First run takes ~15-20 minutes (Docker build + TRT engine).
# Subsequent runs start in ~10 seconds.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
CONTAINER_NAME="da3_demo"
IMAGE_NAME="depth_anything_3_ros2:jetson"
SHARED_DIR="/dev/shm/da3"
ONNX_DIR="models/onnx"
TRT_DIR="models/tensorrt"
ONNX_MODEL="$ONNX_DIR/da3-small-embedded.onnx"
TRT_ENGINE="$TRT_DIR/da3-small-fp16.engine"
TRTEXEC="/usr/src/tensorrt/bin/trtexec"

# Default options
CAMERA_DEVICE=""
NO_DISPLAY=false
FORCE_REBUILD=false
SHOW_HELP=false

# Process IDs for cleanup
TRT_SERVICE_PID=""
CONTAINER_PID=""

# Banner
print_banner() {
    echo ""
    echo -e "${BOLD}============================================${NC}"
    echo -e "${BOLD}   Depth Anything 3 ROS2 - Demo${NC}"
    echo -e "${BOLD}============================================${NC}"
    echo ""
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --camera)
            CAMERA_DEVICE="$2"
            shift 2
            ;;
        --no-display|--headless)
            NO_DISPLAY=true
            shift
            ;;
        --rebuild)
            FORCE_REBUILD=true
            shift
            ;;
        -h|--help)
            SHOW_HELP=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

if [ "$SHOW_HELP" = true ]; then
    print_banner
    echo "Usage: ./run.sh [options]"
    echo ""
    echo "Options:"
    echo "  --camera DEVICE     Specify camera device (e.g., /dev/video0)"
    echo "  --no-display        Run in headless mode (for SSH)"
    echo "  --rebuild           Force rebuild Docker image"
    echo "  -h, --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run.sh                           # Auto-detect camera, show display"
    echo "  ./run.sh --camera /dev/video0      # Use specific camera"
    echo "  ./run.sh --no-display              # SSH mode (no viewer window)"
    echo ""
    echo "First run: ~15-20 minutes (Docker build + TensorRT engine)"
    echo "Subsequent: ~10 seconds"
    exit 0
fi

print_banner

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"

    # Stop container
    if docker ps -q -f name="$CONTAINER_NAME" 2>/dev/null | grep -q .; then
        docker stop "$CONTAINER_NAME" 2>/dev/null || true
    fi
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

    # Stop TRT service
    if [ -n "$TRT_SERVICE_PID" ] && kill -0 "$TRT_SERVICE_PID" 2>/dev/null; then
        kill "$TRT_SERVICE_PID" 2>/dev/null || true
        wait "$TRT_SERVICE_PID" 2>/dev/null || true
    fi

    # Cleanup shared memory
    rm -rf "$SHARED_DIR"/* 2>/dev/null || true

    echo -e "${GREEN}Done.${NC}"
}
trap cleanup EXIT INT TERM

# Step 1: Pre-flight checks
echo -e "${CYAN}[1/6] Checking requirements...${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker not installed${NC}"
    echo "Install: sudo apt install docker.io nvidia-container-toolkit"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}ERROR: Cannot connect to Docker daemon${NC}"
    echo "Fix: sudo usermod -aG docker \$USER && newgrp docker"
    exit 1
fi

# Check TensorRT
USE_TRT=true
if [ ! -f "$TRTEXEC" ]; then
    echo -e "${YELLOW}WARNING: TensorRT trtexec not found${NC}"
    echo "         Will use PyTorch backend (~5 FPS instead of ~40 FPS)"
    USE_TRT=false
fi

# Check Python TensorRT bindings
if [ "$USE_TRT" = true ]; then
    if ! python3 -c "import tensorrt" 2>/dev/null; then
        echo -e "${YELLOW}TensorRT Python bindings not found, attempting install...${NC}"

        # Try pip install first (works on JetPack 6.x)
        if pip3 install --quiet tensorrt 2>/dev/null; then
            if python3 -c "import tensorrt" 2>/dev/null; then
                echo -e "       ${GREEN}TensorRT bindings installed via pip${NC}"
            else
                USE_TRT=false
            fi
        # Try apt install as fallback
        elif sudo apt-get install -y python3-tensorrt 2>/dev/null; then
            if python3 -c "import tensorrt" 2>/dev/null; then
                echo -e "       ${GREEN}TensorRT bindings installed via apt${NC}"
            else
                USE_TRT=false
            fi
        else
            USE_TRT=false
        fi

        if [ "$USE_TRT" = false ]; then
            echo -e "${YELLOW}WARNING: Could not install TensorRT Python bindings${NC}"
            echo "         Manual install: pip3 install tensorrt --break-system-packages"
            echo "         Will use PyTorch backend (~5 FPS instead of ~40 FPS)"
        fi
    fi
fi

# Check pycuda (required for TRT service)
if [ "$USE_TRT" = true ]; then
    if ! python3 -c "import pycuda.driver" 2>/dev/null; then
        echo -e "${YELLOW}pycuda not found, installing...${NC}"
        if pip3 install pycuda --break-system-packages 2>/dev/null || pip3 install pycuda 2>/dev/null; then
            echo -e "       ${GREEN}pycuda installed${NC}"
        else
            echo -e "${YELLOW}WARNING: Could not install pycuda${NC}"
            echo "         Manual install: pip3 install pycuda --break-system-packages"
            USE_TRT=false
        fi
    fi
fi

echo -e "       ${GREEN}Requirements OK${NC}"

# Step 2: Camera detection
echo -e "${CYAN}[2/6] Detecting camera...${NC}"

if [ -z "$CAMERA_DEVICE" ]; then
    # Auto-detect camera
    if [ -e "/dev/video0" ]; then
        CAMERA_DEVICE="/dev/video0"
        # Try to get camera name
        CAMERA_NAME=$(v4l2-ctl --device="$CAMERA_DEVICE" --info 2>/dev/null | grep "Card type" | cut -d: -f2 | xargs || echo "USB Camera")
        echo -e "       Found: ${GREEN}$CAMERA_NAME${NC} ($CAMERA_DEVICE)"
    else
        echo -e "${RED}ERROR: No camera found at /dev/video0${NC}"
        echo ""
        echo "Options:"
        echo "  1. Connect a USB camera"
        echo "  2. Specify camera: ./run.sh --camera /dev/video1"
        exit 1
    fi
else
    if [ ! -e "$CAMERA_DEVICE" ]; then
        echo -e "${RED}ERROR: Camera not found: $CAMERA_DEVICE${NC}"
        exit 1
    fi
    echo -e "       Using: ${GREEN}$CAMERA_DEVICE${NC}"
fi

# Step 3: Docker image
echo -e "${CYAN}[3/6] Checking Docker image...${NC}"

if [ "$FORCE_REBUILD" = true ] || ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^$IMAGE_NAME$"; then
    echo "       Building Docker image (this takes 15-20 minutes)..."
    echo ""
    docker compose build depth-anything-3-jetson 2>&1 | tail -20
    echo ""
    echo -e "       ${GREEN}Docker image built${NC}"
else
    IMAGE_SIZE=$(docker images --format '{{.Size}}' "$IMAGE_NAME" 2>/dev/null || echo "unknown")
    echo -e "       Image ready: ${GREEN}$IMAGE_NAME${NC} ($IMAGE_SIZE)"
fi

# Step 4: TensorRT engine
if [ "$USE_TRT" = true ]; then
    echo -e "${CYAN}[4/6] Checking TensorRT engine...${NC}"

    mkdir -p "$ONNX_DIR" "$TRT_DIR"

    # Download ONNX if needed
    if [ ! -f "$ONNX_MODEL" ]; then
        echo "       Downloading ONNX model..."

        # Install dependencies if needed
        python3 -c "import huggingface_hub" 2>/dev/null || pip3 install -q huggingface_hub
        python3 -c "import onnx" 2>/dev/null || pip3 install -q onnx

        python3 << 'PYEOF'
import os
from huggingface_hub import snapshot_download
import onnx

onnx_dir = "models/onnx"
hf_dir = os.path.join(onnx_dir, "hf-download")
output = os.path.join(onnx_dir, "da3-small-embedded.onnx")

print("       Downloading from HuggingFace...")
snapshot_download(
    repo_id="onnx-community/depth-anything-v3-small",
    local_dir=hf_dir,
    allow_patterns=["*.onnx", "*.onnx_data"]
)

print("       Creating embedded ONNX file...")
model = onnx.load(os.path.join(hf_dir, "onnx", "model.onnx"))
onnx.save(model, output, save_as_external_data=False)
print(f"       Saved: {output}")
PYEOF
    fi

    # Build TensorRT engine if needed
    if [ ! -f "$TRT_ENGINE" ]; then
        echo "       Building TensorRT engine (takes ~2 minutes)..."
        echo ""

        $TRTEXEC \
            --onnx="$ONNX_MODEL" \
            --saveEngine="$TRT_ENGINE" \
            --fp16 \
            --memPoolSize=workspace:2048MiB \
            --optShapes=pixel_values:1x1x3x518x518 \
            2>&1 | grep -E "(Building|Serializing|SUCCESS|Throughput)" || true

        echo ""
    fi

    if [ -f "$TRT_ENGINE" ]; then
        ENGINE_SIZE=$(du -h "$TRT_ENGINE" | cut -f1)
        echo -e "       Engine ready: ${GREEN}$TRT_ENGINE${NC} ($ENGINE_SIZE)"
    else
        echo -e "${YELLOW}       Engine build failed, using PyTorch backend${NC}"
        USE_TRT=false
    fi
else
    echo -e "${CYAN}[4/6] Skipping TensorRT (PyTorch mode)${NC}"
fi

# Step 5: Start TensorRT service
if [ "$USE_TRT" = true ]; then
    echo -e "${CYAN}[5/6] Starting TensorRT service...${NC}"

    mkdir -p "$SHARED_DIR"
    chmod 777 "$SHARED_DIR"
    rm -f "$SHARED_DIR"/* 2>/dev/null || true

    python3 scripts/trt_inference_service_shm.py \
        --engine "$TRT_ENGINE" \
        > /tmp/trt_service.log 2>&1 &
    TRT_SERVICE_PID=$!

    # Wait for ready
    for i in {1..50}; do
        if [ -f "$SHARED_DIR/status" ]; then
            STATUS=$(cat "$SHARED_DIR/status" 2>/dev/null || echo "")
            if [[ "$STATUS" == ready* ]] || [[ "$STATUS" == complete* ]]; then
                echo -e "       ${GREEN}TRT service running${NC} (PID: $TRT_SERVICE_PID)"
                break
            fi
        fi
        sleep 0.1
    done

    if ! kill -0 "$TRT_SERVICE_PID" 2>/dev/null; then
        echo -e "${YELLOW}       TRT service failed, using PyTorch${NC}"
        USE_TRT=false
    fi
else
    echo -e "${CYAN}[5/6] Skipping TRT service (PyTorch mode)${NC}"
fi

# Step 6: Start container
echo -e "${CYAN}[6/6] Starting demo container...${NC}"

# Stop any existing container
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Build Docker run args
DOCKER_ARGS=(
    "--rm"
    "--name" "$CONTAINER_NAME"
    "--runtime" "nvidia"
    "--network" "host"
    "--ipc" "host"
    "-e" "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}"
)

# Add camera device with full v4l2 access
# v4l2 cameras need video group and proper device permissions for memory mapping
DOCKER_ARGS+=(
    "--device" "$CAMERA_DEVICE:$CAMERA_DEVICE"
    "--group-add" "video"
    "-v" "/dev:/dev:rw"
    "--device-cgroup-rule" "c 81:* rmw"
)

# Add display if available
if [ "$NO_DISPLAY" = false ] && [ -n "$DISPLAY" ]; then
    xhost +local:docker 2>/dev/null || true
    DOCKER_ARGS+=(
        "-e" "DISPLAY=$DISPLAY"
        "-e" "QT_X11_NO_MITSHM=1"
        "-v" "/tmp/.X11-unix:/tmp/.X11-unix:rw"
    )
fi

# Add TRT shared memory
if [ "$USE_TRT" = true ]; then
    DOCKER_ARGS+=(
        "-v" "$SHARED_DIR:$SHARED_DIR:rw"
        "-e" "DA3_USE_SHARED_MEMORY=true"
    )
fi

# Build launch command
LAUNCH_CMD="ros2 run v4l2_camera v4l2_camera_node --ros-args"
LAUNCH_CMD+=" -p video_device:=$CAMERA_DEVICE"
LAUNCH_CMD+=" -r /image_raw:=/camera/image_raw"
LAUNCH_CMD+=" & sleep 2"
LAUNCH_CMD+=" && ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py"
LAUNCH_CMD+=" image_topic:=/camera/image_raw"
LAUNCH_CMD+=" publish_colored:=true"
if [ "$USE_TRT" = true ]; then
    LAUNCH_CMD+=" use_shared_memory:=true"
fi

echo ""
echo -e "${BOLD}Demo Configuration:${NC}"
echo "  Camera:   $CAMERA_DEVICE"
echo "  Backend:  $([ "$USE_TRT" = true ] && echo "TensorRT FP16 (20-30 FPS via shared memory)" || echo "PyTorch (~5 FPS)")"
echo "  Display:  $([ "$NO_DISPLAY" = false ] && [ -n "$DISPLAY" ] && echo "Yes" || echo "Headless")"
echo ""

# Start container
echo -e "${GREEN}Starting depth estimation...${NC}"
echo ""

docker run "${DOCKER_ARGS[@]}" "$IMAGE_NAME" \
    bash -c "source /opt/ros/humble/install/setup.bash 2>/dev/null || source /opt/ros/humble/setup.bash && source /ros2_ws/install/setup.bash && $LAUNCH_CMD" &
CONTAINER_PID=$!

sleep 5

echo -e "${BOLD}============================================${NC}"
echo -e "${GREEN}Demo is running!${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""
echo "ROS2 Topics:"
echo "  Input:   /camera/image_raw"
echo "  Depth:   /depth_anything_3/depth"
echo "  Colored: /depth_anything_3/depth_colored"
echo ""

if [ "$NO_DISPLAY" = false ] && [ -n "$DISPLAY" ]; then
    echo "View depth output:"
    echo "  rqt_image_view /depth_anything_3/depth_colored"
    echo ""
fi

echo "Press Ctrl+C to stop"
echo ""

# Wait for container
wait $CONTAINER_PID 2>/dev/null || true
