"""
Unit tests for SharedMemoryInference (file-based IPC backend).

Tests the communication protocol with host TensorRT service via /tmp/da3_shared.
All filesystem operations are mocked since TensorRT runs on host, not in container.
"""

import time
import unittest
from unittest.mock import MagicMock, patch, mock_open

import numpy as np


class TestSharedMemoryInference(unittest.TestCase):
    """Test cases for SharedMemoryInference class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    @patch("depth_anything_3_ros2.da3_inference.SHARED_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_PATH")
    def test_service_availability_when_ready(self, mock_status, mock_dir):
        """Test service detection when status file shows ready."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        mock_status.exists.return_value = True
        mock_status.read_text.return_value = "ready"
        mock_dir.mkdir = MagicMock()

        wrapper = SharedMemoryInference(timeout=1.0)
        wrapper._last_check = 0  # Force re-check

        result = wrapper._check_service()

        self.assertTrue(result)
        self.assertTrue(wrapper._service_available)

    @patch("depth_anything_3_ros2.da3_inference.SHARED_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_PATH")
    def test_service_unavailable_when_no_status(self, mock_status, mock_dir):
        """Test service detection when status file doesn't exist."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        mock_status.exists.return_value = False
        mock_dir.mkdir = MagicMock()

        wrapper = SharedMemoryInference(timeout=1.0)
        wrapper._last_check = 0  # Force re-check

        result = wrapper._check_service()

        self.assertFalse(result)
        self.assertFalse(wrapper._service_available)

    @patch("depth_anything_3_ros2.da3_inference.SHARED_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_PATH")
    def test_fallback_to_pytorch_when_unavailable(self, mock_status, mock_dir):
        """Test fallback to PyTorch wrapper when TRT service unavailable."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        mock_status.exists.return_value = False
        mock_dir.mkdir = MagicMock()

        # Create mock fallback wrapper
        mock_fallback = MagicMock()
        mock_fallback.inference.return_value = {
            "depth": np.random.rand(480, 640).astype(np.float32)
        }

        wrapper = SharedMemoryInference(timeout=1.0, fallback_wrapper=mock_fallback)
        wrapper._last_check = 0

        result = wrapper.inference(self.test_image)

        mock_fallback.inference.assert_called_once()
        self.assertIn("depth", result)

    @patch("depth_anything_3_ros2.da3_inference.SHARED_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_PATH")
    def test_raises_when_unavailable_no_fallback(self, mock_status, mock_dir):
        """Test RuntimeError raised when service unavailable and no fallback."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        mock_status.exists.return_value = False
        mock_dir.mkdir = MagicMock()

        wrapper = SharedMemoryInference(timeout=1.0, fallback_wrapper=None)
        wrapper._last_check = 0

        with self.assertRaises(RuntimeError) as context:
            wrapper.inference(self.test_image)

        self.assertIn("not available", str(context.exception))

    def test_preprocess_image_shape(self):
        """Test image preprocessing produces correct tensor shape."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        with patch("depth_anything_3_ros2.da3_inference.SHARED_DIR") as mock_dir:
            with patch(
                "depth_anything_3_ros2.da3_inference.STATUS_PATH"
            ) as mock_status:
                mock_status.exists.return_value = False
                mock_dir.mkdir = MagicMock()

                wrapper = SharedMemoryInference(timeout=1.0)
                result = wrapper._preprocess_image(self.test_image)

        # DA3 expects (1, 1, 3, 518, 518)
        self.assertEqual(result.shape, (1, 1, 3, 518, 518))
        self.assertEqual(result.dtype, np.float32)

    def test_preprocess_image_normalization(self):
        """Test image preprocessing applies correct normalization."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        with patch("depth_anything_3_ros2.da3_inference.SHARED_DIR") as mock_dir:
            with patch(
                "depth_anything_3_ros2.da3_inference.STATUS_PATH"
            ) as mock_status:
                mock_status.exists.return_value = False
                mock_dir.mkdir = MagicMock()

                wrapper = SharedMemoryInference(timeout=1.0)

                # Create white image (255, 255, 255)
                white_image = np.ones((518, 518, 3), dtype=np.uint8) * 255
                result = wrapper._preprocess_image(white_image)

        # After normalization: (1.0 - mean) / std
        # For white: (1.0 - 0.485) / 0.229 ~ 2.25 for R channel
        # Values should be roughly around 2.0-2.5 for white image
        self.assertTrue(np.all(result > 1.0))

    @patch("depth_anything_3_ros2.da3_inference.SHARED_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_PATH")
    def test_gpu_memory_usage_returns_none(self, mock_status, mock_dir):
        """Test GPU memory usage returns None (managed by host service)."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        mock_status.exists.return_value = False
        mock_dir.mkdir = MagicMock()

        wrapper = SharedMemoryInference(timeout=1.0)
        result = wrapper.get_gpu_memory_usage()

        self.assertIsNone(result)

    @patch("depth_anything_3_ros2.da3_inference.SHARED_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_PATH")
    def test_clear_cache_is_noop(self, mock_status, mock_dir):
        """Test clear_cache does nothing (no local cache for IPC client)."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        mock_status.exists.return_value = False
        mock_dir.mkdir = MagicMock()

        wrapper = SharedMemoryInference(timeout=1.0)
        # Should not raise
        wrapper.clear_cache()

    @patch("depth_anything_3_ros2.da3_inference.SHARED_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_PATH")
    def test_is_service_available_property(self, mock_status, mock_dir):
        """Test is_service_available property."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        mock_status.exists.return_value = True
        mock_status.read_text.return_value = "ready"
        mock_dir.mkdir = MagicMock()

        wrapper = SharedMemoryInference(timeout=1.0)
        wrapper._last_check = 0

        self.assertTrue(wrapper.is_service_available)


