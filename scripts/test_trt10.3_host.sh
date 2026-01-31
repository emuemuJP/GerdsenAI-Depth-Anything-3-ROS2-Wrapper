#!/bin/bash
# TensorRT 10.3 Host Validation Test
# Tests if TRT 10.3 can build DA3 engines before Docker rebuild
#
# Expected time: 2-3 minutes
# Location: Run this on Jetson Orin NX host (not in Docker)

set -e

echo "=== TensorRT 10.3 Host Validation ==="
echo ""

# Step 1: Verify TensorRT version
echo "Step 1: Checking TensorRT version..."
TRT_VERSION=$(/usr/src/tensorrt/bin/trtexec --version 2>&1 | grep -oP 'TensorRT \K[0-9.]+' || echo "NOT_FOUND")
echo "  TensorRT version: $TRT_VERSION"

if [[ "$TRT_VERSION" != 10.3* ]]; then
    echo "  WARNING: Expected TRT 10.3.x, got $TRT_VERSION"
fi
echo ""

# Step 2: Check for ONNX model
echo "Step 2: Locating ONNX model..."
ONNX_PATH=""

# Check common locations
if [ -f "$HOME/depth_anything_3_ros2/models/onnx/da3-small-embedded.onnx" ]; then
    ONNX_PATH="$HOME/depth_anything_3_ros2/models/onnx/da3-small-embedded.onnx"
elif [ -f "$HOME/.cache/huggingface/hub/models--onnx-community--depth-anything-v3-small/snapshots/*/onnx/model.onnx" ]; then
    ONNX_PATH=$(ls $HOME/.cache/huggingface/hub/models--onnx-community--depth-anything-v3-small/snapshots/*/onnx/model.onnx 2>/dev/null | head -1)
fi

if [ -z "$ONNX_PATH" ]; then
    echo "  ONNX model not found. Downloading..."
    mkdir -p /tmp/onnx_test
    cd /tmp/onnx_test
    
    # Download using huggingface-cli if available
    if command -v huggingface-cli &> /dev/null; then
        huggingface-cli download onnx-community/depth-anything-v3-small --include "onnx/model.onnx" --local-dir .
        ONNX_PATH="/tmp/onnx_test/onnx/model.onnx"
    else
        echo "  ERROR: huggingface-cli not found. Install with: pip3 install huggingface_hub"
        echo "  Alternative: Manually download from https://huggingface.co/onnx-community/depth-anything-v3-small"
        exit 1
    fi
fi

echo "  ONNX model: $ONNX_PATH"
echo "  File size: $(du -h "$ONNX_PATH" | cut -f1)"
echo ""

# Step 3: Test TensorRT engine build
echo "Step 3: Building TensorRT engine (this may take 1-2 minutes)..."
OUTPUT_ENGINE="/tmp/da3-trt10.3-test.engine"

echo "  Running trtexec..."
# NOTE: TRT 10.x uses --memPoolSize instead of --workspace
/usr/src/tensorrt/bin/trtexec \
    --onnx="$ONNX_PATH" \
    --saveEngine="$OUTPUT_ENGINE" \
    --fp16 \
    --memPoolSize=workspace:2048MiB \
    --verbose 2>&1 | tee /tmp/trtexec_build.log

# Check for success
echo ""
if [ -f "$OUTPUT_ENGINE" ]; then
    ENGINE_SIZE=$(du -h "$OUTPUT_ENGINE" | cut -f1)
    echo "=== SUCCESS ==="
    echo "  Engine built: $OUTPUT_ENGINE"
    echo "  Engine size: $ENGINE_SIZE"
    echo ""
    echo "CONCLUSION: TensorRT 10.3 CAN build DA3 engines!"
    echo "  -> Safe to rebuild Docker image with L4T r36.4.0"
    echo "  -> Expected FPS: 20-30 at 518x518, 30-40 at 308x308"
    echo ""
    
    # Check for warnings in build log
    if grep -q "fallback" /tmp/trtexec_build.log; then
        echo "NOTE: Some operations may have CPU fallback (check /tmp/trtexec_build.log)"
    fi
    
    exit 0
else
    echo "=== FAILURE ==="
    echo "  Engine build failed"
    echo "  Check /tmp/trtexec_build.log for errors"
    echo ""
    
    # Check for specific errors
    if grep -q "caskConvolutionV2Forward" /tmp/trtexec_build.log; then
        echo "ERROR: caskConvolutionV2Forward error detected"
        echo "  -> TRT 10.3 still has DINOv2 compatibility issues"
    fi
    
    if grep -q "Einsum" /tmp/trtexec_build.log; then
        echo "ERROR: Einsum operator not supported"
        echo "  -> TRT 10.3 lacks required Einsum features"
    fi
    
    echo ""
    echo "CONCLUSION: TensorRT 10.3 CANNOT build DA3 engines"
    echo "  -> Do NOT rebuild Docker image"
    echo "  -> Fallback options:"
    echo "     1. Use ONNX Runtime with CUDA EP (hybrid execution)"
    echo "     2. Use Depth Anything V2 (proven TRT 8.6 support)"
    echo "     3. Wait for JetPack with TRT 10.8+"
    echo ""
    
    exit 1
fi
