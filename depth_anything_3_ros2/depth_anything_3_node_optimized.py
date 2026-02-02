"""
Optimized Depth Anything 3 ROS2 Node for >30 FPS performance.

This node implements aggressive optimizations for real-time depth estimation:
- TensorRT INT8/FP16 inference
- GPU-accelerated preprocessing and upsampling
- Async colorization (off critical path)
- Subscriber checks (only colorize if needed)
- CUDA streams for pipeline parallelism
- Direct GPU pipeline (minimize CPU-GPU transfers)
"""

import time
import threading
from typing import Optional
from queue import Queue, Empty, Full
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
from std_msgs.msg import Header
from cv_bridge import CvBridge, CvBridgeError

from .da3_inference_optimized import DA3InferenceOptimized
from .utils import colorize_depth, PerformanceMetrics


class DepthAnything3NodeOptimized(Node):
    """
    Optimized ROS2 node for high-performance depth estimation.

    Targets >30 FPS at 1080p with depth and confidence outputs on
    NVIDIA Jetson Orin AGX.
    """

    def __init__(self):
        """Initialize the optimized Depth Anything 3 ROS2 node."""
        super().__init__("depth_anything_3_optimized")

        # Declare parameters
        self._declare_parameters()

        # Get parameters
        self._load_parameters()

        # Initialize CV bridge
        self.bridge = CvBridge()

        # Initialize performance metrics
        self.metrics = PerformanceMetrics(window_size=30)

        # Initialize optimized DA3 model
        self.get_logger().info(
            f"Initializing optimized DA3: model={self.model_name}, "
            f"backend={self.backend}, input_size={self.model_input_size}"
        )

        try:
            self.model = DA3InferenceOptimized(
                model_name=self.model_name,
                backend=self.backend,
                device=self.device,
                cache_dir=self.cache_dir,
                model_input_size=self.model_input_size,
                enable_upsampling=self.enable_upsampling,
                upsample_mode=self.upsample_mode,
                use_cuda_streams=self.use_cuda_streams,
                trt_model_path=self.trt_model_path,
            )
            self.get_logger().info("Optimized model loaded successfully")
        except Exception as e:
            self.get_logger().error(f"Failed to load model: {e}")
            raise

        # Setup QoS profile
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=self.queue_size,
        )

        # Create subscribers
        self.image_sub = self.create_subscription(
            Image, "~/image_raw", self.image_callback, qos
        )

        self.camera_info_sub = self.create_subscription(
            CameraInfo, "~/camera_info", self.camera_info_callback, qos
        )

        # Create publishers
        self.depth_pub = self.create_publisher(Image, "~/depth", 10)

        if self.publish_colored:
            self.depth_colored_pub = self.create_publisher(Image, "~/depth_colored", 10)

        if self.publish_confidence:
            self.confidence_pub = self.create_publisher(Image, "~/confidence", 10)

        self.camera_info_pub = self.create_publisher(
            CameraInfo, "~/depth/camera_info", 10
        )

        # Store latest camera info
        self.latest_camera_info: Optional[CameraInfo] = None

        # Thread management
        self._running = True
        self._shutdown_lock = threading.Lock()

        # Async colorization setup
        self.colorization_queue = None
        self.colorization_thread = None
        if self.async_colorization and self.publish_colored:
            self._setup_async_colorization()

        # Performance logging timer
        if self.log_inference_time:
            self.create_timer(5.0, self._log_performance)

        self.get_logger().info(
            f"Optimized node initialized - "
            f"Expected: >30 FPS at {self.output_resolution}"
        )
        self.get_logger().info(f"Subscribed to: {self.image_sub.topic_name}")
        self.get_logger().info(f"Publishing depth to: {self.depth_pub.topic_name}")

    def _declare_parameters(self) -> None:
        """Declare all ROS2 parameters."""
        # Model configuration
        self.declare_parameter("model_name", "depth-anything/DA3-SMALL")
        # Backend options: pytorch, tensorrt_fp16, tensorrt_int8, tensorrt_native
        # tensorrt_native is recommended for production Jetson deployment
        self.declare_parameter("backend", "tensorrt_native")
        self.declare_parameter("device", "cuda")
        self.declare_parameter("cache_dir", "")
        # Path to TensorRT engine file (.engine) for tensorrt_native backend
        # Build with: python scripts/build_tensorrt_engine.py --auto
        self.declare_parameter("trt_model_path", "")
        # Auto-detect and build TensorRT engine if not found
        self.declare_parameter("auto_build_engine", False)

        # Image processing
        self.declare_parameter("model_input_height", 384)
        self.declare_parameter("model_input_width", 384)
        self.declare_parameter("output_height", 1080)
        self.declare_parameter("output_width", 1920)
        self.declare_parameter("input_encoding", "bgr8")

        # GPU optimization
        self.declare_parameter("enable_upsampling", True)
        self.declare_parameter("upsample_mode", "bilinear")
        self.declare_parameter("use_cuda_streams", False)

        # Output configuration
        self.declare_parameter("normalize_depth", True)
        self.declare_parameter("publish_colored", True)
        self.declare_parameter("publish_confidence", True)
        self.declare_parameter("colormap", "turbo")
        self.declare_parameter("async_colorization", True)
        self.declare_parameter("check_subscribers", True)

        # Performance
        self.declare_parameter("queue_size", 1)
        self.declare_parameter("log_inference_time", True)

    def _load_parameters(self) -> None:
        """Load parameters from ROS2 parameter server."""
        # Model configuration
        self.model_name = self.get_parameter("model_name").value
        self.backend = self.get_parameter("backend").value
        self.device = self.get_parameter("device").value
        cache_dir_param = self.get_parameter("cache_dir").value
        self.cache_dir = cache_dir_param if cache_dir_param else None
        trt_path_param = self.get_parameter("trt_model_path").value
        self.trt_model_path = trt_path_param if trt_path_param else None
        self.auto_build_engine = self.get_parameter("auto_build_engine").value

        # Handle TensorRT backend requirements
        if self.backend in ["tensorrt_native", "tensorrt_fp16", "tensorrt_int8"]:
            self._handle_tensorrt_backend()

        # Image processing
        input_h = self.get_parameter("model_input_height").value
        input_w = self.get_parameter("model_input_width").value
        self.model_input_size = (input_h, input_w)

        output_h = self.get_parameter("output_height").value
        output_w = self.get_parameter("output_width").value
        self.output_resolution = (output_h, output_w)

        self.input_encoding = self.get_parameter("input_encoding").value

        # GPU optimization
        self.enable_upsampling = self.get_parameter("enable_upsampling").value
        self.upsample_mode = self.get_parameter("upsample_mode").value
        self.use_cuda_streams = self.get_parameter("use_cuda_streams").value

        # Output configuration
        self.normalize_depth_output = self.get_parameter("normalize_depth").value
        self.publish_colored = self.get_parameter("publish_colored").value
        self.publish_confidence = self.get_parameter("publish_confidence").value
        self.colormap = self.get_parameter("colormap").value
        self.async_colorization = self.get_parameter("async_colorization").value
        self.check_subscribers = self.get_parameter("check_subscribers").value

        # Performance
        self.queue_size = self.get_parameter("queue_size").value
        self.log_inference_time = self.get_parameter("log_inference_time").value

    def _handle_tensorrt_backend(self) -> None:
        """Handle TensorRT backend initialization and auto-build if needed."""
        import os
        from pathlib import Path

        # Check if engine path is provided and exists
        if self.trt_model_path:
            engine_path = Path(self.trt_model_path)
            if engine_path.exists():
                self.get_logger().info(f"Using TensorRT engine: {engine_path}")
                return

            self.get_logger().warning(
                f"TensorRT engine not found: {engine_path}"
            )

        # Try to find existing engine in default location
        default_engine_dir = Path(__file__).parent.parent / "models" / "tensorrt"
        if default_engine_dir.exists():
            engines = list(default_engine_dir.glob("*.engine"))
            if engines:
                # Use the most recently modified engine
                latest_engine = max(engines, key=lambda p: p.stat().st_mtime)
                self.trt_model_path = str(latest_engine)
                self.get_logger().info(
                    f"Found existing TensorRT engine: {latest_engine}"
                )
                return

        # Auto-build engine if enabled
        if self.auto_build_engine:
            self.get_logger().info("Auto-building TensorRT engine...")
            engine_path = self._auto_build_tensorrt_engine()
            if engine_path:
                self.trt_model_path = str(engine_path)
                return

        # Fallback to PyTorch if no engine available
        if self.backend == "tensorrt_native":
            self.get_logger().warning(
                "No TensorRT engine available. Falling back to PyTorch backend. "
                "Build engine with: python scripts/build_tensorrt_engine.py --auto"
            )
            self.backend = "pytorch"

    def _auto_build_tensorrt_engine(self):
        """Auto-build TensorRT engine for the current platform."""
        try:
            import subprocess
            import sys
            from pathlib import Path

            build_script = Path(__file__).parent.parent / "scripts" / "build_tensorrt_engine.py"

            if not build_script.exists():
                self.get_logger().error(
                    f"Build script not found: {build_script}"
                )
                return None

            self.get_logger().info("Running TensorRT engine build (this may take several minutes)...")

            result = subprocess.run(
                [sys.executable, str(build_script), "--auto"],
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            if result.returncode == 0:
                # Find the built engine
                engine_dir = Path(__file__).parent.parent / "models" / "tensorrt"
                engines = list(engine_dir.glob("*.engine"))
                if engines:
                    latest_engine = max(engines, key=lambda p: p.stat().st_mtime)
                    self.get_logger().info(f"Built TensorRT engine: {latest_engine}")
                    return latest_engine
            else:
                self.get_logger().error(
                    f"TensorRT build failed: {result.stderr}"
                )

        except subprocess.TimeoutExpired:
            self.get_logger().error("TensorRT build timed out")
        except Exception as e:
            self.get_logger().error(f"Failed to auto-build TensorRT engine: {e}")

        return None

    def _setup_async_colorization(self) -> None:
        """Setup async colorization thread."""
        self.colorization_queue = Queue(maxsize=2)
        self.colorization_thread = threading.Thread(
            target=self._colorization_worker, daemon=True
        )
        self.colorization_thread.start()
        self.get_logger().info("Async colorization thread started")

    def _colorization_worker(self) -> None:
        """Worker thread for async colorization."""
        while self._running and rclpy.ok():
            try:
                # Get item from queue with timeout
                item = self.colorization_queue.get(timeout=0.1)
                depth_map, header = item

                # Check if still running before processing
                if not self._running:
                    break

                # Colorize depth
                colored_depth = colorize_depth(
                    depth_map, colormap=self.colormap, normalize=True
                )

                # Publish with thread safety
                try:
                    with self._shutdown_lock:
                        if self._running and hasattr(self, "depth_colored_pub"):
                            colored_msg = self.bridge.cv2_to_imgmsg(
                                colored_depth, encoding="bgr8"
                            )
                            colored_msg.header = header
                            self.depth_colored_pub.publish(colored_msg)
                except CvBridgeError as e:
                    self.get_logger().error(f"Failed to publish colored depth: {e}")

            except Empty:
                continue
            except Exception as e:
                self.get_logger().error(f"Error in colorization worker: {e}")

        self.get_logger().info("Colorization worker thread exiting")

    def camera_info_callback(self, msg: CameraInfo) -> None:
        """Store latest camera info."""
        self.latest_camera_info = msg

    def image_callback(self, msg: Image) -> None:
        """
        Process incoming image with optimized pipeline.

        Target: <33ms total processing time for >30 FPS
        """
        start_time = time.time()

        try:
            # Convert ROS Image to OpenCV format
            try:
                cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8")
            except CvBridgeError as e:
                self.get_logger().error(f"CV Bridge conversion failed: {e}")
                return

            # Validate converted image
            if cv_image is None or cv_image.size == 0:
                self.get_logger().error("Received empty image after conversion")
                return

            # Ensure correct format
            if cv_image.dtype != np.uint8:
                cv_image = cv_image.astype(np.uint8)

            # Run optimized inference
            inference_start = time.time()
            try:
                result = self.model.inference(
                    cv_image,
                    return_confidence=self.publish_confidence,
                    return_camera_params=False,
                    output_size=self.output_resolution,
                )
            except Exception as e:
                self.get_logger().error(f"Inference failed: {e}")
                return

            inference_time = time.time() - inference_start

            # Extract depth map
            depth_map = result["depth"]

            # Normalize if requested
            if self.normalize_depth_output:
                depth_map = self._normalize_depth_fast(depth_map)

            # Publish depth map (high priority)
            self._publish_depth(depth_map, msg.header)

            # Publish confidence map if requested
            if self.publish_confidence and "confidence" in result:
                self._publish_confidence(result["confidence"], msg.header)

            # Handle colored depth
            if self.publish_colored:
                # Check if anyone is subscribed (optimization)
                if self.check_subscribers:
                    if self.depth_colored_pub.get_subscription_count() == 0:
                        pass  # Skip colorization if no subscribers
                    elif (
                        self.async_colorization and self.colorization_queue is not None
                    ):
                        # Async colorization (off critical path)
                        try:
                            item = (depth_map.copy(), msg.header)
                            self.colorization_queue.put_nowait(item)
                        except Full:
                            # Queue full, skip this frame (OK for real-time)
                            pass
                    else:
                        # Synchronous colorization (fallback)
                        self._publish_colored_depth(depth_map, msg.header)
                elif self.async_colorization and self.colorization_queue is not None:
                    # Always colorize async
                    try:
                        item = (depth_map.copy(), msg.header)
                        self.colorization_queue.put_nowait(item)
                    except Full:
                        # Queue full, skip this frame (OK for real-time)
                        pass
                else:
                    # Always colorize sync
                    self._publish_colored_depth(depth_map, msg.header)

            # Publish camera info (create a copy to avoid modifying original)
            if self.latest_camera_info is not None:
                from copy import deepcopy

                camera_info_msg = deepcopy(self.latest_camera_info)
                camera_info_msg.header = msg.header
                self.camera_info_pub.publish(camera_info_msg)

            # Update performance metrics
            total_time = time.time() - start_time
            self.metrics.update(inference_time, total_time)

        except Exception as e:
            self.get_logger().error(f"Unexpected error in image callback: {e}")

    def _normalize_depth_fast(self, depth: np.ndarray) -> np.ndarray:
        """Fast depth normalization."""
        min_val = depth.min()
        max_val = depth.max()

        if max_val - min_val < 1e-8:
            return np.zeros_like(depth)

        return ((depth - min_val) / (max_val - min_val)).astype(np.float32)

    def _publish_depth(self, depth_map: np.ndarray, header: Header) -> None:
        """Publish depth map."""
        try:
            depth_msg = self.bridge.cv2_to_imgmsg(depth_map, encoding="32FC1")
            depth_msg.header = header
            self.depth_pub.publish(depth_msg)
        except CvBridgeError as e:
            self.get_logger().error(f"Failed to publish depth map: {e}")

    def _publish_colored_depth(self, depth_map: np.ndarray, header: Header) -> None:
        """Publish colorized depth (synchronous)."""
        try:
            colored_depth = colorize_depth(
                depth_map, colormap=self.colormap, normalize=True
            )

            colored_msg = self.bridge.cv2_to_imgmsg(colored_depth, encoding="bgr8")
            colored_msg.header = header
            self.depth_colored_pub.publish(colored_msg)
        except Exception as e:
            self.get_logger().error(f"Failed to publish colored depth: {e}")

    def _publish_confidence(self, confidence_map: np.ndarray, header: Header) -> None:
        """Publish confidence map."""
        try:
            conf_msg = self.bridge.cv2_to_imgmsg(confidence_map, encoding="32FC1")
            conf_msg.header = header
            self.confidence_pub.publish(conf_msg)
        except CvBridgeError as e:
            self.get_logger().error(f"Failed to publish confidence map: {e}")

    def _log_performance(self) -> None:
        """Log performance metrics."""
        metrics = self.metrics.get_metrics()
        self.get_logger().info(
            f"Performance - "
            f"FPS: {metrics['fps']:.2f}, "
            f"Inference: {metrics['avg_inference_ms']:.1f}ms, "
            f"Total: {metrics['avg_total_ms']:.1f}ms, "
            f"Frames: {metrics['frame_count']}"
        )

        # Log GPU memory
        gpu_mem = self.model.get_gpu_memory_usage()
        if gpu_mem:
            self.get_logger().info(
                f"GPU Memory - "
                f"Allocated: {gpu_mem['allocated_mb']:.1f}MB, "
                f"Reserved: {gpu_mem['reserved_mb']:.1f}MB, "
                f"Free: {gpu_mem['free_mb']:.1f}MB"
            )

    def destroy_node(self) -> None:
        """Clean up resources."""
        self.get_logger().info("Shutting down optimized DA3 node")

        # Signal threads to stop
        self._running = False

        # Stop colorization thread with longer timeout
        if self.colorization_thread is not None and self.colorization_thread.is_alive():
            self.get_logger().info("Waiting for colorization thread to exit...")
            self.colorization_thread.join(timeout=5.0)

            if self.colorization_thread.is_alive():
                self.get_logger().warning("Colorization thread did not exit cleanly")

        # Clean up queue
        if self.colorization_queue is not None:
            # Clear any remaining items
            while not self.colorization_queue.empty():
                try:
                    self.colorization_queue.get_nowait()
                except Empty:
                    break

        # Clean up model with explicit cleanup method
        if hasattr(self, "model"):
            if hasattr(self.model, "cleanup"):
                try:
                    self.model.cleanup()
                except Exception as e:
                    self.get_logger().error(f"Error during model cleanup: {e}")
            del self.model

        super().destroy_node()


def main(args=None):
    """Main entry point for the optimized Depth Anything 3 ROS2 node."""
    rclpy.init(args=args)

    try:
        node = DepthAnything3NodeOptimized()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error in optimized DA3 node: {e}")
    finally:
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
