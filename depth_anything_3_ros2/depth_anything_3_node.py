"""
Depth Anything 3 ROS2 Node.

Camera-agnostic ROS2 node for monocular depth estimation using Depth Anything 3.
This node subscribes to standard sensor_msgs/Image topics and publishes depth maps.
"""

import time
from typing import Optional
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
from std_msgs.msg import Header
from cv_bridge import CvBridge, CvBridgeError
import cv2

from .da3_inference import DA3InferenceWrapper, SharedMemoryInference, SharedMemoryInferenceFast
from .utils import normalize_depth, colorize_depth, PerformanceMetrics, resize_image


class DepthAnything3Node(Node):
    """
    ROS2 node for Depth Anything 3 monocular depth estimation.

    This node is completely camera-agnostic and works with any camera
    publishing standard sensor_msgs/Image messages.
    """

    def __init__(self):
        """Initialize the Depth Anything 3 ROS2 node."""
        super().__init__("depth_anything_3")

        # Declare parameters
        self._declare_parameters()

        # Get parameters
        self._load_parameters()

        # Initialize CV bridge for ROS2 <-> OpenCV conversion
        self.bridge = CvBridge()

        # Initialize performance metrics
        self.metrics = PerformanceMetrics(window_size=30)

        # Initialize inference backend
        try:
            if self.use_shared_memory:
                # Try fast SHM first (uses /dev/shm for ~15-25ms lower latency)
                from pathlib import Path
                if Path("/dev/shm/da3/status").exists():
                    self.get_logger().info(
                        "Initializing SharedMemoryInferenceFast (RAM-backed /dev/shm)"
                    )
                    self.model = SharedMemoryInferenceFast(timeout=0.5)
                    if self.model.is_service_available:
                        self.get_logger().info(
                            "Fast SHM TRT service detected - expecting 20-30 FPS"
                        )
                    else:
                        self.get_logger().warn(
                            "Fast SHM service not ready - falling back to file IPC"
                        )
                        self.model = SharedMemoryInference(timeout=1.0)
                else:
                    self.get_logger().info(
                        "Initializing SharedMemoryInference for host TRT communication"
                    )
                    self.model = SharedMemoryInference(timeout=1.0)
                if self.model.is_service_available:
                    self.get_logger().info("Host TRT service detected and ready")
                else:
                    self.get_logger().warn(
                        "Host TRT service not detected - will retry on first inference"
                    )
            else:
                self.get_logger().info(
                    f"Initializing Depth Anything 3 with model: {self.model_name}"
                )
                self.model = DA3InferenceWrapper(
                    model_name=self.model_name, device=self.device, cache_dir=self.cache_dir
                )
            self.get_logger().info("Inference backend initialized successfully")
        except Exception as e:
            self.get_logger().error(f"Failed to initialize inference backend: {e}")
            raise

        # Setup QoS profile for subscriptions
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

        # Performance logging timer
        if self.log_inference_time:
            self.create_timer(5.0, self._log_performance)

        self.get_logger().info("Depth Anything 3 node initialized successfully")
        self.get_logger().info(f"Subscribed to: {self.image_sub.topic_name}")
        self.get_logger().info(f"Publishing depth to: {self.depth_pub.topic_name}")

    def _declare_parameters(self) -> None:
        """Declare all ROS2 parameters with default values."""
        # Model configuration
        self.declare_parameter("model_name", "depth-anything/DA3-BASE")
        self.declare_parameter("device", "cuda")
        self.declare_parameter("cache_dir", "")

        # Image processing
        self.declare_parameter("inference_height", 518)
        self.declare_parameter("inference_width", 518)
        self.declare_parameter("input_encoding", "bgr8")
        self.declare_parameter("keep_image_size", False)

        # Output configuration
        self.declare_parameter("normalize_depth", True)
        self.declare_parameter("publish_colored", True)
        self.declare_parameter("publish_confidence", True)
        self.declare_parameter("colormap", "turbo")

        # Performance
        self.declare_parameter("queue_size", 1)
        self.declare_parameter("processing_threads", 1)

        # Logging
        self.declare_parameter("log_inference_time", False)

        # Jetson TRT mode (host-container split)
        self.declare_parameter("use_shared_memory", False)

    def _load_parameters(self) -> None:
        """Load parameters from ROS2 parameter server."""
        # Model configuration
        self.model_name = self.get_parameter("model_name").value
        self.device = self.get_parameter("device").value
        cache_dir_param = self.get_parameter("cache_dir").value
        self.cache_dir = cache_dir_param if cache_dir_param else None

        # Image processing
        self.inference_height = self.get_parameter("inference_height").value
        self.inference_width = self.get_parameter("inference_width").value
        self.input_encoding = self.get_parameter("input_encoding").value
        self.keep_image_size = self.get_parameter("keep_image_size").value

        # Output configuration
        self.normalize_depth_output = self.get_parameter("normalize_depth").value
        self.publish_colored = self.get_parameter("publish_colored").value
        self.publish_confidence = self.get_parameter("publish_confidence").value
        self.colormap = self.get_parameter("colormap").value

        # Performance
        self.queue_size = self.get_parameter("queue_size").value
        self.processing_threads = self.get_parameter("processing_threads").value

        # Logging
        self.log_inference_time = self.get_parameter("log_inference_time").value

        # Jetson TRT mode
        self.use_shared_memory = self.get_parameter("use_shared_memory").value

    def camera_info_callback(self, msg: CameraInfo) -> None:
        """
        Store latest camera info for republishing with depth images.

        Args:
            msg: CameraInfo message from camera driver
        """
        self.latest_camera_info = msg

    def image_callback(self, msg: Image) -> None:
        """
        Process incoming image and publish depth estimation.

        Args:
            msg: Input image message from camera (any camera type)
        """
        start_time = time.time()

        try:
            # Convert ROS Image to OpenCV format
            try:
                cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8")
            except CvBridgeError as e:
                self.get_logger().error(f"CV Bridge conversion failed: {e}")
                return

            # Ensure image is in correct format (RGB, uint8)
            if cv_image.dtype != np.uint8:
                self.get_logger().warn(
                    f"Image dtype is {cv_image.dtype}, converting to uint8"
                )
                cv_image = cv_image.astype(np.uint8)

            # Run inference
            inference_start = time.time()
            try:
                result = self.model.inference(
                    cv_image,
                    return_confidence=self.publish_confidence,
                    return_camera_params=False,
                )
            except Exception as e:
                self.get_logger().error(f"Inference failed: {e}")
                return

            inference_time = time.time() - inference_start

            # Extract depth map
            depth_map = result["depth"]

            # Resize if requested
            if self.keep_image_size:
                original_size = (cv_image.shape[0], cv_image.shape[1])
                depth_map = resize_image(
                    depth_map, target_size=original_size, keep_aspect_ratio=False, interpolation=cv2.INTER_LINEAR
                )
                if "confidence" in result:
                    result["confidence"] = resize_image(
                        result["confidence"], target_size=original_size, keep_aspect_ratio=False, interpolation=cv2.INTER_NEAREST
                    )

            # Normalize if requested
            if self.normalize_depth_output:
                depth_map = normalize_depth(depth_map)

            # Publish depth map
            self._publish_depth(depth_map, msg.header)

            # Publish colored depth visualization
            if self.publish_colored:
                self._publish_colored_depth(depth_map, msg.header)

            # Publish confidence map
            if self.publish_confidence and "confidence" in result:
                self._publish_confidence(result["confidence"], msg.header)

            # Publish camera info
            if self.latest_camera_info is not None:
                camera_info_msg = self.latest_camera_info
                camera_info_msg.header = msg.header
                self.camera_info_pub.publish(camera_info_msg)

            # Update performance metrics
            total_time = time.time() - start_time
            self.metrics.update(inference_time, total_time)

        except Exception as e:
            self.get_logger().error(f"Unexpected error in image callback: {e}")

    def _publish_depth(self, depth_map: np.ndarray, header: Header) -> None:
        """
        Publish depth map as ROS2 Image message.

        Args:
            depth_map: Depth map (H, W) as float32
            header: Original image header for timestamp and frame_id
        """
        try:
            depth_msg = self.bridge.cv2_to_imgmsg(depth_map, encoding="32FC1")
            depth_msg.header = header
            self.depth_pub.publish(depth_msg)
        except CvBridgeError as e:
            self.get_logger().error(f"Failed to publish depth map: {e}")

    def _publish_colored_depth(self, depth_map: np.ndarray, header: Header) -> None:
        """
        Publish colorized depth visualization.

        Args:
            depth_map: Depth map (H, W) as float32
            header: Original image header for timestamp and frame_id
        """
        try:
            # Normalize to [0, 1] for colorization (skip if already normalized)
            if self.normalize_depth_output:
                depth_norm = depth_map
            else:
                depth_norm = normalize_depth(depth_map)

            # Smooth depth in float32 to reduce ViT patch boundary artifacts
            depth_smooth = cv2.GaussianBlur(depth_norm, (7, 7), sigmaX=1.5)

            # Convert to uint8 and apply colormap
            depth_u8 = (depth_smooth * 255).astype(np.uint8)
            colored_depth = cv2.applyColorMap(depth_u8, cv2.COLORMAP_TURBO)

            # Convert to ROS message
            colored_msg = self.bridge.cv2_to_imgmsg(colored_depth, encoding="bgr8")
            colored_msg.header = header
            self.depth_colored_pub.publish(colored_msg)
        except Exception as e:
            self.get_logger().error(f"Failed to publish colored depth: {e}")

    def _publish_confidence(self, confidence_map: np.ndarray, header: Header) -> None:
        """
        Publish confidence map.

        Args:
            confidence_map: Confidence map (H, W) as float32
            header: Original image header for timestamp and frame_id
        """
        try:
            conf_msg = self.bridge.cv2_to_imgmsg(confidence_map, encoding="32FC1")
            conf_msg.header = header
            self.confidence_pub.publish(conf_msg)
        except CvBridgeError as e:
            self.get_logger().error(f"Failed to publish confidence map: {e}")

    def _log_performance(self) -> None:
        """Log performance metrics periodically."""
        metrics = self.metrics.get_metrics()
        self.get_logger().info(
            f"Performance - "
            f"FPS: {metrics['fps']:.2f}, "
            f"Inference: {metrics['avg_inference_ms']:.1f}ms, "
            f"Total: {metrics['avg_total_ms']:.1f}ms, "
            f"Frames: {metrics['frame_count']}"
        )

        # Log GPU memory if available
        gpu_mem = self.model.get_gpu_memory_usage()
        if gpu_mem:
            self.get_logger().info(
                f"GPU Memory - "
                f"Allocated: {gpu_mem['allocated_mb']:.1f}MB, "
                f"Reserved: {gpu_mem['reserved_mb']:.1f}MB"
            )

    def destroy_node(self) -> None:
        """Clean up resources on node shutdown."""
        self.get_logger().info("Shutting down Depth Anything 3 node")
        if hasattr(self, "model"):
            del self.model
        super().destroy_node()


def main(args=None):
    """
    Main entry point for the Depth Anything 3 ROS2 node.

    Args:
        args: Command line arguments
    """
    rclpy.init(args=args)

    try:
        node = DepthAnything3Node()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error in Depth Anything 3 node: {e}")
    finally:
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
