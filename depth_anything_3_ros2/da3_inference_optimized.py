"""
Optimized Depth Anything 3 Inference Wrapper with TensorRT support.

This module provides an optimized wrapper with TensorRT INT8/FP16 support
for achieving >30 FPS performance on NVIDIA Jetson platforms.
"""

import logging
from typing import Optional, Dict, Tuple
from enum import Enum
import numpy as np
import torch
from pathlib import Path

from .gpu_utils import (
    GPUDepthUpsampler,
    GPUImagePreprocessor,
    CUDAStreamManager,
    GPUMemoryMonitor
)

logger = logging.getLogger(__name__)


class InferenceBackend(Enum):
    """Available inference backends."""
    PYTORCH = "pytorch"
    TENSORRT_FP16 = "tensorrt_fp16"
    TENSORRT_INT8 = "tensorrt_int8"


class DA3InferenceOptimized:
    """
    Optimized Depth Anything 3 inference with multiple backend support.

    Supports:
    - PyTorch (baseline)
    - TensorRT FP16 (2-3x speedup)
    - TensorRT INT8 (3-4x speedup)
    - GPU-accelerated preprocessing and upsampling
    - CUDA streams for pipeline parallelism
    """

    def __init__(
        self,
        model_name: str = "depth-anything/DA3-SMALL",
        backend: str = "pytorch",
        device: str = "cuda",
        cache_dir: Optional[str] = None,
        model_input_size: Tuple[int, int] = (384, 384),
        enable_upsampling: bool = True,
        upsample_mode: str = "bilinear",
        use_cuda_streams: bool = False,
        trt_model_path: Optional[str] = None
    ):
        """
        Initialize optimized DA3 inference wrapper.

        Args:
            model_name: Hugging Face model ID
            backend: Inference backend (pytorch, tensorrt_fp16, tensorrt_int8)
            device: Inference device
            cache_dir: Model cache directory
            model_input_size: Model input resolution (H, W)
            enable_upsampling: Enable GPU upsampling to original resolution
            upsample_mode: Upsampling mode (bilinear, bicubic, nearest)
            use_cuda_streams: Enable CUDA streams for parallelism
            trt_model_path: Path to TensorRT model (if using TensorRT backend)
        """
        self.model_name = model_name
        self.backend = InferenceBackend(backend)
        self.device = self._setup_device(device)
        self.cache_dir = cache_dir
        self.model_input_size = model_input_size
        self.enable_upsampling = enable_upsampling
        self.trt_model_path = trt_model_path

        # Initialize GPU utilities
        self.upsampler = GPUDepthUpsampler(mode=upsample_mode, device=self.device)
        self.preprocessor = GPUImagePreprocessor(
            target_size=model_input_size,
            device=self.device
        )

        # Initialize CUDA streams
        self.stream_manager = None
        if use_cuda_streams and self.device == 'cuda':
            self.stream_manager = CUDAStreamManager(num_streams=3)

        # Load model
        self._model = None
        self._load_model()

        logger.info(
            f"DA3 Optimized: model={model_name}, backend={backend}, "
            f"input_size={model_input_size}, device={self.device}"
        )

    def _setup_device(self, requested_device: str) -> str:
        """Setup and validate compute device."""
        if requested_device not in ['cuda', 'cpu']:
            raise ValueError(f"Invalid device: {requested_device}")

        if requested_device == 'cuda':
            if not torch.cuda.is_available():
                logger.warning("CUDA requested but not available, falling back to CPU")
                return 'cpu'
            else:
                cuda_device = torch.cuda.get_device_name(0)
                logger.info(f"Using CUDA device: {cuda_device}")
                return 'cuda'

        return 'cpu'

    def _load_model(self) -> None:
        """Load model based on selected backend."""
        if self.backend == InferenceBackend.PYTORCH:
            self._load_pytorch_model()
        elif self.backend in [InferenceBackend.TENSORRT_FP16, InferenceBackend.TENSORRT_INT8]:
            self._load_tensorrt_model()
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    def _load_pytorch_model(self) -> None:
        """Load PyTorch model."""
        try:
            from depth_anything_3.api import DepthAnything3

            logger.info(f"Loading PyTorch model: {self.model_name}")

            if self.cache_dir:
                self._model = DepthAnything3.from_pretrained(
                    self.model_name,
                    cache_dir=self.cache_dir
                )
            else:
                self._model = DepthAnything3.from_pretrained(self.model_name)

            self._model = self._model.to(device=self.device)
            self._model.eval()

            # Enable mixed precision for FP16 inference
            if self.device == 'cuda':
                self._model = self._model.half()  # Convert to FP16
                logger.info("Enabled FP16 mixed precision")

        except ImportError as e:
            raise RuntimeError(
                "Failed to import Depth Anything 3. "
                "Please install: pip install git+https://github.com/"
                "ByteDance-Seed/Depth-Anything-3.git"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load PyTorch model: {str(e)}") from e

    def _load_tensorrt_model(self) -> None:
        """Load TensorRT optimized model."""
        if self.trt_model_path is None:
            raise ValueError(
                "TensorRT model path required for TensorRT backend. "
                "Please convert model first using optimize_tensorrt.py"
            )

        trt_path = Path(self.trt_model_path)
        if not trt_path.exists():
            raise FileNotFoundError(
                f"TensorRT model not found: {trt_path}. "
                "Please run: python examples/scripts/optimize_tensorrt.py"
            )

        try:
            # Try to import torch2trt
            try:
                from torch2trt import TRTModule
            except ImportError:
                raise ImportError(
                    "torch2trt not installed. Install with: "
                    "pip install torch2trt"
                )

            logger.info(f"Loading TensorRT model: {trt_path}")

            # Load TensorRT model
            self._model = TRTModule()
            # Use weights_only=True for security (PyTorch 1.13+)
            try:
                self._model.load_state_dict(torch.load(trt_path, weights_only=True))
            except TypeError:
                # Fallback for older PyTorch versions
                logger.warning("PyTorch version does not support weights_only parameter")
                self._model.load_state_dict(torch.load(trt_path))

            logger.info(f"TensorRT model loaded successfully ({self.backend.value})")

        except Exception as e:
            raise RuntimeError(f"Failed to load TensorRT model: {str(e)}") from e

    def inference(
        self,
        image: np.ndarray,
        return_confidence: bool = True,
        return_camera_params: bool = False,
        output_size: Optional[Tuple[int, int]] = None
    ) -> Dict[str, np.ndarray]:
        """
        Run optimized depth inference.

        Args:
            image: Input RGB image (H, W, 3) uint8
            return_confidence: Return confidence map
            return_camera_params: Return camera parameters
            output_size: Target output size (H, W), None for same as input

        Returns:
            Dictionary with depth, confidence, and optional camera params
        """
        # Comprehensive input validation
        if not isinstance(image, np.ndarray):
            raise ValueError(f"Expected numpy array, got {type(image)}")

        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"Expected RGB image (H, W, 3), got {image.shape}")

        if image.size == 0:
            raise ValueError("Image is empty (size=0)")

        if image.shape[0] <= 0 or image.shape[1] <= 0:
            raise ValueError(f"Invalid image dimensions: {image.shape}")

        if image.shape[0] > 8192 or image.shape[1] > 8192:
            raise ValueError(
                f"Image too large: {image.shape}. "
                f"Maximum supported size is 8192x8192"
            )

        if not np.isfinite(image).all():
            raise ValueError("Image contains NaN or infinite values")

        original_size = (image.shape[0], image.shape[1])

        # Determine output size
        if output_size is None:
            output_size = original_size

        try:
            # Preprocess on GPU
            with torch.no_grad():
                # Convert to GPU tensor and resize
                img_tensor = self.preprocessor.preprocess(image, return_tensor=True)

                # Run inference based on backend
                if self.backend == InferenceBackend.PYTORCH:
                    result = self._inference_pytorch(
                        img_tensor,
                        return_confidence,
                        return_camera_params
                    )
                else:
                    result = self._inference_tensorrt(
                        img_tensor,
                        return_confidence
                    )

                # Upsample to output size if needed
                if self.enable_upsampling and output_size != self.model_input_size:
                    result = self._upsample_results(result, output_size)

            return result

        except torch.cuda.OutOfMemoryError as e:
            if self.device == 'cuda':
                torch.cuda.empty_cache()
            raise RuntimeError(
                f"CUDA out of memory. Try reducing input size or "
                f"using smaller model. Error: {str(e)}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Inference failed: {str(e)}") from e

    def _inference_pytorch(
        self,
        img_tensor: torch.Tensor,
        return_confidence: bool,
        return_camera_params: bool
    ) -> Dict[str, np.ndarray]:
        """Run PyTorch inference."""
        # Convert tensor to NumPy array (DA3 API accepts NumPy arrays directly)
        # This eliminates the CPU bottleneck from PIL conversion
        img_numpy = (img_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)

        # Run inference with NumPy array (no PIL conversion needed!)
        with torch.cuda.amp.autocast(enabled=(self.device == 'cuda')):
            prediction = self._model.inference([img_numpy])

        # Validate prediction
        if prediction is None:
            raise RuntimeError("Model returned None prediction")

        if not hasattr(prediction, 'depth') or prediction.depth is None:
            raise RuntimeError("Model prediction missing depth output")

        if len(prediction.depth) == 0:
            raise RuntimeError("Model returned empty depth map")

        # Extract results
        result = {
            'depth': prediction.depth[0].astype(np.float32)
        }

        if return_confidence:
            result['confidence'] = prediction.conf[0].astype(np.float32)

        if return_camera_params:
            result['extrinsics'] = prediction.extrinsics[0].astype(np.float32)
            result['intrinsics'] = prediction.intrinsics[0].astype(np.float32)

        return result

    def _inference_tensorrt(
        self,
        img_tensor: torch.Tensor,
        return_confidence: bool
    ) -> Dict[str, np.ndarray]:
        """Run TensorRT inference."""
        # Run TensorRT inference
        output = self._model(img_tensor)

        # Parse output based on model configuration
        # Assuming output is depth map, modify based on actual TRT model output
        if isinstance(output, torch.Tensor):
            depth = output.squeeze().cpu().numpy().astype(np.float32)
            result = {'depth': depth}

            # TensorRT models typically only output depth
            if return_confidence:
                # TensorRT converted models do not include confidence output
                # Return uniform confidence map as placeholder
                logger.warning(
                    "TensorRT model does not support confidence output. "
                    "Returning uniform confidence map."
                )
                confidence = np.ones_like(depth, dtype=np.float32)
                result['confidence'] = confidence

        else:
            raise ValueError("Unexpected TensorRT output format")

        return result

    def _upsample_results(
        self,
        result: Dict[str, np.ndarray],
        target_size: Tuple[int, int]
    ) -> Dict[str, np.ndarray]:
        """Upsample depth and confidence to target size on GPU."""
        upsampled = {}

        for key, value in result.items():
            if key in ['depth', 'confidence']:
                # Upsample on GPU
                upsampled[key] = self.upsampler.upsample_numpy(value, target_size)
            else:
                # Keep other outputs as-is
                upsampled[key] = value

        return upsampled

    def get_gpu_memory_usage(self) -> Optional[Dict[str, float]]:
        """Get GPU memory usage statistics."""
        if self.device == 'cuda':
            return GPUMemoryMonitor.get_memory_stats()
        return None

    def clear_cache(self) -> None:
        """Clear CUDA cache."""
        if self.device == 'cuda':
            GPUMemoryMonitor.clear_cache()

    def cleanup(self) -> None:
        """
        Explicitly cleanup resources.

        Call this method when done with the model to ensure proper cleanup.
        """
        if self._model is not None:
            del self._model
            self._model = None

        # Clear GPU cache
        self.clear_cache()

        # Clean up GPU utilities
        if hasattr(self, 'upsampler'):
            del self.upsampler

        if hasattr(self, 'preprocessor'):
            del self.preprocessor

        if hasattr(self, 'stream_manager') and self.stream_manager is not None:
            if hasattr(self.stream_manager, 'cleanup'):
                self.stream_manager.cleanup()

        logger.info("DA3InferenceOptimized cleanup completed")

    def __del__(self):
        """Cleanup resources on deletion (fallback)."""
        try:
            self.cleanup()
        except Exception as e:
            # Don't raise exceptions in __del__
            logger.error(f"Error during cleanup: {e}")
