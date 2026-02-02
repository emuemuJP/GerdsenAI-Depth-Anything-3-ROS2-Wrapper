#!/usr/bin/env python3
"""
TensorRT Inference Service - Host-side service for DA3 depth estimation.

This service runs on the Jetson HOST (not in Docker) where TensorRT 10.3 is available.
It watches for input tensors via shared memory/files and produces depth outputs.

Architecture:
    [Container: ROS2 Node] <-- /tmp/da3_shared --> [Host: TRT Inference Service]

Usage:
    python3 scripts/trt_inference_service.py --engine models/tensorrt/da3-small-fp16.engine

Requirements:
    - TensorRT 10.3+ (available on JetPack 6.2+ host)
    - numpy, pycuda
"""

import argparse
import os
import sys
import time
import signal
import struct
import fcntl
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

# TensorRT imports
try:
    import tensorrt as trt
    import pycuda.driver as cuda
    import pycuda.autoinit
except ImportError as e:
    print(f"Error: TensorRT or PyCUDA not available: {e}")
    print("This script must run on the Jetson HOST with TensorRT 10.3+")
    sys.exit(1)


# Shared memory paths
SHARED_DIR = Path("/tmp/da3_shared")
INPUT_PATH = SHARED_DIR / "input.npy"
OUTPUT_PATH = SHARED_DIR / "output.npy"
LOCK_PATH = SHARED_DIR / "lock"
STATUS_PATH = SHARED_DIR / "status"
REQUEST_PATH = SHARED_DIR / "request"
STATS_PATH = SHARED_DIR / "stats"


class TRTLogger(trt.ILogger):
    """Custom TensorRT logger."""

    def __init__(self, verbose: bool = False):
        super().__init__()
        self.verbose = verbose

    def log(self, severity, msg):
        if severity <= trt.ILogger.WARNING or self.verbose:
            print(f"[TRT] {msg}")


class TRTInferenceEngine:
    """TensorRT inference engine wrapper."""

    def __init__(self, engine_path: str, verbose: bool = False):
        self.logger = TRTLogger(verbose)
        self.engine_path = engine_path
        self.engine = None
        self.context = None
        self.stream = None
        self.bindings = []
        self.inputs = []
        self.outputs = []
        self.input_shape = None
        self.output_shapes = {}

        self._load_engine()
        self._allocate_buffers()

    def _load_engine(self):
        """Load serialized TensorRT engine."""
        print(f"Loading TensorRT engine: {self.engine_path}")

        with open(self.engine_path, "rb") as f:
            engine_data = f.read()

        runtime = trt.Runtime(self.logger)
        self.engine = runtime.deserialize_cuda_engine(engine_data)

        if self.engine is None:
            raise RuntimeError(f"Failed to load engine: {self.engine_path}")

        self.context = self.engine.create_execution_context()
        self.stream = cuda.Stream()

        print(f"Engine loaded successfully")
        print(f"  TensorRT version: {trt.__version__}")
        print(f"  Num I/O tensors: {self.engine.num_io_tensors}")

    def _allocate_buffers(self):
        """Allocate GPU buffers for input/output tensors."""
        self.bindings = []
        self.inputs = []
        self.outputs = []

        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            dtype = trt.nptype(self.engine.get_tensor_dtype(name))
            shape = self.engine.get_tensor_shape(name)

            # Handle dynamic shapes - use optimization profile
            if -1 in shape:
                shape = self.context.get_tensor_shape(name)

            size = int(np.prod(shape))
            host_mem = cuda.pagelocked_empty(size, dtype)
            device_mem = cuda.mem_alloc(host_mem.nbytes)

            binding = {
                "name": name,
                "dtype": dtype,
                "shape": tuple(shape),
                "host": host_mem,
                "device": device_mem,
            }

            if self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                self.inputs.append(binding)
                self.input_shape = tuple(shape)
                print(f"  Input: {name} {shape} {dtype}")
            else:
                self.outputs.append(binding)
                self.output_shapes[name] = tuple(shape)
                print(f"  Output: {name} {shape} {dtype}")

            self.bindings.append(int(device_mem))

    def infer(self, input_tensor: np.ndarray) -> dict:
        """
        Run inference on input tensor.

        Args:
            input_tensor: Input image tensor (1x1x3xHxW or 1x3xHxW)

        Returns:
            Dictionary with output tensors (depth, confidence, etc.)
        """
        # Ensure correct shape
        if input_tensor.shape != self.input_shape:
            if len(input_tensor.shape) == 4 and len(self.input_shape) == 5:
                # Add batch dimension if needed
                input_tensor = input_tensor.reshape(self.input_shape)

        # Copy input to host buffer
        np.copyto(self.inputs[0]["host"], input_tensor.ravel())

        # Transfer input to GPU
        cuda.memcpy_htod_async(
            self.inputs[0]["device"], self.inputs[0]["host"], self.stream
        )

        # Set tensor addresses
        for inp in self.inputs:
            self.context.set_tensor_address(inp["name"], int(inp["device"]))
        for out in self.outputs:
            self.context.set_tensor_address(out["name"], int(out["device"]))

        # Run inference
        self.context.execute_async_v3(stream_handle=self.stream.handle)

        # Transfer outputs back to host
        outputs = {}
        for out in self.outputs:
            cuda.memcpy_dtoh_async(out["host"], out["device"], self.stream)

        # Synchronize
        self.stream.synchronize()

        # Collect outputs
        for out in self.outputs:
            outputs[out["name"]] = out["host"].reshape(out["shape"]).copy()

        return outputs

    def get_input_shape(self) -> Tuple[int, ...]:
        """Get expected input shape."""
        return self.input_shape

    def cleanup(self):
        """Free GPU resources."""
        for inp in self.inputs:
            inp["device"].free()
        for out in self.outputs:
            out["device"].free()


