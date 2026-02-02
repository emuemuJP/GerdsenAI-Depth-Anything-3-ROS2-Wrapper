#!/bin/bash
# Depth Anything V3 - Performance Monitor
# Terminal-based live display of inference metrics
#
# Usage: bash scripts/performance_monitor.sh [options]
#
# Options:
#   --interval SEC    Update interval in seconds (default: 1)
#   --no-color        Disable colored output
#   --once            Print once and exit (no loop)

set -e

# Configuration
SHARED_DIR="/tmp/da3_shared"
UPDATE_INTERVAL=1
USE_COLOR=true
RUN_ONCE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --interval)
            UPDATE_INTERVAL="$2"
            shift 2
            ;;
        --no-color)
            USE_COLOR=false
            shift
            ;;
        --once)
            RUN_ONCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--interval SEC] [--no-color] [--once]"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# Colors
if [ "$USE_COLOR" = true ] && [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    CYAN=''
    BOLD=''
    DIM=''
    NC=''
fi

# Function: Get TRT service stats
get_trt_stats() {
    local status_file="$SHARED_DIR/status"
    local stats_file="$SHARED_DIR/stats"

    TRT_STATUS="Not Running"
    TRT_FPS="--"
    TRT_LATENCY="--"
    TRT_FRAMES="--"

    if [ -f "$status_file" ]; then
        TRT_STATUS=$(cat "$status_file" 2>/dev/null | head -1 || echo "Unknown")
    fi

    if [ -f "$stats_file" ]; then
        # Parse stats file (format: fps,latency_ms,frames)
        local stats=$(cat "$stats_file" 2>/dev/null || echo "")
        if [ -n "$stats" ]; then
            TRT_FPS=$(echo "$stats" | cut -d',' -f1 2>/dev/null || echo "--")
            TRT_LATENCY=$(echo "$stats" | cut -d',' -f2 2>/dev/null || echo "--")
            TRT_FRAMES=$(echo "$stats" | cut -d',' -f3 2>/dev/null || echo "--")
        fi
    fi
}

# Function: Get GPU stats (Jetson tegrastats or nvidia-smi)
get_gpu_stats() {
    GPU_USAGE="--"
    GPU_MEM_USED="--"
    GPU_MEM_TOTAL="--"
    GPU_TEMP="--"

    if command -v tegrastats &> /dev/null; then
        # Jetson: Use tegrastats
        local teg_output=$(timeout 0.5 tegrastats --interval 100 2>/dev/null | head -1 || echo "")
        if [ -n "$teg_output" ]; then
            # Parse GPU usage (GR3D_FREQ X%@freq)
            GPU_USAGE=$(echo "$teg_output" | grep -oP 'GR3D_FREQ \K[0-9]+' || echo "--")

            # Parse RAM (RAM XXXX/YYYY MB)
            local ram_info=$(echo "$teg_output" | grep -oP 'RAM \K[0-9]+/[0-9]+' || echo "")
            if [ -n "$ram_info" ]; then
                GPU_MEM_USED=$(echo "$ram_info" | cut -d'/' -f1)
                GPU_MEM_TOTAL=$(echo "$ram_info" | cut -d'/' -f2)
            fi

            # Parse temperature (GPU@XXC or gpu@XXC)
            GPU_TEMP=$(echo "$teg_output" | grep -oiP '(GPU|gpu)@\K[0-9.]+' || echo "--")
        fi
    elif command -v nvidia-smi &> /dev/null; then
        # x86: Use nvidia-smi
        local smi_output=$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "")
        if [ -n "$smi_output" ]; then
            GPU_USAGE=$(echo "$smi_output" | cut -d',' -f1 | tr -d ' ')
            GPU_MEM_USED=$(echo "$smi_output" | cut -d',' -f2 | tr -d ' ')
            GPU_MEM_TOTAL=$(echo "$smi_output" | cut -d',' -f3 | tr -d ' ')
            GPU_TEMP=$(echo "$smi_output" | cut -d',' -f4 | tr -d ' ')
        fi
    fi
}

# Function: Get ROS2 topic stats
get_ros2_stats() {
    ROS2_DEPTH_HZ="--"
    ROS2_INPUT_HZ="--"

    # Check if ROS2 is available
    if ! command -v ros2 &> /dev/null; then
        return
    fi

    # Source ROS2 if needed
    if [ -f "/opt/ros/humble/setup.bash" ] && [ -z "$ROS_DISTRO" ]; then
        source /opt/ros/humble/setup.bash 2>/dev/null || true
    fi

    # Try to get topic hz (with timeout)
    local depth_hz=$(timeout 2 ros2 topic hz /camera/depth_anything_3/depth --window 5 2>/dev/null | grep "average rate" | head -1 | grep -oP '[0-9.]+' | head -1 || echo "")
    if [ -n "$depth_hz" ]; then
        ROS2_DEPTH_HZ="$depth_hz"
    fi
}

