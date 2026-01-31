#!/bin/bash
# Depth Anything V3 - Camera Detection Script
# Detects available cameras (USB, CSI) on Jetson/Linux systems
#
# Usage: bash scripts/detect_cameras.sh [options]
#
# Options:
#   --json          Output in JSON format
#   --quiet         Only output device paths (for scripting)
#   --first         Return only the first detected camera
#
# Output (default): Human-readable list of cameras
# Output (--json):  JSON array with camera details

set -e

# Colors (disabled if not a terminal)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    NC='\033[0m'
else
    GREEN=''
    YELLOW=''
    CYAN=''
    NC=''
fi

# Parse arguments
JSON_OUTPUT=false
QUIET=false
FIRST_ONLY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --json) JSON_OUTPUT=true; shift ;;
        --quiet|-q) QUIET=true; shift ;;
        --first) FIRST_ONLY=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--json|--quiet|--first]"
            echo ""
            echo "Detects available cameras (USB, CSI) on the system."
            echo ""
            echo "Options:"
            echo "  --json    Output in JSON format"
            echo "  --quiet   Only output device paths"
            echo "  --first   Return only first detected camera"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Arrays to store detected cameras
declare -a CAMERA_DEVICES=()
declare -a CAMERA_NAMES=()
declare -a CAMERA_TYPES=()
declare -a CAMERA_TOPICS=()

# Function: Detect USB cameras via /dev/video*
detect_usb_cameras() {
    for dev in /dev/video*; do
        if [ ! -e "$dev" ]; then
            continue
        fi

        # Check if this is a video capture device (not metadata)
        if command -v v4l2-ctl &> /dev/null; then
            # Get device capabilities
            caps=$(v4l2-ctl --device="$dev" --all 2>/dev/null || true)

            # Skip if not a video capture device
            if ! echo "$caps" | grep -q "Video Capture"; then
                continue
            fi

            # Skip metadata devices (common with USB webcams)
            if echo "$caps" | grep -q "Metadata Capture"; then
                continue
            fi

            # Get device name
            name=$(echo "$caps" | grep "Card type" | sed 's/.*Card type.*: //' | head -1)
            if [ -z "$name" ]; then
                name="Unknown USB Camera"
            fi

            # Get driver name
            driver=$(echo "$caps" | grep "Driver name" | sed 's/.*Driver name.*: //' | head -1)
        else
            # Fallback: just check if device exists and is readable
            if [ ! -r "$dev" ]; then
                continue
            fi
            name="USB Camera (v4l2-ctl not available)"
            driver="unknown"
        fi

        # Add to arrays
        CAMERA_DEVICES+=("$dev")
        CAMERA_NAMES+=("$name")
        CAMERA_TYPES+=("usb")
        CAMERA_TOPICS+=("/camera/image_raw")
    done
}

# Function: Detect CSI cameras (Jetson-specific)
detect_csi_cameras() {
    # Check for NVIDIA Argus camera source (CSI cameras on Jetson)
    if command -v gst-inspect-1.0 &> /dev/null; then
        if gst-inspect-1.0 nvarguscamerasrc &> /dev/null; then
            # nvarguscamerasrc is available - CSI camera likely connected
            # Try to detect which sensor IDs are available
            for sensor_id in 0 1; do
                # Quick test if camera responds (timeout after 1 second)
                if timeout 2 gst-launch-1.0 nvarguscamerasrc sensor-id=$sensor_id num-buffers=1 ! fakesink 2>/dev/null; then
                    CAMERA_DEVICES+=("csi:$sensor_id")
                    CAMERA_NAMES+=("CSI Camera (sensor $sensor_id)")
                    CAMERA_TYPES+=("csi")
                    CAMERA_TOPICS+=("/csi_cam_$sensor_id/image_raw")
                fi
            done
        fi
    fi

    # Also check device tree for camera nodes (alternative detection)
    if [ -d "/proc/device-tree" ]; then
        for cam_node in /proc/device-tree/cam*/; do
            if [ -d "$cam_node" ]; then
                # Found camera node in device tree
                cam_name=$(cat "$cam_node/name" 2>/dev/null || echo "CSI Camera")
                # Only add if not already detected via nvarguscamerasrc
                if ! printf '%s\n' "${CAMERA_DEVICES[@]}" | grep -q "^csi:"; then
                    CAMERA_DEVICES+=("csi:dt")
                    CAMERA_NAMES+=("$cam_name (device tree)")
                    CAMERA_TYPES+=("csi")
                    CAMERA_TOPICS+=("/csi_cam/image_raw")
                fi
                break  # Only add once
            fi
        done
    fi
}

# Function: Detect RealSense cameras
detect_realsense_cameras() {
    # Check if realsense2 library is available
    if command -v rs-enumerate-devices &> /dev/null; then
        if rs-enumerate-devices 2>/dev/null | grep -q "Intel RealSense"; then
            CAMERA_DEVICES+=("realsense:0")
            CAMERA_NAMES+=("Intel RealSense")
            CAMERA_TYPES+=("realsense")
            CAMERA_TOPICS+=("/camera/camera/color/image_raw")
        fi
    fi
}

# Run detection
detect_usb_cameras
detect_csi_cameras
detect_realsense_cameras

# Count detected cameras
num_cameras=${#CAMERA_DEVICES[@]}

# Output based on format
if [ "$JSON_OUTPUT" = true ]; then
    # JSON output
    echo "["
    for i in "${!CAMERA_DEVICES[@]}"; do
        comma=""
        if [ $i -lt $((num_cameras - 1)) ]; then
            comma=","
        fi
        if [ "$FIRST_ONLY" = true ] && [ $i -gt 0 ]; then
            break
        fi
        cat << EOF
  {
    "device": "${CAMERA_DEVICES[$i]}",
    "name": "${CAMERA_NAMES[$i]}",
    "type": "${CAMERA_TYPES[$i]}",
    "topic": "${CAMERA_TOPICS[$i]}"
  }$comma
EOF
    done
    echo "]"
elif [ "$QUIET" = true ]; then
    # Quiet output - just device paths
    for dev in "${CAMERA_DEVICES[@]}"; do
        echo "$dev"
        if [ "$FIRST_ONLY" = true ]; then
            break
        fi
    done
else
    # Human-readable output
    if [ $num_cameras -eq 0 ]; then
        echo -e "${YELLOW}No cameras detected${NC}"
        echo ""
        echo "Tips:"
        echo "  - Connect a USB camera and try again"
        echo "  - For CSI cameras, ensure camera module is connected"
        echo "  - Install v4l2-utils: sudo apt install v4l2-utils"
        exit 1
    fi

    echo -e "${GREEN}Detected $num_cameras camera(s):${NC}"
    echo ""
    for i in "${!CAMERA_DEVICES[@]}"; do
        if [ "$FIRST_ONLY" = true ] && [ $i -gt 0 ]; then
            break
        fi
        echo -e "  ${CYAN}[$i]${NC} ${CAMERA_NAMES[$i]}"
        echo "      Device: ${CAMERA_DEVICES[$i]}"
        echo "      Type:   ${CAMERA_TYPES[$i]}"
        echo "      Topic:  ${CAMERA_TOPICS[$i]}"
        echo ""
    done
fi

exit 0