class InferenceService:
    """
    File-based inference service for host-container communication.

    Protocol:
    1. Container writes input tensor to INPUT_PATH
    2. Container writes timestamp to REQUEST_PATH
    3. Host detects new request, runs inference
    4. Host writes output to OUTPUT_PATH
    5. Host writes "ready" to STATUS_PATH
    """

    def __init__(self, engine: TRTInferenceEngine, poll_interval: float = 0.001):
        self.engine = engine
        self.poll_interval = poll_interval
        self.running = False
        self.stats = {"frames": 0, "total_time": 0.0}

        # Setup shared directory
        SHARED_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(SHARED_DIR, 0o777)

        # Write initial status
        self._write_status("initializing")

        # Clear any stale files
        for path in [INPUT_PATH, OUTPUT_PATH, REQUEST_PATH]:
            if path.exists():
                path.unlink()

        self._write_status("ready")
        print(f"Inference service ready")
        print(f"  Shared dir: {SHARED_DIR}")
        print(f"  Input shape: {engine.get_input_shape()}")

    def _write_status(self, status: str):
        """Write status to file."""
        STATUS_PATH.write_text(status)

    def _write_stats(self, fps: float, latency_ms: float, frames: int):
        """Write stats to file for performance monitor."""
        STATS_PATH.write_text(f"{fps:.2f},{latency_ms:.2f},{frames}")

    def _acquire_lock(self) -> int:
        """Acquire file lock for synchronization."""
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _release_lock(self, fd: int):
        """Release file lock."""
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    def process_request(self) -> bool:
        """
        Check for and process inference request.

        Returns:
            True if request was processed, False otherwise.
        """
        if not REQUEST_PATH.exists():
            return False

        try:
            # Read request timestamp
            request_time = float(REQUEST_PATH.read_text().strip())

            # Load input tensor
            if not INPUT_PATH.exists():
                return False

            input_tensor = np.load(INPUT_PATH)

            # Run inference
            start = time.perf_counter()
            outputs = self.engine.infer(input_tensor)
            inference_time = time.perf_counter() - start

            # Save output (primary depth output)
            # Find the depth output tensor
            depth_key = None
            for key in outputs:
                if "depth" in key.lower() or "predicted" in key.lower():
                    depth_key = key
                    break
            if depth_key is None:
                depth_key = list(outputs.keys())[0]

            np.save(OUTPUT_PATH, outputs[depth_key])

            # Update stats
            self.stats["frames"] += 1
            self.stats["total_time"] += inference_time

            # Clear request
            REQUEST_PATH.unlink()

            # Update status with timing
            self._write_status(f"complete:{inference_time:.4f}")

            return True

        except Exception as e:
            print(f"Error processing request: {e}")
            self._write_status(f"error:{str(e)}")
            return False

    def run(self):
        """Main service loop."""
        self.running = True
        print(f"\nService running. Waiting for requests...")
        print(f"Press Ctrl+C to stop.\n")

        last_stats_write = time.time()
        last_stats_print = time.time()

        while self.running:
            processed = self.process_request()

            if not processed:
                time.sleep(self.poll_interval)

            now = time.time()
            if self.stats["frames"] > 0:
                avg_time = self.stats["total_time"] / self.stats["frames"]
                fps = 1.0 / avg_time if avg_time > 0 else 0
                latency_ms = avg_time * 1000

                # Write stats for performance monitor every second
                if now - last_stats_write > 1.0:
                    self._write_stats(fps, latency_ms, self.stats["frames"])
                    last_stats_write = now

                # Print to console every 5 seconds
                if now - last_stats_print > 5.0:
                    print(
                        f"Stats: {self.stats['frames']} frames, "
                        f"avg {latency_ms:.1f}ms ({fps:.1f} FPS)"
                    )
                    last_stats_print = now

    def stop(self):
        """Stop the service."""
        self.running = False
        self._write_status("stopped")
        print("\nService stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="TensorRT Inference Service for DA3 depth estimation"
    )
    parser.add_argument(
        "--engine",
        type=str,
        default="models/tensorrt/da3-small-fp16.engine",
        help="Path to TensorRT engine file",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.001,
        help="Poll interval in seconds (default: 1ms)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose TensorRT logging"
    )
    args = parser.parse_args()

    # Resolve engine path
    engine_path = Path(args.engine)
    if not engine_path.is_absolute():
        # Try relative to script location
        script_dir = Path(__file__).parent.parent
        engine_path = script_dir / args.engine

    if not engine_path.exists():
        print(f"Error: Engine file not found: {engine_path}")
        sys.exit(1)

    print("=" * 50)
    print("TensorRT Inference Service")
    print("=" * 50)
    print(f"TensorRT version: {trt.__version__}")
    print(f"Engine: {engine_path}")
    print()

    # Load engine
    engine = TRTInferenceEngine(str(engine_path), verbose=args.verbose)

    # Create service
    service = InferenceService(engine, poll_interval=args.poll_interval)

    # Handle signals
    def signal_handler(signum, frame):
        print("\nReceived shutdown signal...")
        service.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run service
    try:
        service.run()
    finally:
        engine.cleanup()


if __name__ == "__main__":
    main()
