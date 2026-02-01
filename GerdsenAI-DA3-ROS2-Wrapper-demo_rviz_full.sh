#!/bin/bash
# GerdsenAI Depth Anything 3 ROS2 Wrapper - Full RViz Demo Script
# Launches node with image publisher, RViz2, and monitoring terminals
# For Ubuntu Desktop with gnome-terminal
#
# This script auto-sources ROS2, installs missing dependencies, and builds if needed.
# Logs are written to /tmp/da3_demo_logs/ for debugging.
#
# Usage:
#   ./GerdsenAI-DA3-ROS2-Wrapper-demo_rviz_full.sh
#
# Requirements:
#   - Ubuntu 22.04 with gnome-terminal
#   - ROS2 Humble/Jazzy/Iron installed in /opt/ros/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

# Configuration
IMAGE_PATH="${REPO_ROOT}/examples/images/outdoor/street_01.jpg"
MODEL_NAME="depth-anything/DA3-BASE"
PUBLISH_RATE="1.0"
RVIZ_CONFIG="${REPO_ROOT}/rviz/depth_view.rviz"

# Node naming (must match launch file: namespace='test', name='depth_anything_3')
NODE_NAMESPACE="test"
NODE_NAME="depth_anything_3"
FULL_NODE_NAME="/${NODE_NAMESPACE}/${NODE_NAME}"

# Topic names (node uses ~/topic pattern which expands to /namespace/node_name/topic)
DEPTH_TOPIC="/${NODE_NAMESPACE}/${NODE_NAME}/depth"
DEPTH_COLORED_TOPIC="/${NODE_NAMESPACE}/${NODE_NAME}/depth_colored"
CONFIDENCE_TOPIC="/${NODE_NAMESPACE}/${NODE_NAME}/confidence"
IMAGE_INPUT_TOPIC="/test_image/image_raw"

# Logging
LOG_DIR="/tmp/da3_demo_logs"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MAIN_LOG="${LOG_DIR}/main_${TIMESTAMP}.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
    echo "[INFO] $(date +%H:%M:%S) $1" >> "$MAIN_LOG"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo "[WARN] $(date +%H:%M:%S) $1" >> "$MAIN_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "[ERROR] $(date +%H:%M:%S) $1" >> "$MAIN_LOG"
}

log_header() {
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN} $1${NC}"
    echo -e "${CYAN}============================================${NC}"
}

# Print banner
log_header "GerdsenAI Depth Anything 3 ROS2 Wrapper Demo"
log_info "Log directory: $LOG_DIR"
log_info "Main log: $MAIN_LOG"

# Check for gnome-terminal
if ! command -v gnome-terminal &> /dev/null; then
    log_error "gnome-terminal not found. Install with: sudo apt install gnome-terminal"
    exit 1
fi

# Auto-source ROS2
DETECTED_ROS_DISTRO=""
if [ -n "$ROS_DISTRO" ]; then
    DETECTED_ROS_DISTRO="$ROS_DISTRO"
    log_info "ROS2 already sourced: $DETECTED_ROS_DISTRO"
else
    log_info "Auto-detecting ROS2..."
    for distro in humble jazzy iron; do
        if [ -f "/opt/ros/${distro}/setup.bash" ]; then
            DETECTED_ROS_DISTRO="$distro"
            source "/opt/ros/${distro}/setup.bash"
            log_info "Sourced ROS2 ${distro}"
            break
        fi
    done
fi

if [ -z "$DETECTED_ROS_DISTRO" ]; then
    log_error "No ROS2 installation found in /opt/ros/"
    log_error "Install ROS2 Humble: https://docs.ros.org/en/humble/Installation.html"
    exit 1
fi

# Check and install missing ROS2 packages
log_info "Checking ROS2 dependencies..."

install_ros_pkg() {
    local pkg="ros-${DETECTED_ROS_DISTRO}-$1"
    if ! dpkg -l 2>/dev/null | grep -q "^ii  ${pkg} "; then
        log_warn "Installing missing package: ${pkg}"
        sudo apt install -y "$pkg" >> "$MAIN_LOG" 2>&1 || {
            log_error "Failed to install ${pkg}"
            return 1
        }
        log_info "Installed ${pkg}"
    fi
}

install_ros_pkg "cv-bridge"
install_ros_pkg "image-publisher"
install_ros_pkg "rviz2"
install_ros_pkg "rqt-image-view"

# Source workspace if exists, build if needed
if [ -f "${REPO_ROOT}/install/setup.bash" ]; then
    source "${REPO_ROOT}/install/setup.bash"
    log_info "Sourced workspace"
fi

