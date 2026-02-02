"""
Integration tests for Depth Anything 3 ROS2 node.

Tests node initialization, parameter handling, and message publishing.
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
class TestDepthAnything3Node(unittest.TestCase):
    """Test cases for DepthAnything3Node class."""

    @classmethod
    def setUpClass(cls):
        """Initialize ROS2 for all tests."""
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        """Shutdown ROS2 after all tests."""
        rclpy.shutdown()

    def setUp(self):
        """Set up test fixtures."""
        self.test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    @patch("depth_anything_3_ros2.depth_anything_3_node.DA3InferenceWrapper")
    def test_node_initialization(self, mock_wrapper):
        """Test node initializes with default parameters."""
        from depth_anything_3_ros2.depth_anything_3_node import DepthAnything3Node

        # Mock the inference wrapper
        mock_model = MagicMock()
        mock_wrapper.return_value = mock_model

        node = DepthAnything3Node()

        # Check node name
        self.assertEqual(node.get_name(), "depth_anything_3")

        # Check parameters exist
        self.assertTrue(node.has_parameter("model_name"))
        self.assertTrue(node.has_parameter("device"))
        self.assertTrue(node.has_parameter("normalize_depth"))

        node.destroy_node()

    @patch("depth_anything_3_ros2.depth_anything_3_node.DA3InferenceWrapper")
    def test_parameter_loading(self, mock_wrapper):
        """Test parameter loading from ROS2 parameter server."""
        from depth_anything_3_ros2.depth_anything_3_node import DepthAnything3Node

        mock_model = MagicMock()
        mock_wrapper.return_value = mock_model

        node = DepthAnything3Node()

        # Check default parameter values
        self.assertEqual(
            node.get_parameter("model_name").value, "depth-anything/DA3-BASE"
        )
        self.assertEqual(node.get_parameter("device").value, "cuda")
        self.assertTrue(node.get_parameter("normalize_depth").value)

        node.destroy_node()

    @patch("depth_anything_3_ros2.depth_anything_3_node.DA3InferenceWrapper")
    def test_publishers_created(self, mock_wrapper):
        """Test that all publishers are created correctly."""
        from depth_anything_3_ros2.depth_anything_3_node import DepthAnything3Node

        mock_model = MagicMock()
        mock_wrapper.return_value = mock_model

        node = DepthAnything3Node()

        # Check publishers exist
        self.assertIsNotNone(node.depth_pub)
        self.assertIsNotNone(node.depth_colored_pub)
        self.assertIsNotNone(node.confidence_pub)
        self.assertIsNotNone(node.camera_info_pub)

        node.destroy_node()

    @patch("depth_anything_3_ros2.depth_anything_3_node.DA3InferenceWrapper")
    def test_subscribers_created(self, mock_wrapper):
        """Test that all subscribers are created correctly."""
        from depth_anything_3_ros2.depth_anything_3_node import DepthAnything3Node

        mock_model = MagicMock()
        mock_wrapper.return_value = mock_model

        node = DepthAnything3Node()

        # Check subscribers exist
        self.assertIsNotNone(node.image_sub)
        self.assertIsNotNone(node.camera_info_sub)

        node.destroy_node()

    @patch("depth_anything_3_ros2.depth_anything_3_node.DA3InferenceWrapper")
    def test_image_callback_processing(self, mock_wrapper):
        """Test image callback processes messages correctly."""
        from depth_anything_3_ros2.depth_anything_3_node import DepthAnything3Node

        # Mock the model inference
        mock_model = MagicMock()
        mock_result = {
            "depth": np.random.rand(480, 640).astype(np.float32),
            "confidence": np.random.rand(480, 640).astype(np.float32),
        }
        mock_model.inference.return_value = mock_result
        mock_wrapper.return_value = mock_model

        node = DepthAnything3Node()

        # Create a test image message
        msg = Image()
        msg.header = Header()
        msg.header.stamp = node.get_clock().now().to_msg()
        msg.header.frame_id = "camera_optical_frame"
        msg.height = 480
        msg.width = 640
        msg.encoding = "rgb8"
        msg.is_bigendian = 0
        msg.step = 640 * 3
        msg.data = self.test_image.tobytes()

        # Call the callback
        node.image_callback(msg)

        # Verify inference was called
        mock_model.inference.assert_called_once()

        node.destroy_node()


if __name__ == "__main__":
    unittest.main()
