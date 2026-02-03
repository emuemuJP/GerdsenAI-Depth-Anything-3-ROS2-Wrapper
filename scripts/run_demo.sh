#!/bin/bash
#
# Depth Anything 3 - Live Demo Runner
#
# This script starts everything needed for a live depth visualization demo:
# 1. TRT inference service (host)
# 2. Camera driver (container)
# 3. Depth estimation node (container)
# 4. Visualization viewer (container with X11)
#
# Usage:
#   bash scripts/run_demo.sh
#
# Requirements:
#   - Jetson with display connected
#   - Camera at /dev/video0
#   - TensorRT engine built (run deploy_jetson.sh first)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
SHARED_DIR="/tmp/da3_shared"
ENGINE_PATH="$REPO_DIR/models/tensorrt/da3-small-fp16.engine"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=============================================="
echo "  Depth Anything 3 - Live Demo"
echo "=============================================="
echo ""

# Check for engine
if [ ! -f "$ENGINE_PATH" ]; then
    echo -e "${RED}ERROR: TensorRT engine not found${NC}"
    echo "Run first: bash scripts/deploy_jetson.sh --host-trt"
    exit 1
fi

# Check for camera
if [ ! -e "/dev/video0" ]; then
    echo -e "${RED}ERROR: No camera found at /dev/video0${NC}"
    exit 1
fi

# Check for display
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0
    echo -e "${YELLOW}Setting DISPLAY=:0${NC}"
fi

# Allow Docker to access X11 display
echo -e "${GREEN}Enabling X11 access for Docker...${NC}"
xhost +local:docker 2>/dev/null || xhost + 2>/dev/null || true

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down..."
    pkill -f trt_inference_service 2>/dev/null || true
    docker exec da3_ros2_jetson pkill -f depth_anything_3 2>/dev/null || true
    docker exec da3_ros2_jetson pkill -f v4l2_camera 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT

# 1. Start TRT service
echo -e "${GREEN}[1/4] Starting TRT inference service...${NC}"
pkill -f trt_inference_service 2>/dev/null || true
rm -rf "$SHARED_DIR"/*
mkdir -p "$SHARED_DIR"
chmod 777 "$SHARED_DIR"

python3 "$SCRIPT_DIR/trt_inference_service.py" \
    --engine "$ENGINE_PATH" \
    --poll-interval 0.001 &
TRT_PID=$!

# Wait for TRT to be ready
for i in {1..50}; do
    if [ -f "$SHARED_DIR/status" ]; then
        STATUS=$(cat "$SHARED_DIR/status")
        if [[ "$STATUS" == ready* ]] || [[ "$STATUS" == complete* ]]; then
            echo -e "${GREEN}   TRT service ready${NC}"
            break
        fi
    fi
    sleep 0.1
done

# 2. Start camera in container
echo -e "${GREEN}[2/4] Starting camera driver...${NC}"
docker exec da3_ros2_jetson pkill -f v4l2_camera 2>/dev/null || true
docker exec -d da3_ros2_jetson bash -c "
    source /opt/ros/humble/install/setup.bash
    source /ros2_ws/install/setup.bash
    ros2 run v4l2_camera v4l2_camera_node \
        --ros-args -p video_device:=/dev/video0 \
        -r /image_raw:=/camera/image_raw
"
sleep 2
echo -e "${GREEN}   Camera started${NC}"

# 3. Start depth node in container
echo -e "${GREEN}[3/4] Starting depth estimation node...${NC}"
docker exec da3_ros2_jetson pkill -f depth_anything_3 2>/dev/null || true
docker exec -d da3_ros2_jetson bash -c "
    source /opt/ros/humble/install/setup.bash
    source /ros2_ws/install/setup.bash
    ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
        use_shared_memory:=true \
        image_topic:=/camera/image_raw \
        publish_colored:=true
"
sleep 3
echo -e "${GREEN}   Depth node started${NC}"

# 4. Launch viewer
echo -e "${GREEN}[4/4] Launching depth viewer...${NC}"
echo ""

# Check if running with display access (not via SSH)
if [ -n "$SSH_CLIENT" ] || [ -n "$SSH_TTY" ]; then
    echo -e "${YELLOW}=============================================="
    echo "  Running via SSH - limited display access"
    echo "=============================================="
    echo ""
    echo "The depth pipeline is now running!"
    echo "To view the output, run ONE of these on the Jetson directly:"
    echo ""
    echo "  Option 1 - rqt_image_view (if ROS2 on host):"
    echo "    rqt_image_view /depth_anything_3/depth_colored"
    echo ""
    echo "  Option 2 - Docker with display:"
    echo "    xhost +local:docker"
    echo "    docker exec -e DISPLAY=:0 da3_ros2_jetson rqt_image_view /depth_anything_3/depth_colored"
    echo ""
    echo "Press Ctrl+C to stop the demo.${NC}"
    echo ""

    # Keep running until Ctrl+C
    while true; do
        sleep 5
        # Show stats
        if [ -f "/tmp/da3_shared/stats" ]; then
            STATS=$(cat /tmp/da3_shared/stats)
            FPS=$(echo $STATS | cut -d',' -f1)
            LATENCY=$(echo $STATS | cut -d',' -f2)
            FRAMES=$(echo $STATS | cut -d',' -f3)
            echo -e "TRT Stats: ${GREEN}${FPS} FPS${NC}, ${LATENCY}ms latency, ${FRAMES} frames"
        fi
    done
else
    echo "=============================================="
    echo "  Controls:"
    echo "    Q - Quit"
    echo "    S - Save frame"
    echo "    F - Toggle FPS"
    echo "=============================================="
    echo ""

    # Allow Docker to access X11 display
    xhost +local:docker 2>/dev/null || xhost + 2>/dev/null || true

    # Run viewer in container with X11 forwarding
    docker exec -e DISPLAY=$DISPLAY -e QT_X11_NO_MITSHM=1 da3_ros2_jetson bash -c "
        source /opt/ros/humble/install/setup.bash
        source /ros2_ws/install/setup.bash
        python3 /ros2_ws/src/depth_anything_3_ros2/scripts/demo_depth_viewer.py
    "
fi
