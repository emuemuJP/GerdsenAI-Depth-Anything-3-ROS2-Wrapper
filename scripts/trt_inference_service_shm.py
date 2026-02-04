#!/usr/bin/env python3
"""
TensorRT Inference Service with Shared Memory IPC (Optimized).

This version uses numpy.memmap on /dev/shm for ~15-25ms faster IPC
compared to file-based np.load/np.save.

Usage:
    python3 scripts/trt_inference_service_shm.py --engine models/tensorrt/da3-small-fp16.engine
"""

import argparse
import os
import sys
import time
import signal
import mmap
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


# Shared memory paths - use /dev/shm for RAM-backed storage
SHM_DIR = Path("/dev/shm/da3")
INPUT_SHM = SHM_DIR / "input.bin"
OUTPUT_SHM = SHM_DIR / "output.bin"
REQUEST_SHM = SHM_DIR / "request"
STATUS_SHM = SHM_DIR / "status"
STATS_PATH = SHM_DIR / "stats"

# Fixed shapes for DA3-small @ 518x518
INPUT_SHAPE = (1, 1, 3, 518, 518)
OUTPUT_SHAPE = (1, 518, 518)
INPUT_SIZE = int(np.prod(INPUT_SHAPE)) * 4  # float32 = 4 bytes
OUTPUT_SIZE = int(np.prod(OUTPUT_SHAPE)) * 4


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
        """Run inference on input tensor."""
        if input_tensor.shape != self.input_shape:
            if len(input_tensor.shape) == 4 and len(self.input_shape) == 5:
                input_tensor = input_tensor.reshape(self.input_shape)

        np.copyto(self.inputs[0]["host"], input_tensor.ravel())

        cuda.memcpy_htod_async(
            self.inputs[0]["device"], self.inputs[0]["host"], self.stream
        )

        for inp in self.inputs:
            self.context.set_tensor_address(inp["name"], int(inp["device"]))
        for out in self.outputs:
            self.context.set_tensor_address(out["name"], int(out["device"]))

        self.context.execute_async_v3(stream_handle=self.stream.handle)

        outputs = {}
        for out in self.outputs:
            cuda.memcpy_dtoh_async(out["host"], out["device"], self.stream)

        self.stream.synchronize()

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