# Function: Display stats
display_stats() {
    # Clear screen (or just print newlines in RUN_ONCE mode)
    if [ "$RUN_ONCE" = false ]; then
        clear
    fi

    echo ""
    echo -e "${BOLD}========================================${NC}"
    echo -e "${BOLD}  Depth Anything V3 - Performance      ${NC}"
    echo -e "${BOLD}========================================${NC}"
    echo ""

    # TRT Service Status
    echo -e "${CYAN}TensorRT Inference Service${NC}"
    echo "----------------------------------------"
    if [ "$TRT_STATUS" = "ready" ] || [ "$TRT_STATUS" = "complete" ]; then
        echo -e "  Status:     ${GREEN}Running${NC}"
    elif [ "$TRT_STATUS" = "processing" ]; then
        echo -e "  Status:     ${YELLOW}Processing${NC}"
    else
        echo -e "  Status:     ${RED}$TRT_STATUS${NC}"
    fi

    # Format FPS with color
    if [ "$TRT_FPS" != "--" ] && [ -n "$TRT_FPS" ]; then
        fps_val=$(printf "%.1f" "$TRT_FPS" 2>/dev/null || echo "$TRT_FPS")
        if (( $(echo "$TRT_FPS > 30" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "  FPS:        ${GREEN}$fps_val${NC}"
        elif (( $(echo "$TRT_FPS > 15" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "  FPS:        ${YELLOW}$fps_val${NC}"
        else
            echo -e "  FPS:        ${RED}$fps_val${NC}"
        fi
    else
        echo -e "  FPS:        ${DIM}--${NC}"
    fi

    # Format latency
    if [ "$TRT_LATENCY" != "--" ] && [ -n "$TRT_LATENCY" ]; then
        lat_val=$(printf "%.1f ms" "$TRT_LATENCY" 2>/dev/null || echo "$TRT_LATENCY ms")
        echo -e "  Latency:    $lat_val"
    else
        echo -e "  Latency:    ${DIM}--${NC}"
    fi

    echo -e "  Frames:     ${TRT_FRAMES:-0}"
    echo ""

    # GPU Stats
    echo -e "${CYAN}GPU Resources${NC}"
    echo "----------------------------------------"
    if [ "$GPU_USAGE" != "--" ]; then
        echo -e "  GPU Usage:  ${GPU_USAGE}%"
    else
        echo -e "  GPU Usage:  ${DIM}--${NC}"
    fi

    if [ "$GPU_MEM_USED" != "--" ] && [ "$GPU_MEM_TOTAL" != "--" ]; then
        echo -e "  GPU Memory: ${GPU_MEM_USED} / ${GPU_MEM_TOTAL} MB"
    else
        echo -e "  GPU Memory: ${DIM}--${NC}"
    fi

    if [ "$GPU_TEMP" != "--" ]; then
        if (( $(echo "$GPU_TEMP > 80" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "  GPU Temp:   ${RED}${GPU_TEMP}C${NC}"
        elif (( $(echo "$GPU_TEMP > 60" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "  GPU Temp:   ${YELLOW}${GPU_TEMP}C${NC}"
        else
            echo -e "  GPU Temp:   ${GREEN}${GPU_TEMP}C${NC}"
        fi
    else
        echo -e "  GPU Temp:   ${DIM}--${NC}"
    fi
    echo ""

    # ROS2 Stats (if available)
    if [ "$ROS2_DEPTH_HZ" != "--" ]; then
        echo -e "${CYAN}ROS2 Topics${NC}"
        echo "----------------------------------------"
        echo -e "  Depth Hz:   $ROS2_DEPTH_HZ"
        echo ""
    fi

    # Footer
    echo "----------------------------------------"
    echo -e "${DIM}Updated: $(date '+%H:%M:%S')${NC}"
    if [ "$RUN_ONCE" = false ]; then
        echo -e "${DIM}Press Ctrl+C to exit${NC}"
    fi
    echo ""
}

# Main loop
echo "Starting performance monitor..."
echo "Shared directory: $SHARED_DIR"
echo ""

while true; do
    get_trt_stats
    get_gpu_stats
    # Skip ROS2 stats for now (can be slow)
    # get_ros2_stats

    display_stats

    if [ "$RUN_ONCE" = true ]; then
        break
    fi

    sleep "$UPDATE_INTERVAL"
done