class TestSharedMemoryInferenceProtocol(unittest.TestCase):
    """Test cases for the IPC protocol of SharedMemoryInference."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        self.mock_depth = np.random.rand(518, 518).astype(np.float32)

    @patch("depth_anything_3_ros2.da3_inference.np.save")
    @patch("depth_anything_3_ros2.da3_inference.np.load")
    @patch("depth_anything_3_ros2.da3_inference.os.fsync")
    @patch("depth_anything_3_ros2.da3_inference.OUTPUT_PATH")
    @patch("depth_anything_3_ros2.da3_inference.INPUT_PATH")
    @patch("depth_anything_3_ros2.da3_inference.REQUEST_PATH")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_PATH")
    @patch("depth_anything_3_ros2.da3_inference.SHARED_DIR")
    def test_inference_protocol_flow(
        self,
        mock_dir,
        mock_status,
        mock_request,
        mock_input,
        mock_output,
        mock_fsync,
        mock_load,
        mock_save,
    ):
        """Test the full inference protocol flow."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        # Setup mocks
        mock_dir.mkdir = MagicMock()
        mock_status.exists.return_value = True
        mock_status.read_text.return_value = "complete:123456"
        mock_output.exists.return_value = True
        mock_load.return_value = self.mock_depth

        # Mock Path operations for temp files
        mock_input.parent = MagicMock()
        mock_input.parent.__truediv__ = MagicMock(return_value=MagicMock())
        mock_request.parent = MagicMock()
        mock_request.parent.__truediv__ = MagicMock(return_value=MagicMock())

        wrapper = SharedMemoryInference(timeout=1.0)
        wrapper._service_available = True
        wrapper._last_check = time.time()

        # Mock the file operations
        with patch("builtins.open", mock_open()):
            result = wrapper._inference_via_shared_memory(self.test_image)

        # Verify output
        self.assertIn("depth", result)
        self.assertEqual(result["depth"].dtype, np.float32)

    @patch("depth_anything_3_ros2.da3_inference.SHARED_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_PATH")
    def test_timeout_handling(self, mock_status, mock_dir):
        """Test timeout when service doesn't respond."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInference

        mock_dir.mkdir = MagicMock()
        mock_status.exists.return_value = True
        # Status never shows complete
        mock_status.read_text.return_value = "ready"

        wrapper = SharedMemoryInference(timeout=0.01)  # Very short timeout
        wrapper._service_available = True
        wrapper._last_check = time.time()

        # Mock input path operations
        with patch("depth_anything_3_ros2.da3_inference.INPUT_PATH") as mock_input:
            mock_input.parent = MagicMock()
            mock_input.parent.__truediv__ = MagicMock(return_value=MagicMock())
            with patch("depth_anything_3_ros2.da3_inference.REQUEST_PATH") as mock_req:
                mock_req.parent = MagicMock()
                mock_req.parent.__truediv__ = MagicMock(return_value=MagicMock())
                with patch("builtins.open", mock_open()):
                    with patch("depth_anything_3_ros2.da3_inference.os.fsync"):
                        with patch("depth_anything_3_ros2.da3_inference.np.save"):
                            with self.assertRaises(TimeoutError) as context:
                                wrapper._inference_via_shared_memory(self.test_image)

        self.assertIn("timeout", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main()
