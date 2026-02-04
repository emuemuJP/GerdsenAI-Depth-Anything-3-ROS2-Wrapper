#!/bin/bash
# DEPRECATED: Use ./run.sh at repo root instead
#
# This script is kept for backwards compatibility but may be removed in future versions.
# The new ./run.sh script provides all functionality with a simpler interface:
#   ./run.sh                      # Auto-detect everything
#   ./run.sh --camera /dev/video0 # Specific camera
#   ./run.sh --no-display         # Headless mode
#   ./run.sh --rebuild            # Force rebuild
#
# ------------------------------------------------------------------
# Depth Anything V3 - Demo Script (Legacy)
# Single-command demo launcher for Jetson deployment
#
# Usage: bash scripts/demo.sh [options]
#
# Options:
#   --camera DEVICE     Specify camera device (e.g., /dev/video0)
#   --topic TOPIC       Specify ROS2 image topic directly
#   --no-rviz           Skip RViz2 launch
#   --no-monitor        Skip performance monitor
#   --no-trt            Use PyTorch instead of TensorRT
#   --rebuild           Force rebuild Docker image
#   --help              Show this help message
#
# Example:
#   bash scripts/demo.sh                     # Auto-detect camera, full demo
#   bash scripts/demo.sh --camera /dev/video0
#   bash scripts/demo.sh --topic /usb_cam/image_raw --no-rviz

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# Configuration
ONNX_DIR="models/onnx"
TRT_DIR="models/tensorrt"
ONNX_MODEL="$ONNX_DIR/da3-small-embedded.onnx"
TRT_ENGINE="$TRT_DIR/da3-small-fp16.engine"
TRTEXEC="/usr/src/tensorrt/bin/trtexec"
SHARED_DIR="/tmp/da3_shared"

# Process IDs for cleanup
TRT_SERVICE_PID=""
MONITOR_PID=""
RVIZ_PID=""
CONTAINER_NAME="da3_demo"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Default options
CAMERA_DEVICE=""
IMAGE_TOPIC=""
LAUNCH_RVIZ=true
LAUNCH_MONITOR=true
USE_TRT=true
FORCE_REBUILD=false

# Banner
echo ""
echo -e "${BOLD}======================================${NC}"
echo -e "${BOLD}   Depth Anything V3 - Demo Mode${NC}"
echo -e "${BOLD}======================================${NC}"
echo ""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --camera)
            CAMERA_DEVICE="$2"
            shift 2
            ;;
        --topic)
            IMAGE_TOPIC="$2"
            shift 2
            ;;
        --no-rviz)
            LAUNCH_RVIZ=false
            shift
            ;;
        --no-monitor)
            LAUNCH_MONITOR=false
            shift
            ;;
        --no-trt)
            USE_TRT=false
            shift
            ;;
        --rebuild)
            FORCE_REBUILD=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --camera DEVICE     Specify camera device (e.g., /dev/video0)"
            echo "  --topic TOPIC       Specify ROS2 image topic directly"
            echo "  --no-rviz           Skip RViz2 launch"
            echo "  --no-monitor        Skip performance monitor"
            echo "  --no-trt            Use PyTorch instead of TensorRT"
            echo "  --rebuild           Force rebuild Docker image"
            echo ""
            echo "Examples:"
            echo "  $0                              # Auto-detect camera"
            echo "  $0 --camera /dev/video0         # Use specific camera"
            echo "  $0 --topic /camera/image_raw    # Use existing topic"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down demo...${NC}"

    # Stop RViz2
    if [ -n "$RVIZ_PID" ] && kill -0 "$RVIZ_PID" 2>/dev/null; then
        echo "  Stopping RViz2..."
        kill "$RVIZ_PID" 2>/dev/null || true
    fi

    # Stop performance monitor
    if [ -n "$MONITOR_PID" ] && kill -0 "$MONITOR_PID" 2>/dev/null; then
        echo "  Stopping performance monitor..."
        kill "$MONITOR_PID" 2>/dev/null || true
    fi

    # Stop Docker container
    if docker ps -q -f name="$CONTAINER_NAME" 2>/dev/null | grep -q .; then
        echo "  Stopping Docker container..."
        docker stop "$CONTAINER_NAME" 2>/dev/null || true
    fi

    # Stop TRT service
    if [ -n "$TRT_SERVICE_PID" ] && kill -0 "$TRT_SERVICE_PID" 2>/dev/null; then
        echo "  Stopping TRT inference service..."
        kill "$TRT_SERVICE_PID" 2>/dev/null || true
        wait "$TRT_SERVICE_PID" 2>/dev/null || true
    fi

    echo -e "${GREEN}Demo stopped.${NC}"
}
trap cleanup EXIT INT TERM

