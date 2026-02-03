#!/bin/bash
# Phase 4: Thermal and Stability Validation
# Runs sustained TRT inference while monitoring GPU temperature and FPS stability
#
# Usage: bash scripts/thermal_stability_test.sh [duration_minutes] [resolution]
#   Default: 10 minutes, 518x518

set -e

DURATION_MIN=${1:-10}
RESOLUTION=${2:-518}
DURATION_SEC=$((DURATION_MIN * 60))

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

TRTEXEC="/usr/src/tensorrt/bin/trtexec"
ENGINE="models/tensorrt/da3-small-fp16-${RESOLUTION}.engine"
LOG_DIR="logs/thermal_test_$(date +%Y%m%d_%H%M%S)"
TEMP_LOG="$LOG_DIR/temperature.csv"
FPS_LOG="$LOG_DIR/fps.csv"
SUMMARY="$LOG_DIR/summary.txt"

mkdir -p "$LOG_DIR"

echo "========================================"
echo "Phase 4: Thermal/Stability Validation"
echo "========================================"
echo ""
echo "Configuration:"
echo "  Duration: ${DURATION_MIN} minutes"
echo "  Resolution: ${RESOLUTION}x${RESOLUTION}"
echo "  Engine: $ENGINE"
echo "  Log directory: $LOG_DIR"
echo ""

if [ ! -f "$ENGINE" ]; then
    echo "ERROR: Engine not found: $ENGINE"
    echo "Run deploy_jetson.sh or benchmark scripts first."
    exit 1
fi

# Initialize CSV headers
echo "timestamp,elapsed_sec,gpu_temp_c,cpu_temp_c,power_mw" > "$TEMP_LOG"
echo "timestamp,elapsed_sec,throughput_fps,latency_mean_ms,latency_p99_ms" > "$FPS_LOG"

# Function to get GPU temperature
get_gpu_temp() {
    cat /sys/devices/gpu.0/hwmon/hwmon*/temp1_input 2>/dev/null | awk '{print $1/1000}' || echo "N/A"
}

# Function to get CPU temperature
get_cpu_temp() {
    cat /sys/devices/virtual/thermal/thermal_zone*/temp 2>/dev/null | head -1 | awk '{print $1/1000}' || echo "N/A"
}

# Function to get power consumption
get_power() {
    cat /sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon*/in*_input 2>/dev/null | head -1 || echo "N/A"
}

echo "Starting temperature monitor in background..."
START_TIME=$(date +%s)

# Background temperature monitoring (every 5 seconds)
(
    while true; do
        NOW=$(date +%s)
        ELAPSED=$((NOW - START_TIME))
        if [ $ELAPSED -ge $DURATION_SEC ]; then
            break
        fi

        TIMESTAMP=$(date +%H:%M:%S)
        GPU_TEMP=$(get_gpu_temp)
        CPU_TEMP=$(get_cpu_temp)
        POWER=$(get_power)

        echo "$TIMESTAMP,$ELAPSED,$GPU_TEMP,$CPU_TEMP,$POWER" >> "$TEMP_LOG"
        sleep 5
    done
) &
TEMP_PID=$!

echo "Starting sustained inference test..."
echo ""
echo "Progress:"

# Run inference in batches and log FPS
BATCH_ITERATIONS=500
BATCH_WARMUP=1000
BATCHES=$((DURATION_SEC / 15))  # Roughly 15 sec per batch

for i in $(seq 1 $BATCHES); do
    NOW=$(date +%s)
    ELAPSED=$((NOW - START_TIME))

    if [ $ELAPSED -ge $DURATION_SEC ]; then
        break
    fi

    REMAINING=$((DURATION_SEC - ELAPSED))
    PROGRESS=$((ELAPSED * 100 / DURATION_SEC))

    # Get current temperature
    GPU_TEMP=$(get_gpu_temp)

    echo -ne "\r  [$PROGRESS%] Elapsed: ${ELAPSED}s | Remaining: ${REMAINING}s | GPU: ${GPU_TEMP}C    "

    # Run benchmark batch
    RESULT=$($TRTEXEC --loadEngine="$ENGINE" --iterations=$BATCH_ITERATIONS --warmUp=$BATCH_WARMUP 2>&1)

    # Parse results
    THROUGHPUT=$(echo "$RESULT" | grep "Throughput:" | awk '{print $2}')
    LATENCY_MEAN=$(echo "$RESULT" | grep "Latency:" | grep -oP 'mean = \K[0-9.]+')
    LATENCY_P99=$(echo "$RESULT" | grep "Latency:" | grep -oP 'percentile\(99%\) = \K[0-9.]+')

    TIMESTAMP=$(date +%H:%M:%S)
    echo "$TIMESTAMP,$ELAPSED,$THROUGHPUT,$LATENCY_MEAN,$LATENCY_P99" >> "$FPS_LOG"
