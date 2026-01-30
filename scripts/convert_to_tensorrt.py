#!/usr/bin/env python3
"""
Convert Depth Anything 3 models to TensorRT (Legacy torch2trt approach)

NOTE: This script uses torch2trt which may fail due to Issue #22 (ONNX export failure).
For production use, prefer the pre-exported ONNX approach:

    python scripts/build_tensorrt_engine.py --auto

This builds TensorRT engines from pre-exported ONNX models, bypassing the export issue.

Legacy Requirements:
    - torch2trt: pip install torch2trt
    - NVIDIA JetPack 6.x (includes TensorRT)

Legacy Usage (may fail - use build_tensorrt_engine.py instead):
    # Convert DA3-SMALL to INT8 (fastest)
    python3 convert_to_tensorrt.py \
        --model depth-anything/DA3-SMALL \
        --output models/da3_small_int8.pth \
        --precision int8 \
        --input-size 384 384

    # Convert DA3-BASE to FP16 (good balance)
    python3 convert_to_tensorrt.py \
        --model depth-anything/DA3-BASE \
        --output models/da3_base_fp16.pth \
        --precision fp16 \
        --input-size 518 518

RECOMMENDED: Use the new ONNX-based approach instead:
    python scripts/build_tensorrt_engine.py --model da3-small --precision fp16
"""

import argparse
import sys
import time
from pathlib import Path
import json

import torch
import numpy as np


def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import torch2trt
    except ImportError:
        print("ERROR: torch2trt not installed")
        print("Install with: pip install torch2trt")
        print("See: https://github.com/NVIDIA-AI-IOT/torch2trt")
        sys.exit(1)

    if not torch.cuda.is_available():
        print("ERROR: CUDA not available")
        print("TensorRT conversion requires CUDA")
        sys.exit(1)

    try:
        from depth_anything_3.api import DepthAnything3
    except ImportError:
        print("ERROR: Depth Anything 3 not installed")
        print("Install with: pip install git+https://github.com/ByteDance-Seed/Depth-Anything-3.git")
        sys.exit(1)


def load_da3_model(model_name: str):
    """Load DA3 model."""
    from depth_anything_3.api import DepthAnything3

    print(f"\nLoading model: {model_name}")
    model = DepthAnything3.from_pretrained(model_name)
    model = model.cuda()
    model.eval()
    print("Model loaded successfully")

    return model


def convert_to_tensorrt(
    model,
    input_size,
    precision: str,
    calibration_images=None
):
    """
    Convert model to TensorRT.

    Args:
        model: PyTorch model
        input_size: (H, W) input size
        precision: 'fp32', 'fp16', or 'int8'
        calibration_images: Images for INT8 calibration
    """
    from torch2trt import torch2trt

    print(f"\nConverting to TensorRT ({precision})...")
    print(f"Input size: {input_size}")

    # Create example input
    h, w = input_size
    x = torch.randn(1, 3, h, w).cuda()

    # Set precision flags
    fp16_mode = (precision == 'fp16')
    int8_mode = (precision == 'int8')

    # INT8 calibration setup
    int8_calib_dataset = None
    int8_calib_batch_size = 1

    if int8_mode and calibration_images is not None:
        print(f"Using {len(calibration_images)} calibration images for INT8")
        # Prepare calibration dataset
        int8_calib_dataset = calibration_images
        int8_calib_batch_size = 1

    print("Converting... (this may take several minutes)")
    start_time = time.time()

    try:
        model_trt = torch2trt(
            model,
            [x],
            fp16_mode=fp16_mode,
            int8_mode=int8_mode,
            int8_calib_dataset=int8_calib_dataset,
            int8_calib_batch_size=int8_calib_batch_size,
            max_workspace_size=(1 << 30),  # 1GB
            max_batch_size=1,
        )

        conversion_time = time.time() - start_time
        print(f"Conversion completed in {conversion_time:.2f}s")

        return model_trt

    except Exception as e:
        print(f"ERROR: Conversion failed: {e}")
        sys.exit(1)


def save_tensorrt_model(model_trt, output_path: Path, metadata: dict):
    """Save TensorRT model and metadata."""
    print(f"\nSaving model to: {output_path}")

    # Create output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save model
    torch.save(model_trt.state_dict(), output_path)
    print("Model saved")

    # Save metadata
    metadata_path = output_path.with_suffix('.json')
    try:
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"Metadata saved to: {metadata_path}")
    except OSError as e:
        print(f"WARNING: Failed to save metadata: {e}")