# Step 1: Pre-flight checks
echo -e "${CYAN}[1/6] Pre-flight checks...${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker not installed${NC}"
    echo "       Install with: sudo apt install docker.io"
    exit 1
fi

# Check docker group membership
if ! docker info &> /dev/null; then
    echo -e "${RED}ERROR: Cannot connect to Docker daemon${NC}"
    echo "       Add your user to the docker group:"
    echo "         sudo usermod -aG docker \$USER"
    echo "       Then log out and back in, or run: newgrp docker"
    exit 1
fi

# Check nvidia-docker
if ! docker info 2>/dev/null | grep -q "nvidia"; then
    echo -e "${YELLOW}WARNING: NVIDIA Docker runtime may not be configured${NC}"
fi

# Check TensorRT (optional)
if [ "$USE_TRT" = true ]; then
    if [ ! -f "$TRTEXEC" ]; then
        echo -e "${YELLOW}WARNING: TensorRT not found, will use PyTorch fallback (~5 FPS)${NC}"
        USE_TRT=false
    else
        TRT_VERSION=$($TRTEXEC --help 2>&1 | grep -oP 'TensorRT v\K[0-9]+' | head -1 || echo "0")
        if [ "$TRT_VERSION" -lt 10 ]; then
            echo -e "${YELLOW}WARNING: TensorRT $TRT_VERSION found, need 10.3+ for optimal performance${NC}"
            USE_TRT=false
        else
            echo -e "       TensorRT 10.x detected"
        fi
    fi
fi

echo -e "       ${GREEN}Pre-flight checks passed${NC}"

# Step 2: Camera detection
echo -e "${CYAN}[2/6] Detecting cameras...${NC}"

if [ -n "$IMAGE_TOPIC" ]; then
    # User specified topic directly
    echo -e "       Using specified topic: ${GREEN}$IMAGE_TOPIC${NC}"
    CAMERA_DEVICE=""
elif [ -n "$CAMERA_DEVICE" ]; then
    # User specified camera device
    if [ ! -e "$CAMERA_DEVICE" ]; then
        echo -e "${RED}ERROR: Camera device not found: $CAMERA_DEVICE${NC}"
        exit 1
    fi
    echo -e "       Using specified camera: ${GREEN}$CAMERA_DEVICE${NC}"
    IMAGE_TOPIC="/camera/image_raw"
else
    # Auto-detect cameras
    echo "       Scanning for cameras..."

    # Run camera detection
    if [ -f "$SCRIPT_DIR/detect_cameras.sh" ]; then
        # Get cameras in JSON format
        cameras_json=$(bash "$SCRIPT_DIR/detect_cameras.sh" --json 2>/dev/null || echo "[]")
        num_cameras=$(echo "$cameras_json" | grep -c '"device"' || echo "0")

        if [ "$num_cameras" -eq 0 ]; then
            echo -e "${YELLOW}No cameras detected.${NC}"
            echo ""
            echo "Options:"
            echo "  1. Connect a USB camera and run again"
            echo "  2. Specify topic manually: --topic /your/image/topic"
            echo "  3. Use test images (see examples/scripts/)"
            exit 1
        elif [ "$num_cameras" -eq 1 ]; then
            # Single camera - use it
            CAMERA_DEVICE=$(echo "$cameras_json" | grep '"device"' | head -1 | sed 's/.*"device": "\([^"]*\)".*/\1/')
            CAMERA_NAME=$(echo "$cameras_json" | grep '"name"' | head -1 | sed 's/.*"name": "\([^"]*\)".*/\1/')
            IMAGE_TOPIC="/camera/image_raw"
            echo -e "       Found: ${GREEN}$CAMERA_NAME${NC}"
            echo "       Device: $CAMERA_DEVICE"
        else
            # Multiple cameras - show selection menu
            echo -e "       Found ${GREEN}$num_cameras${NC} cameras:"
            echo ""

            # Parse and display cameras
            idx=0
            declare -a cam_devices=()
            declare -a cam_names=()
            while IFS= read -r line; do
                if echo "$line" | grep -q '"device"'; then
                    dev=$(echo "$line" | sed 's/.*"device": "\([^"]*\)".*/\1/')
                    cam_devices+=("$dev")
                fi
                if echo "$line" | grep -q '"name"'; then
                    name=$(echo "$line" | sed 's/.*"name": "\([^"]*\)".*/\1/')
                    cam_names+=("$name")
                    echo "       [$idx] $name ($dev)"
                    ((idx++)) || true
                fi
            done <<< "$cameras_json"

            echo ""
            read -p "       Select camera [0-$((idx-1))]: " selection

            if [[ "$selection" =~ ^[0-9]+$ ]] && [ "$selection" -lt "$idx" ]; then
                CAMERA_DEVICE="${cam_devices[$selection]}"
                CAMERA_NAME="${cam_names[$selection]}"
                IMAGE_TOPIC="/camera/image_raw"
                echo -e "       Selected: ${GREEN}$CAMERA_NAME${NC}"
            else
                echo -e "${RED}Invalid selection${NC}"
                exit 1
            fi
        fi
    else
        # Fallback: simple /dev/video0 check
        if [ -e "/dev/video0" ]; then
            CAMERA_DEVICE="/dev/video0"
            IMAGE_TOPIC="/camera/image_raw"
            echo -e "       Found: ${GREEN}/dev/video0${NC}"
        else
            echo -e "${RED}No cameras found. Please connect a camera or specify --topic${NC}"
            exit 1
        fi
    fi