done

echo ""
echo ""
echo "Stopping temperature monitor..."
kill $TEMP_PID 2>/dev/null || true
wait $TEMP_PID 2>/dev/null || true

# Generate summary
echo "========================================"
echo "Generating Summary"
echo "========================================"

{
    echo "Thermal/Stability Test Summary"
    echo "=============================="
    echo ""
    echo "Test Configuration:"
    echo "  Duration: ${DURATION_MIN} minutes"
    echo "  Resolution: ${RESOLUTION}x${RESOLUTION}"
    echo "  Engine: $ENGINE"
    echo "  Date: $(date)"
    echo ""

    # Temperature stats
    echo "Temperature Statistics:"
    if [ -f "$TEMP_LOG" ] && [ $(wc -l < "$TEMP_LOG") -gt 1 ]; then
        GPU_TEMPS=$(tail -n +2 "$TEMP_LOG" | cut -d',' -f3 | grep -v "N/A")
        if [ -n "$GPU_TEMPS" ]; then
            GPU_MIN=$(echo "$GPU_TEMPS" | sort -n | head -1)
            GPU_MAX=$(echo "$GPU_TEMPS" | sort -n | tail -1)
            GPU_AVG=$(echo "$GPU_TEMPS" | awk '{sum+=$1; count++} END {printf "%.1f", sum/count}')
            echo "  GPU Temp: min=${GPU_MIN}C, max=${GPU_MAX}C, avg=${GPU_AVG}C"

            # Check if stayed under 80C
            if (( $(echo "$GPU_MAX < 80" | bc -l) )); then
                echo "  Status: PASS (stayed under 80C target)"
            else
                echo "  Status: WARNING (exceeded 80C target)"
            fi
        fi
    fi
    echo ""

    # FPS stats
    echo "Performance Statistics:"
    if [ -f "$FPS_LOG" ] && [ $(wc -l < "$FPS_LOG") -gt 1 ]; then
        FPS_VALUES=$(tail -n +2 "$FPS_LOG" | cut -d',' -f3 | grep -v "^$")
        if [ -n "$FPS_VALUES" ]; then
            FPS_MIN=$(echo "$FPS_VALUES" | sort -n | head -1)
            FPS_MAX=$(echo "$FPS_VALUES" | sort -n | tail -1)
            FPS_AVG=$(echo "$FPS_VALUES" | awk '{sum+=$1; count++} END {printf "%.2f", sum/count}')
            FPS_STDDEV=$(echo "$FPS_VALUES" | awk -v avg="$FPS_AVG" '{sum+=($1-avg)^2; count++} END {printf "%.2f", sqrt(sum/count)}')

            echo "  Throughput: min=${FPS_MIN} FPS, max=${FPS_MAX} FPS, avg=${FPS_AVG} FPS"
            echo "  Stability (stddev): ${FPS_STDDEV} FPS"

            # Check stability (stddev < 5% of mean)
            THRESHOLD=$(echo "$FPS_AVG * 0.05" | bc -l)
            if (( $(echo "$FPS_STDDEV < $THRESHOLD" | bc -l) )); then
                echo "  Status: PASS (stable, stddev < 5% of mean)"
            else
                echo "  Status: WARNING (variable performance)"
            fi
        fi

        LATENCY_VALUES=$(tail -n +2 "$FPS_LOG" | cut -d',' -f4 | grep -v "^$")
        if [ -n "$LATENCY_VALUES" ]; then
            LAT_AVG=$(echo "$LATENCY_VALUES" | awk '{sum+=$1; count++} END {printf "%.2f", sum/count}')
            echo "  Latency (mean): ${LAT_AVG} ms"
        fi
    fi
    echo ""

    echo "Log Files:"
    echo "  Temperature: $TEMP_LOG"
    echo "  FPS: $FPS_LOG"
    echo ""
    echo "=============================="

} | tee "$SUMMARY"

echo ""
echo "Full results saved to: $LOG_DIR"