# Check if package exists, build if not
if ! ros2 pkg list 2>/dev/null | grep -q "depth_anything_3_ros2"; then
    log_warn "Package not found, building workspace..."
    cd "$REPO_ROOT"
    colcon build --packages-select depth_anything_3_ros2 --symlink-install >> "$MAIN_LOG" 2>&1
    if [ $? -eq 0 ]; then
        source "${REPO_ROOT}/install/setup.bash"
        log_info "Build successful"
    else
        log_error "Build failed. Check $MAIN_LOG"
        exit 1
    fi
fi

log_info "Package depth_anything_3_ros2 ready"

# Check sample image
if [ ! -f "$IMAGE_PATH" ]; then
    log_warn "Sample image not found, downloading..."
    if [ -f "${REPO_ROOT}/examples/scripts/download_samples.sh" ]; then
        cd "${REPO_ROOT}/examples" && bash scripts/download_samples.sh >> "$MAIN_LOG" 2>&1
        cd "$REPO_ROOT"
    fi
fi

if [ ! -f "$IMAGE_PATH" ]; then
    log_error "Sample image not found: $IMAGE_PATH"
    exit 1
fi

# Find launch file
PKG_PREFIX=$(ros2 pkg prefix depth_anything_3_ros2 2>/dev/null)
LAUNCH_FILE="${PKG_PREFIX}/share/depth_anything_3_ros2/launch/examples/image_publisher_test.launch.py"

if [ ! -f "$LAUNCH_FILE" ]; then
    LAUNCH_FILE="${REPO_ROOT}/launch/examples/image_publisher_test.launch.py"
fi

if [ ! -f "$LAUNCH_FILE" ]; then
    log_error "Launch file not found"
    exit 1
fi

log_info "Launch file: $LAUNCH_FILE"

# Display configuration
log_info "Configuration:"
log_info "  Image: $IMAGE_PATH"
log_info "  Model: $MODEL_NAME"
log_info "  Rate: $PUBLISH_RATE Hz"
log_info "  Node: $FULL_NODE_NAME"
log_info "  Depth topic: $DEPTH_TOPIC"

# Create shared environment setup script
SETUP_SCRIPT="${LOG_DIR}/setup_env.sh"
cat > "$SETUP_SCRIPT" << SETUP_EOF
#!/bin/bash
# Auto-generated environment setup for DA3 demo terminals
export ROS_DISTRO="${DETECTED_ROS_DISTRO}"
export REPO_ROOT="${REPO_ROOT}"
export NODE_NAMESPACE="${NODE_NAMESPACE}"
export NODE_NAME="${NODE_NAME}"
export FULL_NODE_NAME="${FULL_NODE_NAME}"
export DEPTH_TOPIC="${DEPTH_TOPIC}"
export DEPTH_COLORED_TOPIC="${DEPTH_COLORED_TOPIC}"
export CONFIDENCE_TOPIC="${CONFIDENCE_TOPIC}"
export IMAGE_INPUT_TOPIC="${IMAGE_INPUT_TOPIC}"
export IMAGE_PATH="${IMAGE_PATH}"
export MODEL_NAME="${MODEL_NAME}"
export PUBLISH_RATE="${PUBLISH_RATE}"
export LAUNCH_FILE="${LAUNCH_FILE}"
export RVIZ_CONFIG="${RVIZ_CONFIG}"
export LOG_DIR="${LOG_DIR}"

source /opt/ros/\${ROS_DISTRO}/setup.bash
source \${REPO_ROOT}/install/setup.bash

echo "Environment loaded"
echo "  Node: \$FULL_NODE_NAME"
echo "  Depth topic: \$DEPTH_TOPIC"
SETUP_EOF
chmod +x "$SETUP_SCRIPT"

# Cleanup function
cleanup() {
    echo ""
    log_info "Shutting down demo processes..."
    pkill -f "image_publisher_test.launch.py" 2>/dev/null || true
    pkill -f "depth_anything_3_node" 2>/dev/null || true
    pkill -f "image_publisher_node" 2>/dev/null || true
    sleep 1
    log_info "Demo stopped. Logs: $LOG_DIR"
}
trap cleanup EXIT INT TERM

echo ""
log_header "Launching Demo Terminals"

# Terminal 1: Main node with image publisher
log_info "Terminal 1: Depth estimation node..."
NODE_LOG="${LOG_DIR}/node_${TIMESTAMP}.log"

gnome-terminal --title="[1] DA3 Node" --geometry=130x35+0+0 -- bash -c '
NODE_LOG="'"$NODE_LOG"'"
SETUP_SCRIPT="'"$SETUP_SCRIPT"'"

exec > >(tee -a "$NODE_LOG") 2>&1

echo "============================================"
echo " GerdsenAI DA3 - Depth Estimation Node"
echo "============================================"
echo ""
echo "Log: $NODE_LOG"
echo ""