fi

# Step 3: TensorRT engine
if [ "$USE_TRT" = true ]; then
    echo -e "${CYAN}[3/6] Checking TensorRT engine...${NC}"

    mkdir -p "$ONNX_DIR" "$TRT_DIR"

    # Check for ONNX model
    if [ ! -f "$ONNX_MODEL" ]; then
        echo "       Downloading ONNX model from HuggingFace..."

        # Auto-install huggingface_hub if missing
        if ! python3 -c "import huggingface_hub" 2>/dev/null; then
            echo "       Installing huggingface_hub..."
            if ! pip3 install huggingface_hub 2>&1 | tail -2; then
                echo -e "${YELLOW}WARNING: Failed to install huggingface_hub${NC}"
                USE_TRT=false
            fi
        fi

        # Auto-install onnx if missing
        if [ "$USE_TRT" = true ] && ! python3 -c "import onnx" 2>/dev/null; then
            echo "       Installing onnx..."
            if ! pip3 install onnx 2>&1 | tail -2; then
                echo -e "${YELLOW}WARNING: Failed to install onnx${NC}"
                USE_TRT=false
            fi
        fi

        # Download and embed model
        if [ "$USE_TRT" = true ]; then
            python3 << 'PYEOF'
import os
import sys
try:
    from huggingface_hub import snapshot_download
    import onnx

    onnx_dir = "models/onnx"
    hf_download_dir = os.path.join(onnx_dir, "hf-download")
    output_model = os.path.join(onnx_dir, "da3-small-embedded.onnx")

    print("       Downloading ONNX model...")
    snapshot_download(
        repo_id="onnx-community/depth-anything-v3-small",
        local_dir=hf_download_dir,
        allow_patterns=["*.onnx", "*.onnx_data"]
    )

    print("       Embedding weights into single ONNX file...")
    model_path = os.path.join(hf_download_dir, "onnx", "model.onnx")
    model = onnx.load(model_path)
    onnx.save(model, output_model, save_as_external_data=False)
    print(f"       Created: {output_model}")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
            if [ $? -ne 0 ]; then
                echo -e "${YELLOW}WARNING: Failed to download ONNX model, falling back to PyTorch${NC}"
                USE_TRT=false
            fi
        fi
    fi

    # Check for TensorRT engine
    if [ ! -f "$TRT_ENGINE" ]; then
        echo "       Building TensorRT engine (first time only)..."
        echo "       This takes approximately 2 minutes..."
        echo ""

        $TRTEXEC \
            --onnx="$ONNX_MODEL" \
            --saveEngine="$TRT_ENGINE" \
            --fp16 \
            --memPoolSize=workspace:2048MiB \
            --optShapes=pixel_values:1x1x3x518x518 \
            2>&1 | grep -E "(Building|Serializing|SUCCESS|Throughput)" || true

        if [ ! -f "$TRT_ENGINE" ]; then
            echo -e "${YELLOW}WARNING: Engine build failed, falling back to PyTorch${NC}"
            USE_TRT=false
        fi
    fi

    if [ -f "$TRT_ENGINE" ]; then
        ENGINE_SIZE=$(du -h "$TRT_ENGINE" | cut -f1)
        echo -e "       Engine ready: ${GREEN}$TRT_ENGINE${NC} ($ENGINE_SIZE)"
    fi
