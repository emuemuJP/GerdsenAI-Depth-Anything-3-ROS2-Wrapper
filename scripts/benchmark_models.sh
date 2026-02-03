#!/bin/bash
# Benchmark different DA3 model sizes
# Tests: small, base, large at 518x518
#
# Usage: bash scripts/benchmark_models.sh [small|base|large|all]
#   Default: tests all models

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

export PATH="$HOME/.local/bin:$PATH"

ONNX_DIR="models/onnx"
TRT_DIR="models/tensorrt"
TRTEXEC="/usr/src/tensorrt/bin/trtexec"

# Parse argument
MODEL_TO_TEST="${1:-all}"

echo "========================================"
echo "DA3 Model Size Benchmark"
echo "========================================"
echo ""

mkdir -p "$ONNX_DIR" "$TRT_DIR"

# Function to download and build a model
benchmark_model() {
    local MODEL_SIZE=$1  # small, base, or large
    local HF_REPO="onnx-community/depth-anything-v3-${MODEL_SIZE}"
    local ONNX_MODEL="$ONNX_DIR/da3-${MODEL_SIZE}-embedded.onnx"
    local ENGINE="$TRT_DIR/da3-${MODEL_SIZE}-fp16-518.engine"

    echo "=== Testing DA3-${MODEL_SIZE^^} (518x518) ==="

    # Download ONNX model if needed
    if [ ! -f "$ONNX_MODEL" ]; then
        echo "Downloading DA3-${MODEL_SIZE^^} ONNX model..."

        # Auto-install dependencies if needed
        python3 -c "import huggingface_hub" 2>/dev/null || {
            echo "  Installing huggingface_hub..."
            pip3 install huggingface_hub 2>&1 | tail -1
        }

        python3 -c "import onnx" 2>/dev/null || {
            echo "  Installing onnx..."
            pip3 install onnx 2>&1 | tail -1
        }

        python3 << PYEOF
import os
from huggingface_hub import snapshot_download
import onnx

onnx_dir = "models/onnx"
hf_download_dir = os.path.join(onnx_dir, "hf-download-${MODEL_SIZE}")
output_model = "${ONNX_MODEL}"

print("  Downloading from HuggingFace: ${HF_REPO}")
snapshot_download(
    repo_id="${HF_REPO}",
    local_dir=hf_download_dir,
    allow_patterns=["*.onnx", "*.onnx_data"]
)

print("  Embedding weights into single ONNX file...")
model_path = os.path.join(hf_download_dir, "onnx", "model.onnx")
model = onnx.load(model_path)
onnx.save(model, output_model, save_as_external_data=False)
print(f"  Created: {output_model}")
PYEOF

        if [ $? -ne 0 ]; then
            echo "ERROR: Failed to download DA3-${MODEL_SIZE^^} model"
            return 1
        fi
    fi

    ONNX_SIZE=$(du -h "$ONNX_MODEL" 2>/dev/null | cut -f1 || echo "N/A")
    echo "  ONNX model: $ONNX_MODEL ($ONNX_SIZE)"

    # Build TensorRT engine if needed
    if [ ! -f "$ENGINE" ]; then
        echo ""
        echo "Building TensorRT engine for DA3-${MODEL_SIZE^^}..."
        echo "  (Large models may take 5-10 minutes)"
        $TRTEXEC \
            --onnx="$ONNX_MODEL" \
            --saveEngine="$ENGINE" \
            --fp16 \
            --memPoolSize=workspace:2048MiB \
            --optShapes=pixel_values:1x1x3x518x518 \
            2>&1 | tee /tmp/trtexec_${MODEL_SIZE}_build.log | grep -E "(Building|Serializing|SUCCESS|ERROR|Throughput)"

        if [ ! -f "$ENGINE" ]; then
            echo "ERROR: Failed to build DA3-${MODEL_SIZE^^} engine"
            echo "Check /tmp/trtexec_${MODEL_SIZE}_build.log for details"
            return 1
        fi
    fi

    ENGINE_SIZE=$(du -h "$ENGINE" 2>/dev/null | cut -f1 || echo "N/A")
    echo "  Engine: $ENGINE ($ENGINE_SIZE)"

    echo ""
    echo "Benchmarking DA3-${MODEL_SIZE^^}..."
    $TRTEXEC --loadEngine="$ENGINE" --iterations=100 --warmUp=2000 2>&1 | grep -E "(mean|median|Throughput)"
    echo ""
}

# Run benchmarks based on argument
case "$MODEL_TO_TEST" in
    small)
        benchmark_model "small"
        ;;
    base)
        benchmark_model "base"
        ;;
    large)
        benchmark_model "large"
        ;;
    all)
        benchmark_model "small"
        benchmark_model "base"
        benchmark_model "large"
        ;;
    *)
        echo "Usage: $0 [small|base|large|all]"
        exit 1
        ;;
esac

echo "========================================"
echo "Model Size Comparison Summary"
echo "========================================"

# Show all engine sizes
echo ""
echo "Engine Files:"
ls -lh $TRT_DIR/da3-*-fp16-518.engine 2>/dev/null | awk '{print "  "$9": "$5}' || echo "  No engines found"

echo ""
echo "Model Size Reference:"
echo "  Small: ~24M params, fastest inference"
echo "  Base:  ~97M params, balanced"
echo "  Large: ~335M params, highest quality"