def benchmark_model(model, input_size, iterations=100, warmup=10):
    """Benchmark model performance."""
    print(f"\nBenchmarking ({iterations} iterations)...")

    h, w = input_size
    x = torch.randn(1, 3, h, w).cuda()

    # Warmup
    print(f"Warmup ({warmup} iterations)...")
    with torch.no_grad():
        for _ in range(warmup):
            _ = model(x)

    torch.cuda.synchronize()

    # Benchmark
    times = []
    with torch.no_grad():
        for i in range(iterations):
            start = time.time()
            _ = model(x)
            torch.cuda.synchronize()
            end = time.time()
            times.append(end - start)

            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{iterations} iterations")

    # Calculate statistics
    times = np.array(times)
    mean_ms = np.mean(times) * 1000
    std_ms = np.std(times) * 1000
    min_ms = np.min(times) * 1000
    max_ms = np.max(times) * 1000
    fps = 1.0 / np.mean(times)

    print("\nBenchmark Results:")
    print(f"  Mean: {mean_ms:.2f} ms")
    print(f"  Std:  {std_ms:.2f} ms")
    print(f"  Min:  {min_ms:.2f} ms")
    print(f"  Max:  {max_ms:.2f} ms")
    print(f"  FPS:  {fps:.2f}")

    return {
        'mean_ms': mean_ms,
        'std_ms': std_ms,
        'min_ms': min_ms,
        'max_ms': max_ms,
        'fps': fps
    }


def main():
    parser = argparse.ArgumentParser(
        description='Convert DA3 models to TensorRT'
    )
    parser.add_argument(
        '--model', '-m',
        type=str,
        default='depth-anything/DA3-SMALL',
        help='Model to convert (default: DA3-SMALL)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        required=True,
        help='Output path for TensorRT model'
    )
    parser.add_argument(
        '--precision', '-p',
        type=str,
        default='fp16',
        choices=['fp32', 'fp16', 'int8'],
        help='Precision mode (default: fp16)'
    )
    parser.add_argument(
        '--input-size',
        type=int,
        nargs=2,
        default=[384, 384],
        metavar=('HEIGHT', 'WIDTH'),
        help='Input size (default: 384 384)'
    )
    parser.add_argument(
        '--benchmark',
        action='store_true',
        help='Benchmark both original and converted models'
    )
    parser.add_argument(
        '--iterations',
        type=int,
        default=100,
        help='Benchmark iterations (default: 100)'
    )
    parser.add_argument(
        '--calibration-dir',
        type=str,
        help='Directory with calibration images for INT8 (optional)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.input_size[0] <= 0 or args.input_size[1] <= 0:
        print("ERROR: Input size must be positive")
        sys.exit(1)

    if args.input_size[0] > 4096 or args.input_size[1] > 4096:
        print("WARNING: Very large input size may cause out of memory errors")

    # Check output path
    output_path = Path(args.output)
    if output_path.exists() and not output_path.is_file():
        print(f"ERROR: Output path exists and is not a file: {output_path}")
        sys.exit(1)

    if not output_path.parent.exists():
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"ERROR: Cannot create output directory: {e}")
            sys.exit(1)

    # Check dependencies
    check_dependencies()

    # Load original model
    model_orig = load_da3_model(args.model)

    # Benchmark original model
    if args.benchmark:
        print("\n" + "=" * 60)
        print("ORIGINAL MODEL BENCHMARK")
        print("=" * 60)
        results_orig = benchmark_model(
            model_orig,
            tuple(args.input_size),
            args.iterations
        )

    # Load calibration images for INT8
    calibration_images = None
    if args.precision == 'int8' and args.calibration_dir:
        print(f"\nLoading calibration images from: {args.calibration_dir}")
        # TODO: Load and prepare calibration images
        print("Warning: INT8 calibration not yet implemented")
        print("Model will be converted without calibration (may be suboptimal)")

    # Convert to TensorRT
    model_trt = convert_to_tensorrt(
        model_orig,
        tuple(args.input_size),
        args.precision,
        calibration_images
    )

    # Save model
    output_path = Path(args.output)
    metadata = {
        'model_name': args.model,
        'precision': args.precision,
        'input_size': args.input_size,
        'conversion_date': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    save_tensorrt_model(model_trt, output_path, metadata)

    # Benchmark TensorRT model
    if args.benchmark:
        print("\n" + "=" * 60)
        print("TENSORRT MODEL BENCHMARK")
        print("=" * 60)
        results_trt = benchmark_model(
            model_trt,
            tuple(args.input_size),
            args.iterations
        )

        # Compare
        print("\n" + "=" * 60)
        print("COMPARISON")
        print("=" * 60)

        # Safely calculate speedup
        if results_trt['mean_ms'] > 0:
            speedup = results_orig['mean_ms'] / results_trt['mean_ms']
            print(f"Speedup:      {speedup:.2f}x")
        else:
            print("Speedup:      Unable to calculate (TRT time is zero)")

        print(f"Original:     {results_orig['mean_ms']:.2f} ms ({results_orig['fps']:.2f} FPS)")
        print(f"TensorRT:     {results_trt['mean_ms']:.2f} ms ({results_trt['fps']:.2f} FPS)")
        print(f"Time saved:   {results_orig['mean_ms'] - results_trt['mean_ms']:.2f} ms")

    # Cleanup to free GPU memory
    del model_orig
    del model_trt
    torch.cuda.empty_cache()

    print("\n" + "=" * 60)
    print("CONVERSION COMPLETE")
    print("=" * 60)
    print(f"Model saved to: {output_path}")
    print("\nTo use in ROS2:")
    print(f"  ros2 launch depth_anything_3_ros2 depth_anything_3_optimized.launch.py \\")
    print(f"    backend:=tensorrt_{args.precision} \\")
    print(f"    trt_model_path:={output_path.absolute()}")


if __name__ == '__main__':
    main()