else
    echo -e "${CYAN}[3/6] Skipping TensorRT (PyTorch mode)${NC}"
fi

# Step 4: Start TRT inference service
if [ "$USE_TRT" = true ]; then
    echo -e "${CYAN}[4/6] Starting TensorRT inference service...${NC}"

    # Create shared directory
    mkdir -p "$SHARED_DIR"
    chmod 777 "$SHARED_DIR"

    # Check Python dependencies
    # Check TensorRT
    if ! python3 -c "import tensorrt" 2>/dev/null; then
        echo -e "${YELLOW}WARNING: TensorRT Python bindings not found${NC}"
        echo "       Falling back to PyTorch"
        USE_TRT=false
    else
        # Auto-install numpy if missing
        if ! python3 -c "import numpy" 2>/dev/null; then
            echo "       Installing numpy..."
            if ! pip3 install numpy 2>&1 | tail -2; then
                echo -e "${YELLOW}WARNING: Failed to install numpy, falling back to PyTorch${NC}"
                USE_TRT=false
            fi
        fi

        # Auto-install pycuda if missing
        if [ "$USE_TRT" = true ] && ! python3 -c "import pycuda.driver" 2>/dev/null; then
            echo "       Installing pycuda (required for TRT inference)..."
            if pip3 install pycuda 2>&1 | tail -3; then
                echo -e "${GREEN}       pycuda installed successfully${NC}"
            else
                echo -e "${YELLOW}WARNING: Failed to install pycuda, falling back to PyTorch${NC}"
                USE_TRT=false
            fi
        fi
    fi

    if [ "$USE_TRT" = true ]; then
        # Start TRT service
        python3 "$SCRIPT_DIR/trt_inference_service.py" \
            --engine "$TRT_ENGINE" \
            --poll-interval 0.001 \
            > /tmp/trt_service.log 2>&1 &
        TRT_SERVICE_PID=$!

        # Wait for initialization
        sleep 2
        if ! kill -0 "$TRT_SERVICE_PID" 2>/dev/null; then
            echo -e "${YELLOW}WARNING: TRT service failed to start${NC}"
            echo "       Check /tmp/trt_service.log for details"
            USE_TRT=false
        else
            echo -e "       TRT service running (PID: ${GREEN}$TRT_SERVICE_PID${NC})"
        fi
    fi
else
    echo -e "${CYAN}[4/6] Skipping TRT service (PyTorch mode)${NC}"
fi

# Step 5: Docker container
echo -e "${CYAN}[5/6] Starting Docker container...${NC}"

# Check if image exists
if [ "$FORCE_REBUILD" = true ] || ! docker images | grep -q "depth_anything_3_ros2.*jetson"; then
    echo "       Building Docker image (this may take 15-20 minutes)..."
    docker compose build depth-anything-3-jetson
fi

# Stop any existing container
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Prepare Docker run command
DOCKER_ARGS=(
    "--rm"
    "--name" "$CONTAINER_NAME"
    "--runtime" "nvidia"
    "--network" "host"
    "--ipc" "host"
    "-e" "DISPLAY=$DISPLAY"
    "-e" "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}"
    "-v" "/tmp/.X11-unix:/tmp/.X11-unix:rw"
    "-v" "$SHARED_DIR:$SHARED_DIR:rw"
    "-v" "$REPO_DIR/models:/ros2_ws/src/depth_anything_3_ros2/models:rw"
)

# Add camera device if USB
if [ -n "$CAMERA_DEVICE" ] && [[ "$CAMERA_DEVICE" == /dev/video* ]]; then
    DOCKER_ARGS+=("--device" "$CAMERA_DEVICE:$CAMERA_DEVICE")
fi

# Add TensorRT mounts if using host TRT
if [ "$USE_TRT" = true ]; then
    DOCKER_ARGS+=(
        "-v" "/usr/src/tensorrt:/usr/src/tensorrt:ro"
        "-e" "DA3_HOST_TRT=true"
    )
fi

# Build the ROS2 launch command
LAUNCH_CMD="ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py"
LAUNCH_CMD+=" image_topic:=$IMAGE_TOPIC"
LAUNCH_CMD+=" log_inference_time:=true"
LAUNCH_CMD+=" publish_confidence:=true"

# Determine image name
IMAGE_NAME="depth_anything_3_ros2:jetson"
if ! docker images | grep -q "depth_anything_3_ros2.*jetson"; then
    IMAGE_NAME="ghcr.io/gerdsenai/depth_anything_3_ros2:jetson"