source "$SETUP_SCRIPT"

echo ""
echo "Configuration:"
echo "  Image: $IMAGE_PATH"
echo "  Model: $MODEL_NAME"
echo "  Rate: $PUBLISH_RATE Hz"
echo ""

# Check Python dependencies
echo "Checking Python dependencies..."
python3 -c "import torch; print(f\"  PyTorch: {torch.__version__}\")" 2>/dev/null || {
    echo "ERROR: PyTorch not installed"
    read -p "Press Enter to close."
    exit 1
}
python3 -c "import cv2; print(f\"  OpenCV: {cv2.__version__}\")" 2>/dev/null || {
    echo "ERROR: OpenCV not installed"
    read -p "Press Enter to close."
    exit 1
}
python3 -c "import torch; cuda=torch.cuda.is_available(); print(f\"  CUDA: {cuda}\")"

echo ""
echo "Starting ROS2 launch..."
echo "========================================"
echo ""

ros2 launch "$LAUNCH_FILE" \
    image_path:="$IMAGE_PATH" \
    model_name:="$MODEL_NAME" \
    publish_rate:="$PUBLISH_RATE"

EXIT_CODE=$?
echo ""
echo "========================================"
echo "Node exited with code: $EXIT_CODE"
echo ""
if [ $EXIT_CODE -ne 0 ]; then
    echo "Common issues:"
    echo "  - Missing Python packages"
    echo "  - Model download failed (check internet)"
    echo "  - Out of memory (try smaller model)"
fi
read -p "Press Enter to close."
' &
sleep 6

# Terminal 2: RViz2
log_info "Terminal 2: RViz2 visualization..."
RVIZ_LOG="${LOG_DIR}/rviz_${TIMESTAMP}.log"

gnome-terminal --title="[2] RViz2" --geometry=100x25+850+0 -- bash -c '
RVIZ_LOG="'"$RVIZ_LOG"'"
SETUP_SCRIPT="'"$SETUP_SCRIPT"'"

exec > >(tee -a "$RVIZ_LOG") 2>&1

echo "============================================"
echo " GerdsenAI DA3 - RViz2 Visualization"
echo "============================================"
echo ""

source "$SETUP_SCRIPT"

if ! command -v rviz2 &> /dev/null; then
    echo "ERROR: rviz2 not found"
    echo "Install: sudo apt install ros-${ROS_DISTRO}-rviz2"
    read -p "Press Enter to close."
    exit 1
fi

echo "Waiting for topics (5 sec)..."
sleep 5

echo ""
echo "Starting RViz2..."
echo "Add Image displays for:"
echo "  - $DEPTH_TOPIC"
echo "  - $DEPTH_COLORED_TOPIC"
echo ""

if [ -f "$RVIZ_CONFIG" ]; then
    rviz2 -d "$RVIZ_CONFIG"
else
    rviz2
fi

read -p "Press Enter to close."
' &
sleep 2

# Terminal 3: Topic monitor
log_info "Terminal 3: Topic monitoring..."
TOPICS_LOG="${LOG_DIR}/topics_${TIMESTAMP}.log"

gnome-terminal --title="[3] Topic Monitor" --geometry=100x35+0+450 -- bash -c '
TOPICS_LOG="'"$TOPICS_LOG"'"
SETUP_SCRIPT="'"$SETUP_SCRIPT"'"

exec > >(tee -a "$TOPICS_LOG") 2>&1

echo "============================================"
echo " GerdsenAI DA3 - Topic Monitor"
echo "============================================"
echo ""

source "$SETUP_SCRIPT"

echo "Waiting for node to start (12 sec)..."
sleep 12

echo ""
echo "All topics:"
echo "-----------"
ros2 topic list
echo ""

echo "Depth topics:"
echo "-------------"
ros2 topic list | grep -E "depth|confidence" || echo "None found yet"
echo ""

echo "Checking depth topic: $DEPTH_TOPIC"
ros2 topic info "$DEPTH_TOPIC" 2>/dev/null || echo "Topic not available yet"
echo ""

echo "Waiting for first message (30s)..."
timeout 30 ros2 topic echo "$DEPTH_TOPIC" --once 2>/dev/null && echo "Message received!" || {
    echo "Timeout - check Terminal 1 for errors"
}
echo ""

echo "Monitoring frequency (15 sec)..."
timeout 15 ros2 topic hz "$DEPTH_TOPIC" 2>/dev/null || echo "Done"
echo ""

echo ""
echo "Interactive menu:"
echo "  1) Topic frequency"
echo "  2) Echo messages"
echo "  3) List topics"
echo "  4) Node info"
echo "  5) Exit"

