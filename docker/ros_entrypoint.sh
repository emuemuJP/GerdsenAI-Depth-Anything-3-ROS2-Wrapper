#!/bin/bash
# ROS2 Docker Entrypoint Script
# This script sources the ROS2 environment and executes the command

set -e

# Source ROS2 environment
source /opt/ros/humble/setup.bash

# Source workspace if it exists
if [ -f /ros2_ws/install/setup.bash ]; then
    source /ros2_ws/install/setup.bash
fi

# TensorRT engine detection and optional on-demand building
# Set DA3_TENSORRT_AUTO=true to enable automatic engine building
if [ "${DA3_TENSORRT_AUTO:-false}" = "true" ]; then
    ENGINE_DIR="/root/.cache/tensorrt"
    ONNX_DIR="/root/.cache/onnx"

    # Check if any .engine files exist
    if [ ! -d "$ENGINE_DIR" ] || [ -z "$(ls -A $ENGINE_DIR/*.engine 2>/dev/null)" ]; then
        echo "[TensorRT] No engines found in $ENGINE_DIR"
        echo "[TensorRT] Building TensorRT engine automatically..."

        # Ensure directories exist
        mkdir -p "$ENGINE_DIR" "$ONNX_DIR"

        # Run the build script with auto-detection
        if [ -f /app/scripts/build_tensorrt_engine.py ]; then
            python3 /app/scripts/build_tensorrt_engine.py \
                --auto \
                --output-dir /root/.cache \
                || echo "[TensorRT] WARNING: Engine build failed, falling back to PyTorch"
        else
            echo "[TensorRT] WARNING: build_tensorrt_engine.py not found"
        fi
    else
        echo "[TensorRT] Found existing engines in $ENGINE_DIR:"
        ls -la "$ENGINE_DIR"/*.engine 2>/dev/null || true
    fi
fi

# Execute the command
exec "$@"