fi

echo ""
echo -e "${BOLD}Demo Configuration:${NC}"
echo "  Camera:     ${CAMERA_DEVICE:-"(topic: $IMAGE_TOPIC)"}"
echo "  Image Topic: $IMAGE_TOPIC"
echo "  Backend:    $([ "$USE_TRT" = true ] && echo "TensorRT FP16 (~40 FPS)" || echo "PyTorch (~5 FPS)")"
echo "  RViz2:      $([ "$LAUNCH_RVIZ" = true ] && echo "Yes" || echo "No")"
echo "  Monitor:    $([ "$LAUNCH_MONITOR" = true ] && echo "Yes" || echo "No")"
echo ""

# Start v4l2_camera if using USB camera
if [ -n "$CAMERA_DEVICE" ] && [[ "$CAMERA_DEVICE" == /dev/video* ]]; then
    # Launch container with v4l2_camera + depth node
    FULL_CMD="ros2 run v4l2_camera v4l2_camera_node --ros-args"
    FULL_CMD+=" -p video_device:=$CAMERA_DEVICE"
    FULL_CMD+=" -r image_raw:=$IMAGE_TOPIC"
    FULL_CMD+=" & sleep 2 && $LAUNCH_CMD"
else
    FULL_CMD="$LAUNCH_CMD"
fi

echo -e "${GREEN}Starting depth estimation...${NC}"
echo "  Container: $CONTAINER_NAME"
echo ""

# Launch container in background
# Note: dustynv Jetson images use /opt/ros/humble/install/setup.bash
docker run "${DOCKER_ARGS[@]}" "$IMAGE_NAME" \
    bash -c "source /opt/ros/humble/install/setup.bash && source /ros2_ws/install/setup.bash && $FULL_CMD" &
CONTAINER_PID=$!

# Wait for container to start
sleep 5

# Step 6: Performance monitor and RViz2
echo -e "${CYAN}[6/6] Starting visualization tools...${NC}"

# Start performance monitor
if [ "$LAUNCH_MONITOR" = true ]; then
    if [ -f "$SCRIPT_DIR/performance_monitor.sh" ]; then
        # Check if we have a terminal to launch in
        if [ -n "$DISPLAY" ] && command -v gnome-terminal &> /dev/null; then
            gnome-terminal --title="DA3 Performance Monitor" -- bash "$SCRIPT_DIR/performance_monitor.sh" &
            MONITOR_PID=$!
            echo "       Performance monitor started (new terminal)"
        elif [ -n "$DISPLAY" ] && command -v xterm &> /dev/null; then
            xterm -title "DA3 Performance Monitor" -e "bash $SCRIPT_DIR/performance_monitor.sh" &
            MONITOR_PID=$!
            echo "       Performance monitor started (xterm)"
        else
            # No GUI terminal - show inline
            echo "       Performance monitor: View with 'bash scripts/performance_monitor.sh'"
        fi
    else
        echo "       Performance monitor script not found"
    fi
fi

# Start RViz2
if [ "$LAUNCH_RVIZ" = true ]; then
    if command -v rviz2 &> /dev/null; then
        # Source ROS2 if needed
        if [ -f "/opt/ros/humble/setup.bash" ]; then
            source /opt/ros/humble/setup.bash
        fi

        RVIZ_CONFIG="$REPO_DIR/rviz/depth_view.rviz"
        if [ -f "$RVIZ_CONFIG" ]; then
            rviz2 -d "$RVIZ_CONFIG" &
            RVIZ_PID=$!
            echo -e "       RViz2 started with config: ${GREEN}depth_view.rviz${NC}"
        else
            rviz2 &
            RVIZ_PID=$!
            echo "       RViz2 started (no config file)"
        fi
    else
        echo -e "${YELLOW}       RViz2 not installed on host${NC}"
        echo "       Install with: sudo apt install ros-humble-rviz2"
        echo "       Then source: source /opt/ros/humble/setup.bash"
    fi
fi

echo ""
echo -e "${BOLD}======================================${NC}"
echo -e "${GREEN}Demo is running!${NC}"
echo -e "${BOLD}======================================${NC}"
echo ""
echo "ROS2 Topics:"
echo "  Input:  $IMAGE_TOPIC"
echo "  Depth:  /camera/depth_anything_3/depth"
echo "  Color:  /camera/depth_anything_3/depth_colored"
echo ""
echo "Press Ctrl+C to stop the demo"
echo ""

# Wait for container to exit
wait $CONTAINER_PID 2>/dev/null || true