while true; do
    read -p "Choice [1-5]: " choice
    case $choice in
        1) ros2 topic hz "$DEPTH_TOPIC" ;;
        2) ros2 topic echo "$DEPTH_TOPIC" ;;
        3) ros2 topic list ;;
        4) ros2 node list && echo "" && ros2 node info "$FULL_NODE_NAME" 2>/dev/null ;;
        5) break ;;
        *) echo "Invalid" ;;
    esac
    echo ""
done
' &
sleep 1

# Terminal 4: Parameter monitor
log_info "Terminal 4: Parameter monitoring..."
PARAMS_LOG="${LOG_DIR}/params_${TIMESTAMP}.log"

gnome-terminal --title="[4] Parameters" --geometry=100x30+850+450 -- bash -c '
PARAMS_LOG="'"$PARAMS_LOG"'"
SETUP_SCRIPT="'"$SETUP_SCRIPT"'"

exec > >(tee -a "$PARAMS_LOG") 2>&1

echo "============================================"
echo " GerdsenAI DA3 - Parameter Monitor"
echo "============================================"
echo ""

source "$SETUP_SCRIPT"

echo "Waiting for node (14 sec)..."
sleep 14

echo ""
echo "Active nodes:"
echo "-------------"
ros2 node list
echo ""

echo "Parameters for $FULL_NODE_NAME:"
echo "--------------------------------"
ros2 param list "$FULL_NODE_NAME" 2>/dev/null || echo "Node not available"
echo ""

echo "Key parameters:"
echo "---------------"
for p in model_name device inference_height inference_width colormap; do
    val=$(ros2 param get "$FULL_NODE_NAME" $p 2>/dev/null | grep -oP "(?<=value: ).*" || echo "N/A")
    echo "  $p: $val"
done

echo ""
read -p "Press Enter for node info..."
ros2 node info "$FULL_NODE_NAME" 2>/dev/null || echo "Not available"

read -p "Press Enter to close."
' &
sleep 1

# Terminal 5: Additional topics
log_info "Terminal 5: Additional topics..."
EXTRA_LOG="${LOG_DIR}/extra_${TIMESTAMP}.log"

gnome-terminal --title="[5] Extra Topics" --geometry=100x30+425+225 -- bash -c '
EXTRA_LOG="'"$EXTRA_LOG"'"
SETUP_SCRIPT="'"$SETUP_SCRIPT"'"

exec > >(tee -a "$EXTRA_LOG") 2>&1

echo "============================================"
echo " GerdsenAI DA3 - Additional Topics"
echo "============================================"
echo ""

source "$SETUP_SCRIPT"

echo "Waiting for node (16 sec)..."
sleep 16

echo ""
echo "1. Colored depth: $DEPTH_COLORED_TOPIC"
ros2 topic info "$DEPTH_COLORED_TOPIC" 2>/dev/null || echo "   Not available"
echo ""

echo "2. Confidence: $CONFIDENCE_TOPIC"
ros2 topic info "$CONFIDENCE_TOPIC" 2>/dev/null || echo "   Not available"
echo ""

echo "3. Input image: $IMAGE_INPUT_TOPIC"
ros2 topic info "$IMAGE_INPUT_TOPIC" 2>/dev/null || echo "   Not available"
echo ""

echo ""
echo "Monitor options:"
echo "  1) Depth"
echo "  2) Colored depth"
echo "  3) Confidence"
echo "  4) Image input"
echo "  5) Bandwidth"
echo "  6) Exit"

while true; do
    read -p "Choice [1-6]: " choice
    case $choice in
        1) ros2 topic echo "$DEPTH_TOPIC" ;;
        2) ros2 topic echo "$DEPTH_COLORED_TOPIC" ;;
        3) ros2 topic echo "$CONFIDENCE_TOPIC" ;;
        4) ros2 topic hz "$IMAGE_INPUT_TOPIC" ;;
        5) ros2 topic bw "$DEPTH_TOPIC" ;;
        6) break ;;
        *) echo "Invalid" ;;
    esac
    echo ""
done
' &

echo ""
log_header "Demo Running"
log_info ""
log_info "Terminals:"
log_info "  [1] Node + Image Publisher - Main depth estimation"
log_info "  [2] RViz2 - Visualization"
log_info "  [3] Topic Monitor - Message inspection"
log_info "  [4] Parameters - Node configuration"
log_info "  [5] Extra Topics - Colored, confidence"
log_info ""
log_info "Topics:"
log_info "  Depth: $DEPTH_TOPIC"
log_info "  Colored: $DEPTH_COLORED_TOPIC"
log_info "  Confidence: $CONFIDENCE_TOPIC"
log_info ""
log_info "Logs: $LOG_DIR"
log_info "If Terminal 1 crashes: cat ${NODE_LOG}"
log_info ""
log_info "Press Ctrl+C to stop all processes"
echo ""

wait
