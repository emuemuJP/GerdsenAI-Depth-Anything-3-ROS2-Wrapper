"""
Unit tests for SharedMemoryInferenceFast (/dev/shm IPC backend).

Tests the memory-mapped communication protocol with host TensorRT service.
All filesystem and memmap operations are mocked since TRT runs on host.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np


class TestSharedMemoryInferenceFast(unittest.TestCase):
    """Test cases for SharedMemoryInferenceFast class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_SHM")
    def test_service_availability_when_ready(self, mock_status, mock_dir):
        """Test service detection when status file shows ready."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = True
        mock_status.exists.return_value = True
        mock_status.read_text.return_value = "ready"

        with patch(
            "depth_anything_3_ros2.da3_inference.INPUT_SHM"
        ) as mock_input:
            with patch(
                "depth_anything_3_ros2.da3_inference.OUTPUT_SHM"
            ) as mock_output:
                mock_input.exists.return_value = False
                mock_output.exists.return_value = False

                wrapper = SharedMemoryInferenceFast(timeout=1.0)
                wrapper._last_check = 0  # Force re-check

                result = wrapper._check_service()

        self.assertTrue(result)
        self.assertTrue(wrapper._service_available)

    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_SHM")
    def test_service_unavailable_when_no_status(self, mock_status, mock_dir):
        """Test service detection when status file doesn't exist."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = True
        mock_status.exists.return_value = False

        with patch("depth_anything_3_ros2.da3_inference.INPUT_SHM") as mock_in:
            with patch("depth_anything_3_ros2.da3_inference.OUTPUT_SHM") as mock_out:
                mock_in.exists.return_value = False
                mock_out.exists.return_value = False

                wrapper = SharedMemoryInferenceFast(timeout=1.0)
                wrapper._last_check = 0

                result = wrapper._check_service()

        self.assertFalse(result)
        self.assertFalse(wrapper._service_available)

    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_SHM")
    def test_fallback_to_pytorch_when_unavailable(self, mock_status, mock_dir):
        """Test fallback to PyTorch wrapper when fast SHM unavailable."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = False
        mock_status.exists.return_value = False

        # Create mock fallback wrapper
        mock_fallback = MagicMock()
        mock_fallback.inference.return_value = {
            "depth": np.random.rand(480, 640).astype(np.float32)
        }

        wrapper = SharedMemoryInferenceFast(
            timeout=1.0, fallback_wrapper=mock_fallback
        )
        wrapper._last_check = 0

        result = wrapper.inference(self.test_image)

        mock_fallback.inference.assert_called_once()
        self.assertIn("depth", result)

    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_SHM")
    def test_raises_when_unavailable_no_fallback(self, mock_status, mock_dir):
        """Test RuntimeError raised when service unavailable and no fallback."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = False
        mock_status.exists.return_value = False

        wrapper = SharedMemoryInferenceFast(timeout=1.0, fallback_wrapper=None)
        wrapper._last_check = 0

        with self.assertRaises(RuntimeError) as context:
            wrapper.inference(self.test_image)

        self.assertIn("not available", str(context.exception).lower())

    def test_preprocess_image_shape(self):
        """Test image preprocessing produces correct tensor shape."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        with patch("depth_anything_3_ros2.da3_inference.SHM_DIR") as mock_dir:
            mock_dir.exists.return_value = False

            wrapper = SharedMemoryInferenceFast(timeout=1.0)
            result = wrapper._preprocess_image(self.test_image)

        # DA3 expects (1, 1, 3, 518, 518)
        self.assertEqual(result.shape, (1, 1, 3, 518, 518))
        self.assertEqual(result.dtype, np.float32)

    def test_preprocess_image_normalization(self):
        """Test image preprocessing applies correct normalization."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        with patch("depth_anything_3_ros2.da3_inference.SHM_DIR") as mock_dir:
            mock_dir.exists.return_value = False

            wrapper = SharedMemoryInferenceFast(timeout=1.0)

            # Create white image (255, 255, 255)
            white_image = np.ones((518, 518, 3), dtype=np.uint8) * 255
            result = wrapper._preprocess_image(white_image)

        # After normalization: (1.0 - mean) / std
        # Values should be > 1.0 for white image
        self.assertTrue(np.all(result > 1.0))

    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    def test_gpu_memory_usage_returns_none(self, mock_dir):
        """Test GPU memory usage returns None (managed by host service)."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = False

        wrapper = SharedMemoryInferenceFast(timeout=1.0)
        result = wrapper.get_gpu_memory_usage()

        self.assertIsNone(result)

    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    def test_clear_cache_is_noop(self, mock_dir):
        """Test clear_cache does nothing (no local cache for IPC client)."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = False

        wrapper = SharedMemoryInferenceFast(timeout=1.0)
        # Should not raise
        wrapper.clear_cache()

    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_SHM")
    def test_is_service_available_property(self, mock_status, mock_dir):
        """Test is_service_available property."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = True
        mock_status.exists.return_value = True
        mock_status.read_text.return_value = "ready"

        with patch("depth_anything_3_ros2.da3_inference.INPUT_SHM") as mock_in:
            with patch("depth_anything_3_ros2.da3_inference.OUTPUT_SHM") as mock_out:
                mock_in.exists.return_value = False
                mock_out.exists.return_value = False

                wrapper = SharedMemoryInferenceFast(timeout=1.0)
                wrapper._last_check = 0

                self.assertTrue(wrapper.is_service_available)


class TestSharedMemoryInferenceFastMemmap(unittest.TestCase):
    """Test cases for memmap operations of SharedMemoryInferenceFast."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        self.mock_depth = np.random.rand(1, 518, 518).astype(np.float32)

    @patch("depth_anything_3_ros2.da3_inference.np.memmap")
    @patch("depth_anything_3_ros2.da3_inference.INPUT_SHM")
    @patch("depth_anything_3_ros2.da3_inference.OUTPUT_SHM")
    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    def test_memmap_initialization(
        self, mock_dir, mock_output, mock_input, mock_memmap
    ):
        """Test memory map initialization when SHM files exist."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = True
        mock_input.exists.return_value = True
        mock_output.exists.return_value = True

        # Create mock memmap arrays
        mock_input_mmap = MagicMock()
        mock_output_mmap = MagicMock()
        mock_memmap.side_effect = [mock_input_mmap, mock_output_mmap]

        SharedMemoryInferenceFast(timeout=1.0)

        # Should have attempted to create memmaps
        self.assertEqual(mock_memmap.call_count, 2)

    @patch("depth_anything_3_ros2.da3_inference.np.array")
    @patch("depth_anything_3_ros2.da3_inference.REQUEST_SHM")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_SHM")
    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    def test_inference_via_memmap(
        self, mock_dir, mock_status, mock_request, mock_array
    ):
        """Test inference through memory-mapped arrays."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = True
        mock_status.exists.return_value = True
        mock_status.read_text.return_value = "complete:123456"

        # Create mock output that returns proper depth array
        mock_array.return_value = self.mock_depth

        wrapper = SharedMemoryInferenceFast(timeout=1.0)
        wrapper._service_available = True
        wrapper._last_check = time.time()

        # Create mock memmaps
        wrapper._input_mmap = MagicMock()
        wrapper._input_mmap.__setitem__ = MagicMock()
        wrapper._input_mmap.flush = MagicMock()
        wrapper._output_mmap = self.mock_depth

        result = wrapper._inference_via_memmap(self.test_image)

        self.assertIn("depth", result)
        self.assertEqual(result["depth"].dtype, np.float32)

    @patch("depth_anything_3_ros2.da3_inference.REQUEST_SHM")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_SHM")
    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    def test_timeout_handling(self, mock_dir, mock_status, mock_request):
        """Test timeout when service doesn't respond."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = True
        mock_status.exists.return_value = True
        # Status never shows complete
        mock_status.read_text.return_value = "ready"

        wrapper = SharedMemoryInferenceFast(timeout=0.01)  # Very short timeout
        wrapper._service_available = True
        wrapper._last_check = time.time()

        # Create mock memmaps
        wrapper._input_mmap = MagicMock()
        wrapper._input_mmap.__setitem__ = MagicMock()
        wrapper._input_mmap.flush = MagicMock()
        wrapper._output_mmap = MagicMock()

        with self.assertRaises(TimeoutError) as context:
            wrapper._inference_via_memmap(self.test_image)

        self.assertIn("timeout", str(context.exception).lower())

    @patch("depth_anything_3_ros2.da3_inference.REQUEST_SHM")
    @patch("depth_anything_3_ros2.da3_inference.STATUS_SHM")
    @patch("depth_anything_3_ros2.da3_inference.SHM_DIR")
    def test_error_from_service(self, mock_dir, mock_status, mock_request):
        """Test error handling when service reports error."""
        from depth_anything_3_ros2.da3_inference import SharedMemoryInferenceFast

        mock_dir.exists.return_value = True
        mock_status.exists.return_value = True
        mock_status.read_text.return_value = "error:TRT engine failed"

        wrapper = SharedMemoryInferenceFast(timeout=1.0)
        wrapper._service_available = True
        wrapper._last_check = time.time()

        # Create mock memmaps
        wrapper._input_mmap = MagicMock()
        wrapper._input_mmap.__setitem__ = MagicMock()
        wrapper._input_mmap.flush = MagicMock()
        wrapper._output_mmap = MagicMock()

        with self.assertRaises(RuntimeError) as context:
            wrapper._inference_via_memmap(self.test_image)

        self.assertIn("error", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main()
