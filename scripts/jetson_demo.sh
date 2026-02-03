#!/bin/bash
# Jetson Demo Script - Run directly on Jetson with display connected
# Usage: bash scripts/jetson_demo.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CONTAINER_NAME="da3_ros2_jetson"
ENGINE_PATH="$REPO_DIR/models/tensorrt/da3-small-fp16.engine"
SHARED_DIR="/tmp/da3_shared"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Depth Anything 3 - Jetson Demo${NC}"
echo -e "${CYAN}========================================${NC}"

# Check if running with display
if [ -z "$DISPLAY" ]; then
    echo -e "${RED}ERROR: No display detected.${NC}"
    echo -e "${YELLOW}This script must be run directly on Jetson with a monitor connected.${NC}"
    echo -e "${YELLOW}If using SSH, try: ssh -X gerdsenai@<jetson-ip> or run locally.${NC}"
    exit 1
fi

# Allow Docker X11 access
echo -e "${GREEN}[1/6] Configuring X11 display access...${NC}"
xhost +local:docker 2>/dev/null || true

# Create shared memory directory
echo -e "${GREEN}[2/6] Setting up shared memory directory...${NC}"
mkdir -p "$SHARED_DIR"
chmod 777 "$SHARED_DIR"
rm -f "$SHARED_DIR"/*.npy "$SHARED_DIR"/status "$SHARED_DIR"/ready 2>/dev/null || true

# Check for TensorRT engine
if [ ! -f "$ENGINE_PATH" ]; then
    echo -e "${RED}ERROR: TensorRT engine not found at $ENGINE_PATH${NC}"
    echo -e "${YELLOW}Build it first with: python3 scripts/build_tensorrt_engine.py${NC}"
    exit 1
fi

# Check container exists
if ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}ERROR: Container '$CONTAINER_NAME' not found.${NC}"
    echo -e "${YELLOW}Build it first with: docker build -t da3_ros2_jetson .${NC}"
    exit 1
fi

# Start container if not running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${GREEN}[3/6] Starting Docker container...${NC}"
    docker start "$CONTAINER_NAME"
    sleep 2
else
    echo -e "${GREEN}[3/6] Container already running...${NC}"
fi

# Kill any existing processes
echo -e "${GREEN}[4/6] Cleaning up old processes...${NC}"
pkill -f "trt_inference_service.py" 2>/dev/null || true
docker exec "$CONTAINER_NAME" pkill -f "v4l2_camera_node" 2>/dev/null || true
docker exec "$CONTAINER_NAME" pkill -f "depth_anything_3_node" 2>/dev/null || true
docker exec "$CONTAINER_NAME" pkill -f "demo_depth_viewer" 2>/dev/null || true
sleep 1

# Start TRT inference service on host
echo -e "${GREEN}[5/6] Starting TensorRT inference service...${NC}"
cd "$REPO_DIR"
python3 scripts/trt_inference_service.py --engine "$ENGINE_PATH" &
TRT_PID=$!
echo "TRT service PID: $TRT_PID"

# Wait for TRT service to be ready
echo -n "Waiting for TRT service"
for i in {1..30}; do
    if [ -f "$SHARED_DIR/ready" ]; then
        echo -e " ${GREEN}Ready!${NC}"
        break
    fi
    echo -n "."
    sleep 0.5
done

if [ ! -f "$SHARED_DIR/ready" ]; then
    echo -e " ${RED}Timeout!${NC}"
    kill $TRT_PID 2>/dev/null || true
    exit 1
fi

# Start camera node in container
echo -e "${GREEN}[6/6] Starting ROS2 nodes...${NC}"
docker exec -d "$CONTAINER_NAME" bash -c "
    source /opt/ros/humble/install/setup.bash 2>/dev/null || source /opt/ros/humble/setup.bash
    source /ros2_ws/install/setup.bash 2>/dev/null || true
    ros2 run v4l2_camera v4l2_camera_node --ros-args \
        -p video_device:=/dev/video0 \
        -r /image_raw:=/camera/image_raw
" &
sleep 2

# Start depth node in container
docker exec -d "$CONTAINER_NAME" bash -c "
    source /opt/ros/humble/install/setup.bash 2>/dev/null || source /opt/ros/humble/setup.bash
    source /ros2_ws/install/setup.bash 2>/dev/null || true
    ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
        use_shared_memory:=true \
        image_topic:=/camera/image_raw \
        publish_colored:=true
" &
sleep 3

echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}Pipeline running! Starting viewer...${NC}"
echo -e "${CYAN}========================================${NC}"
echo -e "${YELLOW}Controls: Q=Quit, S=Save screenshot, F=Toggle FPS${NC}"
echo ""

# Run viewer in foreground (blocking)
docker exec -it \
    -e DISPLAY="$DISPLAY" \
    -e QT_X11_NO_MITSHM=1 \
    "$CONTAINER_NAME" bash -c "
    source /opt/ros/humble/install/setup.bash 2>/dev/null || source /opt/ros/humble/setup.bash
    source /ros2_ws/install/setup.bash 2>/dev/null || true
    python3 /ros2_ws/src/depth_anything_3_ros2/scripts/demo_depth_viewer.py
"

# Cleanup on exit
echo -e "${YELLOW}Shutting down...${NC}"
kill $TRT_PID 2>/dev/null || true
docker exec "$CONTAINER_NAME" pkill -f "v4l2_camera_node" 2>/dev/null || true
docker exec "$CONTAINER_NAME" pkill -f "depth_anything_3_node" 2>/dev/null || true
echo -e "${GREEN}Done!${NC}"
