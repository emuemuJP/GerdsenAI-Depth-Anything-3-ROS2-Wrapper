"""
Tests for camera-agnostic functionality.

Tests that the node works with various image encodings and formats,
demonstrating camera-agnostic design.
"""

import unittest
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

# Conditional ROS2 imports - allows collection without ROS2 installed
try:
    import rclpy
    from sensor_msgs.msg import Image
    from std_msgs.msg import Header

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    rclpy = None
    Image = None
    Header = None


@pytest.mark.skipif(not ROS2_AVAILABLE, reason="ROS2 not available")
class TestGenericCamera(unittest.TestCase):
    """Test cases for camera-agnostic functionality."""

    @classmethod
    def setUpClass(cls):
        """Initialize ROS2 for all tests."""
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        """Shutdown ROS2 after all tests."""
        rclpy.shutdown()

    def _create_image_msg(
        self,
        height: int,
        width: int,
        encoding: str,
        frame_id: str = "camera_optical_frame",
    ) -> Image:
        """
        Create a test Image message.

        Args:
            height: Image height
            width: Image width
            encoding: Image encoding (bgr8, rgb8, mono8)
            frame_id: Frame ID for the image

        Returns:
            sensor_msgs/Image message
        """
        msg = Image()
        msg.header = Header()
        msg.header.frame_id = frame_id
        msg.height = height
        msg.width = width
        msg.encoding = encoding
        msg.is_bigendian = 0

        # Create appropriate test data based on encoding
        if encoding in ["bgr8", "rgb8"]:
            channels = 3
            test_data = np.random.randint(
                0, 255, (height, width, channels), dtype=np.uint8
            )
        elif encoding == "mono8":
            channels = 1
            test_data = np.random.randint(0, 255, (height, width), dtype=np.uint8)
        else:
            raise ValueError(f"Unsupported encoding: {encoding}")

        msg.step = width * channels
        msg.data = test_data.tobytes()

        return msg

    @patch("depth_anything_3_ros2.depth_anything_3_node.DA3InferenceWrapper")
    def test_bgr8_encoding(self, mock_wrapper):
        """Test processing BGR8 encoded images."""
        from depth_anything_3_ros2.depth_anything_3_node import DepthAnything3Node

        mock_model = MagicMock()
        mock_result = {
            "depth": np.random.rand(480, 640).astype(np.float32),
            "confidence": np.random.rand(480, 640).astype(np.float32),
        }
        mock_model.inference.return_value = mock_result
        mock_wrapper.return_value = mock_model

        node = DepthAnything3Node()

        # Create BGR8 test message
        msg = self._create_image_msg(480, 640, "bgr8")
        msg.header.stamp = node.get_clock().now().to_msg()

        # Process message
        node.image_callback(msg)

        # Verify inference was called
        self.assertTrue(mock_model.inference.called)

        node.destroy_node()

    @patch("depth_anything_3_ros2.depth_anything_3_node.DA3InferenceWrapper")
    def test_rgb8_encoding(self, mock_wrapper):
        """Test processing RGB8 encoded images."""
        from depth_anything_3_ros2.depth_anything_3_node import DepthAnything3Node

        mock_model = MagicMock()
        mock_result = {
            "depth": np.random.rand(480, 640).astype(np.float32),
            "confidence": np.random.rand(480, 640).astype(np.float32),
        }
        mock_model.inference.return_value = mock_result
        mock_wrapper.return_value = mock_model

        node = DepthAnything3Node()

        # Create RGB8 test message
        msg = self._create_image_msg(480, 640, "rgb8")
        msg.header.stamp = node.get_clock().now().to_msg()

        # Process message
        node.image_callback(msg)

        # Verify inference was called
        self.assertTrue(mock_model.inference.called)

        node.destroy_node()

    @patch("depth_anything_3_ros2.depth_anything_3_node.DA3InferenceWrapper")
    def test_different_image_sizes(self, mock_wrapper):
        """Test processing images of different sizes."""
        from depth_anything_3_ros2.depth_anything_3_node import DepthAnything3Node

        mock_model = MagicMock()
        mock_wrapper.return_value = mock_model

        node = DepthAnything3Node()

        # Test various common camera resolutions
        resolutions = [
            (480, 640),  # VGA
            (720, 1280),  # HD
            (1080, 1920),  # Full HD
        ]

        for height, width in resolutions:
            mock_result = {
                "depth": np.random.rand(height, width).astype(np.float32),
                "confidence": np.random.rand(height, width).astype(np.float32),
            }
            mock_model.inference.return_value = mock_result

            msg = self._create_image_msg(height, width, "rgb8")
            msg.header.stamp = node.get_clock().now().to_msg()

            # Should handle different sizes without errors
            node.image_callback(msg)

        node.destroy_node()

    @patch("depth_anything_3_ros2.depth_anything_3_node.DA3InferenceWrapper")
    def test_different_frame_ids(self, mock_wrapper):
        """Test that node handles different frame IDs correctly."""
        from depth_anything_3_ros2.depth_anything_3_node import DepthAnything3Node

        mock_model = MagicMock()
        mock_result = {
            "depth": np.random.rand(480, 640).astype(np.float32),
            "confidence": np.random.rand(480, 640).astype(np.float32),
        }
        mock_model.inference.return_value = mock_result
        mock_wrapper.return_value = mock_model

        node = DepthAnything3Node()

        # Test various frame IDs from different cameras
        frame_ids = [
            "camera_optical_frame",
            "zed_left_camera_optical_frame",
            "camera_color_optical_frame",
            "usb_cam_optical_frame",
        ]

        for frame_id in frame_ids:
            msg = self._create_image_msg(480, 640, "rgb8", frame_id)
            msg.header.stamp = node.get_clock().now().to_msg()

            # Should handle different frame IDs without errors
            node.image_callback(msg)

        node.destroy_node()


if __name__ == "__main__":
    unittest.main()
