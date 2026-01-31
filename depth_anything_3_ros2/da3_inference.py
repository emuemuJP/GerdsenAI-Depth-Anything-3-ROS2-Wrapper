"""
Depth Anything 3 Inference Wrapper.

This module provides a wrapper around the Depth Anything 3 model for efficient
depth estimation with CUDA support and CPU fallback.
"""

import logging
from typing import Optional, Dict
import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)


class DA3InferenceWrapper:
    """
    Wrapper class for Depth Anything 3 model inference.

    This class handles model loading from Hugging Face Hub, inference execution,
    and provides utilities for depth map processing with proper error handling
    and resource management.
    """

    def __init__(
        self,
        model_name: str = "depth-anything/DA3-BASE",
        device: str = "cuda",
        cache_dir: Optional[str] = None,
    ):
        """
        Initialize the DA3 inference wrapper.

        Args:
            model_name: Hugging Face model ID or local model path
            device: Inference device ('cuda' or 'cpu')
            cache_dir: Optional directory for model caching

        Raises:
            RuntimeError: If model loading fails
            ValueError: If device is invalid
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._device = None

        # Validate and set device
        self.device = self._setup_device(device)

        # Load model
        self._load_model()

        logger.info(f"DA3 model '{model_name}' loaded successfully on {self.device}")

    def _setup_device(self, requested_device: str) -> str:
        """
        Setup and validate the compute device.

        Args:
            requested_device: Requested device string ('cuda' or 'cpu')

        Returns:
            Validated device string

        Raises:
            ValueError: If requested device is invalid
        """
        if requested_device not in ["cuda", "cpu"]:
            raise ValueError(
                f"Invalid device '{requested_device}'. " f"Must be 'cuda' or 'cpu'"
            )

        # Check CUDA availability
        if requested_device == "cuda":
            if not torch.cuda.is_available():
                logger.warning(
                    "CUDA requested but not available. Falling back to CPU. "
                    "Performance may be degraded."
                )
                return "cpu"
            else:
                cuda_device = torch.cuda.get_device_name(0)
                logger.info(f"Using CUDA device: {cuda_device}")
                return "cuda"

        return "cpu"

    def _load_model(self) -> None:
        """
        Load the Depth Anything 3 model from Hugging Face Hub.

        Raises:
            RuntimeError: If model loading fails
        """
        try:
            # Try loading via depth_anything_3.api first (full installation)
            try:
                from depth_anything_3.api import DepthAnything3

                logger.info(
                    f"Loading model '{self.model_name}' via DA3 API..."
                )
                if self.cache_dir:
                    self._model = DepthAnything3.from_pretrained(
                        self.model_name, cache_dir=self.cache_dir
                    )
                else:
                    self._model = DepthAnything3.from_pretrained(self.model_name)
                self._model = self._model.to(device=self.device)
                self._model.eval()
                return
            except ImportError:
                logger.info(
                    "DA3 API not available (missing optional deps), "
                    "using direct model loading..."
                )

            # Fallback: Load model directly without api module
            # This avoids pycolmap/open3d dependencies
            from huggingface_hub import hf_hub_download
            from safetensors.torch import load_file
            import json

            logger.info(
                f"Loading model '{self.model_name}' directly from HuggingFace..."
            )

            # Download config and weights
            config_path = hf_hub_download(
                repo_id=self.model_name,
                filename="config.json",
                cache_dir=self.cache_dir,
            )
            weights_path = hf_hub_download(
                repo_id=self.model_name,
                filename="model.safetensors",
                cache_dir=self.cache_dir,
            )

            # Load config
            with open(config_path) as f:
                config = json.load(f)

            # Import model class directly (avoids api.py)
            from depth_anything_3.model.da3 import DepthAnything3Net

            # Create model from config
            self._model = DepthAnything3Net(
                encoder=config.get("encoder", "vitl"),
                features=config.get("features", 256),
                out_channels=config.get("out_channels", [256, 512, 1024, 1024]),
            )

            # Load weights
            state_dict = load_file(weights_path)
            self._model.load_state_dict(state_dict)

            # Move to device and set eval mode
            self._model = self._model.to(device=self.device)
            self._model.eval()

            logger.info(f"Model loaded directly: {self.model_name}")

        except ImportError as e:
            raise RuntimeError(
                "Failed to import Depth Anything 3. "
                "Please ensure the package is installed: "
                "pip install git+https://github.com/"
                "ByteDance-Seed/Depth-Anything-3.git"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to load model '{self.model_name}': {str(e)}"
            ) from e

    def inference(
        self,
        image: np.ndarray,
        return_confidence: bool = True,
        return_camera_params: bool = False,
    ) -> Dict[str, np.ndarray]:
        """
        Run depth inference on an input image.

        Args:
            image: Input RGB image as numpy array (H, W, 3) with values in [0, 255]
            return_confidence: Whether to return confidence map
            return_camera_params: Whether to return camera extrinsics and intrinsics

        Returns:
            Dictionary containing:
                - 'depth': Depth map (H, W) as float32
                - 'confidence': Confidence map (H, W) as float32 (if requested)
                - 'extrinsics': Camera extrinsics (3, 4) as float32 (if requested)
                - 'intrinsics': Camera intrinsics (3, 3) as float32 (if requested)

        Raises:
            ValueError: If input image format is invalid
            RuntimeError: If inference fails
        """
        # Validate input
        if not isinstance(image, np.ndarray):
            raise ValueError(f"Expected numpy array, got {type(image)}")

        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(
                f"Expected RGB image with shape (H, W, 3), got {image.shape}"
            )

        if image.dtype != np.uint8:
            logger.warning(f"Expected uint8 image, got {image.dtype}. Converting...")
            image = image.astype(np.uint8)

        try:
            # Convert numpy array to PIL Image for DA3 API
            pil_image = Image.fromarray(image)

            # Run inference
            with torch.no_grad():
                prediction = self._model.inference([pil_image])

            # Extract results
            result = {"depth": prediction.depth[0].astype(np.float32)}

            if return_confidence:
                result["confidence"] = prediction.conf[0].astype(np.float32)

            if return_camera_params:
                result["extrinsics"] = prediction.extrinsics[0].astype(np.float32)
                result["intrinsics"] = prediction.intrinsics[0].astype(np.float32)

            return result

        except torch.cuda.OutOfMemoryError as e:
            # Clear CUDA cache on OOM
            if self.device == "cuda":
                torch.cuda.empty_cache()
            raise RuntimeError(
                f"CUDA out of memory during inference. Try reducing image size or "
                f"switching to CPU mode. Error: {str(e)}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Inference failed: {str(e)}") from e

    def get_gpu_memory_usage(self) -> Optional[Dict[str, float]]:
        """
        Get current GPU memory usage statistics.

        Returns:
            Dictionary with 'allocated_mb' and 'reserved_mb' if CUDA is available,
            None otherwise
        """
        if self.device == "cuda" and torch.cuda.is_available():
            return {
                "allocated_mb": torch.cuda.memory_allocated() / (1024**2),
                "reserved_mb": torch.cuda.memory_reserved() / (1024**2),
            }
        return None

    def clear_cache(self) -> None:
        """Clear CUDA cache to free up memory."""
        if self.device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("CUDA cache cleared")

    def __del__(self):
        """Cleanup resources on deletion."""
        if self._model is not None:
            del self._model
            self.clear_cache()
