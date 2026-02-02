#!/bin/bash
# TensorRT 10.3 Host Validation Test
# Tests if TRT 10.3 can build DA3 engines before Docker rebuild
#
# Expected time: 2-3 minutes
# Location: Run this on Jetson Orin NX host (not in Docker)

set -e

echo "=== TensorRT 10.3 Host Validation ==="
echo ""

# Step 0: Find trtexec
TRTEXEC=""
if [ -x "/usr/src/tensorrt/bin/trtexec" ]; then
    TRTEXEC="/usr/src/tensorrt/bin/trtexec"
elif command -v trtexec &> /dev/null; then
    TRTEXEC=$(command -v trtexec)
else
    echo "ERROR: trtexec not found"
    echo "  Expected at: /usr/src/tensorrt/bin/trtexec"
    echo "  This script must run on Jetson with TensorRT installed"
    exit 1
fi
echo "Using trtexec: $TRTEXEC"
echo ""

# Step 1: Verify TensorRT version
echo "Step 1: Checking TensorRT version..."

# Get raw trtexec output for debugging
TRTEXEC_OUTPUT=$($TRTEXEC --help 2>&1 | head -5)
echo "  trtexec header: $(echo "$TRTEXEC_OUTPUT" | grep -i tensorrt | head -1)"

# TRT 10.x shows version in format: [TensorRT v100300] meaning 10.03.00
# Extract from the help/version output
TRT_VERSION_RAW=$($TRTEXEC --help 2>&1 | grep -oE 'TensorRT v[0-9]+' | head -1 || echo "")
if [ -n "$TRT_VERSION_RAW" ]; then
    # Convert v100300 to 10.3
    VERSION_NUM=$(echo "$TRT_VERSION_RAW" | grep -oE '[0-9]+')
    MAJOR=$((VERSION_NUM / 10000))
    MINOR=$(((VERSION_NUM % 10000) / 100))
    TRT_VERSION="${MAJOR}.${MINOR}"
else
    # Fallback: try direct version extraction
    TRT_VERSION=$($TRTEXEC --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "NOT_FOUND")
fi
echo "  TensorRT version: $TRT_VERSION"

# Default to TRT 10.x syntax if detection fails (we know Jetson has TRT 10.3)
USE_TRT10_SYNTAX=true
if [[ "$TRT_VERSION" =~ ^[89]\. ]]; then
    echo "  Detected TRT 8.x/9.x - using legacy syntax"
    USE_TRT10_SYNTAX=false
elif [[ "$TRT_VERSION" =~ ^10\. ]]; then
    echo "  Detected TRT 10.x - using modern syntax"
else
    echo "  WARNING: Could not detect version, assuming TRT 10.x"
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
echo "  Input: $ONNX_PATH"
echo "  Output: $OUTPUT_ENGINE"
echo ""

# NOTE: TRT 10.x uses --memPoolSize instead of --workspace
# DA3 ONNX model has 5D dynamic input shape - must specify explicitly
# Input tensor name: pixel_values, shape: batch x 1 x channels x height x width
INPUT_SHAPE="pixel_values:1x1x3x518x518"
echo "  Input shape: $INPUT_SHAPE"

if [ "$USE_TRT10_SYNTAX" = true ]; then
    echo "  Using TRT 10.x syntax (--memPoolSize)"
    $TRTEXEC \
        --onnx="$ONNX_PATH" \
        --saveEngine="$OUTPUT_ENGINE" \
        --fp16 \
        --memPoolSize=workspace:2048MiB \
        --optShapes="$INPUT_SHAPE" \
        --verbose 2>&1 | tee /tmp/trtexec_build.log
else
    echo "  Using TRT 8.x syntax (--workspace)"
    $TRTEXEC \
        --onnx="$ONNX_PATH" \
        --saveEngine="$OUTPUT_ENGINE" \
        --fp16 \
        --workspace=2048 \
        --optShapes="$INPUT_SHAPE" \
        --verbose 2>&1 | tee /tmp/trtexec_build.log
fi

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