class SharedMemoryService:
    """
    Shared memory inference service using numpy.memmap on /dev/shm.

    This eliminates file I/O overhead by using RAM-backed memory mapping.
    Expected latency reduction: 15-25ms compared to file-based IPC.
    """

    def __init__(self, engine: TRTInferenceEngine, poll_interval: float = 0.0005):
        self.engine = engine
        self.poll_interval = poll_interval
        self.running = False
        self.stats = {"frames": 0, "total_time": 0.0}

        # Setup shared memory directory
        SHM_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(SHM_DIR, 0o777)

        # Pre-allocate shared memory files
        self._init_shared_memory()

        self._write_status("ready")
        print(f"Shared Memory Inference Service ready")
        print(f"  SHM dir: {SHM_DIR}")
        print(f"  Input: {INPUT_SHM} ({INPUT_SIZE} bytes)")
        print(f"  Output: {OUTPUT_SHM} ({OUTPUT_SIZE} bytes)")
        print(f"  Poll interval: {poll_interval * 1000:.2f}ms")

    def _init_shared_memory(self):
        """Initialize shared memory files with fixed sizes."""
        # Create input buffer
        if not INPUT_SHM.exists() or INPUT_SHM.stat().st_size != INPUT_SIZE:
            with open(INPUT_SHM, 'wb') as f:
                f.write(b'\x00' * INPUT_SIZE)
        os.chmod(INPUT_SHM, 0o666)

        # Create output buffer
        if not OUTPUT_SHM.exists() or OUTPUT_SHM.stat().st_size != OUTPUT_SIZE:
            with open(OUTPUT_SHM, 'wb') as f:
                f.write(b'\x00' * OUTPUT_SIZE)
        os.chmod(OUTPUT_SHM, 0o666)

        # Memory map the files
        self.input_mmap = np.memmap(
            INPUT_SHM, dtype=np.float32, mode='r', shape=INPUT_SHAPE
        )
        self.output_mmap = np.memmap(
            OUTPUT_SHM, dtype=np.float32, mode='r+', shape=OUTPUT_SHAPE
        )

        print(f"  Memory mapped input: {self.input_mmap.shape}")
        print(f"  Memory mapped output: {self.output_mmap.shape}")

    def _write_status(self, status: str):
        """Write status to shared memory file."""
        STATUS_SHM.write_text(status)

    def _write_stats(self, fps: float, latency_ms: float, frames: int):
        """Write stats for monitoring."""
        STATS_PATH.write_text(f"{fps:.2f},{latency_ms:.2f},{frames}")

    def _check_request(self) -> Optional[float]:
        """Check if new request is pending. Returns request timestamp or None."""
        if not REQUEST_SHM.exists():
            return None
        try:
            content = REQUEST_SHM.read_text().strip()
            if content:
                return float(content)
        except (ValueError, OSError):
            pass
        return None

    def process_request(self) -> bool:
        """Process inference request using memory-mapped I/O."""
        request_time = self._check_request()
        if request_time is None:
            return False

        try:
            start = time.perf_counter()

            # Read directly from memory map (no file I/O!)
            input_tensor = np.array(self.input_mmap)

            # Run inference
            outputs = self.engine.infer(input_tensor)

            # Find depth output
            depth_key = None
            for key in outputs:
                if "depth" in key.lower() or "predicted" in key.lower():
                    depth_key = key
                    break
            if depth_key is None:
                depth_key = list(outputs.keys())[0]

            depth_output = outputs[depth_key]

            # Remove extra dimensions if needed
            while depth_output.ndim > 3:
                depth_output = depth_output[0]
            if depth_output.shape != OUTPUT_SHAPE:
                depth_output = depth_output.reshape(OUTPUT_SHAPE)

            # Write directly to memory map (no file I/O!)
            self.output_mmap[:] = depth_output
            self.output_mmap.flush()

            inference_time = time.perf_counter() - start

            # Update stats
            self.stats["frames"] += 1
            self.stats["total_time"] += inference_time

            # Clear request and update status
            REQUEST_SHM.unlink()
            self._write_status(f"complete:{inference_time:.4f}")

            return True

        except Exception as e:
            print(f"Error processing request: {e}")
            self._write_status(f"error:{str(e)}")
            return False

    def run(self):
        """Main service loop."""
        self.running = True
        print(f"\nService running with shared memory IPC...")
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

                if now - last_stats_write > 1.0:
                    self._write_stats(fps, latency_ms, self.stats["frames"])
                    last_stats_write = now

                if now - last_stats_print > 5.0:
                    print(
                        f"Stats: {self.stats['frames']} frames, "
                        f"avg {latency_ms:.1f}ms ({fps:.1f} FPS) [SHM mode]"
                    )
                    last_stats_print = now

    def stop(self):
        """Stop the service."""
        self.running = False
        self._write_status("stopped")
        print("\nService stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="TensorRT Inference Service with Shared Memory IPC"
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
        default=0.0005,
        help="Poll interval in seconds (default: 0.5ms)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose TensorRT logging"
    )
    args = parser.parse_args()

    engine_path = Path(args.engine)
    if not engine_path.is_absolute():
        script_dir = Path(__file__).parent.parent
        engine_path = script_dir / args.engine

    if not engine_path.exists():
        print(f"Error: Engine file not found: {engine_path}")
        sys.exit(1)

    print("=" * 60)
    print("TensorRT Inference Service (Shared Memory Mode)")
    print("=" * 60)
    print(f"TensorRT version: {trt.__version__}")
    print(f"Engine: {engine_path}")
    print()

    engine = TRTInferenceEngine(str(engine_path), verbose=args.verbose)
    service = SharedMemoryService(engine, poll_interval=args.poll_interval)

    def signal_handler(signum, frame):
        print("\nReceived shutdown signal...")
        service.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.run()
    finally:
        engine.cleanup()


if __name__ == "__main__":
    main()
