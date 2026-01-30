#!/usr/bin/env python3
"""
TensorRT Optimization for Jetson Platforms (Legacy torch2trt approach)

NOTE: This script uses torch2trt which may fail due to Issue #22 (ONNX export failure).
For production use, prefer the pre-exported ONNX approach:

    python scripts/build_tensorrt_engine.py --auto

This builds TensorRT engines from pre-exported ONNX models, bypassing the export issue.

This legacy script optimizes Depth Anything 3 models using torch2trt.
May not work with all model variants due to DINOv2 tracing issues.

Requirements:
    - NVIDIA JetPack 6.x (includes TensorRT)
    - torch2trt: pip install torch2trt
    - PyTorch with CUDA support

Usage:
    # Optimize DA3-BASE model (may fail - use build_tensorrt_engine.py instead)
    python3 optimize_tensorrt.py \
        --model depth-anything/DA3-BASE \
        --output da3_base_trt.pth \
        --precision fp16

    # Test optimized model
    python3 optimize_tensorrt.py \
        --model depth-anything/DA3-BASE \
        --output da3_base_trt.pth \
        --test \
        --test-image test.jpg

    # Benchmark optimization
    python3 optimize_tensorrt.py \
        --model depth-anything/DA3-BASE \
        --output da3_base_trt.pth \
        --benchmark \
        --iterations 100

RECOMMENDED: Use the new ONNX-based approach instead:
    python scripts/build_tensorrt_engine.py --model da3-small --precision fp16
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Tuple, Optional, Dict
import numpy as np

try:
    import torch
    from torch2trt import torch2trt, TRTModule
except ImportError:
    print("Error: torch2trt not installed")
    print("Install with: pip install torch2trt")
    sys.exit(1)

try:
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation
except ImportError:
    print("Error: transformers not installed")
    print("Install with: pip install transformers")
    sys.exit(1)

from PIL import Image
import cv2


class TensorRTOptimizer:
    """TensorRT optimization for Depth Anything 3 models."""

    def __init__(
        self,
        model_name: str = "depth-anything/DA3-BASE",
        precision: str = "fp16",
        max_batch_size: int = 1,
    ):
        """
        Initialize TensorRT optimizer.

        Args:
            model_name: Hugging Face model identifier
            precision: Precision mode (fp32, fp16, int8)
            max_batch_size: Maximum batch size for optimization
        """
        self.model_name = model_name
        self.precision = precision
        self.max_batch_size = max_batch_size

        # Validate precision
        if precision not in ['fp32', 'fp16', 'int8']:
            raise ValueError(
                f"Invalid precision: {precision}. "
                f"Must be fp32, fp16, or int8"
            )

        # Check CUDA availability
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available. TensorRT requires CUDA.")

        print(f"Initializing TensorRT optimizer for {model_name}")
        print(f"Precision: {precision}")
        print(f"Max batch size: {max_batch_size}")

    def load_original_model(self) -> Tuple[torch.nn.Module, object]:
        """
        Load original PyTorch model.

        Returns:
            Tuple of (model, image_processor)
        """
        print("\nLoading original model...")

        try:
            processor = AutoImageProcessor.from_pretrained(self.model_name)
            model = AutoModelForDepthEstimation.from_pretrained(
                self.model_name
            )
            model = model.cuda()
            model.eval()

            print("Original model loaded successfully")
            return model, processor

        except Exception as e:
            print(f"Error loading model: {e}")
            raise

    def optimize_model(
        self,
        model: torch.nn.Module,
        input_shape: Tuple[int, int, int, int] = (1, 3, 518, 518),
    ) -> TRTModule:
        """
        Optimize model with TensorRT.

        Args:
            model: Original PyTorch model
            input_shape: Input tensor shape (batch, channels, height, width)

        Returns:
            TensorRT optimized model
        """
        print("\nOptimizing model with TensorRT...")
        print(f"Input shape: {input_shape}")

        # Create example input
        x = torch.randn(input_shape).cuda()

        # Configure TensorRT
        fp16_mode = (self.precision == 'fp16')
        int8_mode = (self.precision == 'int8')

        print("Converting to TensorRT...")
        start_time = time.time()

        try:
            model_trt = torch2trt(
                model,
                [x],
                fp16_mode=fp16_mode,
                int8_mode=int8_mode,
                max_batch_size=self.max_batch_size,
                max_workspace_size=1 << 30,  # 1GB
            )

            conversion_time = time.time() - start_time
            print(f"Conversion completed in {conversion_time:.2f}s")

            return model_trt

        except Exception as e:
            print(f"Error during TensorRT conversion: {e}")
            raise

    def save_optimized_model(
        self, model_trt: TRTModule, output_path: Path
    ):
        """
        Save TensorRT optimized model.

        Args:
            model_trt: TensorRT model
            output_path: Output file path
        """
        print(f"\nSaving optimized model to {output_path}")

        try:
            torch.save(model_trt.state_dict(), output_path)
            print("Model saved successfully")

            # Save metadata
            metadata = {
                'model_name': self.model_name,
                'precision': self.precision,
                'max_batch_size': self.max_batch_size,
            }
            metadata_path = output_path.with_suffix('.json')

            import json
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            print(f"Metadata saved to {metadata_path}")

        except Exception as e:
            print(f"Error saving model: {e}")
            raise

    def load_optimized_model(
        self, model_path: Path
    ) -> Tuple[TRTModule, Dict]:
        """
        Load TensorRT optimized model.

        Args:
            model_path: Path to saved TensorRT model

        Returns:
            Tuple of (model, metadata)
        """
        print(f"\nLoading optimized model from {model_path}")

        try:
            # Load metadata
            metadata_path = model_path.with_suffix('.json')
            import json
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            # Create TRT module
            model_trt = TRTModule()
            model_trt.load_state_dict(torch.load(model_path))

            print("Optimized model loaded successfully")
            return model_trt, metadata

        except Exception as e:
            print(f"Error loading optimized model: {e}")
            raise

    def benchmark(
        self,
        model: torch.nn.Module,
        input_shape: Tuple[int, int, int, int] = (1, 3, 518, 518),
        iterations: int = 100,
        warmup: int = 10,
    ) -> Dict[str, float]:
        """
        Benchmark model performance.

        Args:
            model: Model to benchmark
            input_shape: Input tensor shape
            iterations: Number of iterations
            warmup: Number of warmup iterations

        Returns:
            Dictionary with benchmark results
        """
        print(f"\nBenchmarking model ({iterations} iterations)...")

        # Create example input
        x = torch.randn(input_shape).cuda()

        # Warmup
        print(f"Warmup ({warmup} iterations)...")
        with torch.no_grad():
            for _ in range(warmup):
                _ = model(x)

        # Synchronize
        torch.cuda.synchronize()

        # Benchmark
        print(f"Running benchmark...")
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
        results = {
            'mean_ms': np.mean(times) * 1000,
            'std_ms': np.std(times) * 1000,
            'min_ms': np.min(times) * 1000,
            'max_ms': np.max(times) * 1000,
            'median_ms': np.median(times) * 1000,
            'fps': 1.0 / np.mean(times),
        }

        # Print results
        print("\nBenchmark Results:")
        print(f"  Mean: {results['mean_ms']:.2f} ms")
        print(f"  Std: {results['std_ms']:.2f} ms")
        print(f"  Min: {results['min_ms']:.2f} ms")
        print(f"  Max: {results['max_ms']:.2f} ms")
        print(f"  Median: {results['median_ms']:.2f} ms")
        print(f"  FPS: {results['fps']:.2f}")

        return results

    def test_inference(
        self,
        model: torch.nn.Module,
        image_path: Path,
        processor: object,
        output_path: Optional[Path] = None,
    ):
        """
        Test inference on image.

        Args:
            model: Model to test
            image_path: Input image path
            processor: Image processor
            output_path: Optional output path for depth map
        """
        print(f"\nTesting inference on {image_path}")

        # Load image
        image = Image.open(image_path).convert('RGB')
        print(f"Image size: {image.size}")

        # Preprocess
        inputs = processor(images=image, return_tensors="pt")
        pixel_values = inputs["pixel_values"].cuda()

        # Inference
        print("Running inference...")
        start = time.time()

        with torch.no_grad():
            outputs = model(pixel_values)
            depth = outputs.predicted_depth if hasattr(
                outputs, 'predicted_depth'
            ) else outputs

        torch.cuda.synchronize()
        inference_time = time.time() - start

        print(f"Inference time: {inference_time * 1000:.2f} ms")

        # Post-process
        depth = depth.squeeze().cpu().numpy()
        print(f"Depth range: [{depth.min():.3f}, {depth.max():.3f}]")

        # Save if requested
        if output_path:
            depth_normalized = cv2.normalize(
                depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U
            )
            depth_colored = cv2.applyColorMap(
                depth_normalized, cv2.COLORMAP_TURBO
            )
            cv2.imwrite(str(output_path), depth_colored)
            print(f"Saved depth map to {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Optimize DA3 models with TensorRT for Jetson'
    )
    parser.add_argument(
        '--model', '-m', type=str, default='depth-anything/DA3-BASE',
        help='Model to optimize (default: depth-anything/DA3-BASE)'
    )
    parser.add_argument(
        '--output', '-o', type=str, default='da3_trt.pth',
        help='Output path for optimized model (default: da3_trt.pth)'
    )
    parser.add_argument(
        '--precision', '-p', type=str, default='fp16',
        choices=['fp32', 'fp16', 'int8'],
        help='Precision mode (default: fp16)'
    )
    parser.add_argument(
        '--batch-size', type=int, default=1,
        help='Maximum batch size (default: 1)'
    )
    parser.add_argument(
        '--height', type=int, default=518,
        help='Input height (default: 518)'
    )
    parser.add_argument(
        '--width', type=int, default=518,
        help='Input width (default: 518)'
    )
    parser.add_argument(
        '--benchmark', action='store_true',
        help='Benchmark original vs optimized model'
    )
    parser.add_argument(
        '--iterations', type=int, default=100,
        help='Benchmark iterations (default: 100)'
    )
    parser.add_argument(
        '--test', action='store_true',
        help='Test inference on image'
    )
    parser.add_argument(
        '--test-image', type=str,
        help='Image for inference test'
    )
    parser.add_argument(
        '--test-output', type=str,
        help='Output path for test depth map'
    )

    args = parser.parse_args()

    # Create optimizer
    optimizer = TensorRTOptimizer(
        model_name=args.model,
        precision=args.precision,
        max_batch_size=args.batch_size,
    )

    # Load original model
    model_orig, processor = optimizer.load_original_model()

    # Determine input shape
    input_shape = (args.batch_size, 3, args.height, args.width)

    # Benchmark original model if requested
    if args.benchmark:
        print("\n" + "=" * 60)
        print("ORIGINAL MODEL BENCHMARK")
        print("=" * 60)
        results_orig = optimizer.benchmark(
            model_orig, input_shape, args.iterations
        )

    # Optimize model
    model_trt = optimizer.optimize_model(model_orig, input_shape)

    # Save optimized model
    output_path = Path(args.output)
    optimizer.save_optimized_model(model_trt, output_path)

    # Benchmark optimized model if requested
    if args.benchmark:
        print("\n" + "=" * 60)
        print("OPTIMIZED MODEL BENCHMARK")
        print("=" * 60)
        results_trt = optimizer.benchmark(
            model_trt, input_shape, args.iterations
        )

        # Compare
        print("\n" + "=" * 60)
        print("COMPARISON")
        print("=" * 60)
        speedup = results_orig['mean_ms'] / results_trt['mean_ms']
        print(f"Speedup: {speedup:.2f}x")
        print(f"Original: {results_orig['mean_ms']:.2f} ms")
        print(f"Optimized: {results_trt['mean_ms']:.2f} ms")
        print(f"FPS increase: {results_trt['fps']:.2f} -> "
              f"{results_orig['fps']:.2f}")

    # Test inference if requested
    if args.test:
        if not args.test_image:
            print("Error: --test-image required for inference test")
            sys.exit(1)

        test_image = Path(args.test_image)
        if not test_image.exists():
            print(f"Error: Test image not found: {test_image}")
            sys.exit(1)

        test_output = Path(args.test_output) if args.test_output else None

        optimizer.test_inference(
            model_trt, test_image, processor, test_output
        )

    print("\nOptimization complete!")
    print(f"Optimized model saved to: {output_path}")
    print("\nTo use in ROS2 node, modify da3_inference.py to load TRT model")


if __name__ == '__main__':
    main()
