"""
Depth Anything 3 Inference Wrapper.

This module provides inference backends for Depth Anything 3 depth estimation.

PRODUCTION BACKEND (Recommended):
- SharedMemoryInferenceFast: Communicates with host TensorRT 10.3 service via /dev/shm
  - ~15ms inference + ~8ms IPC = ~23ms total frame time
  - 23+ FPS real-world (camera-limited), 43+ FPS processing capacity
  - Requires: Host running trt_inference_service_shm.py

FALLBACK/DEVELOPMENT BACKENDS:
- SharedMemoryInference: File-based IPC with host TRT service (slower, ~40ms IPC)
- DA3InferenceWrapper: PyTorch backend for development/testing only (~5 FPS)

For production deployment on Jetson, use ./run.sh which automatically starts
the TRT service and configures shared memory IPC.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional, Dict
import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)


# Shared memory paths for host-container TRT communication
SHARED_DIR = Path("/tmp/da3_shared")
INPUT_PATH = SHARED_DIR / "input.npy"
OUTPUT_PATH = SHARED_DIR / "output.npy"
STATUS_PATH = SHARED_DIR / "status"
REQUEST_PATH = SHARED_DIR / "request"

# Fast shared memory paths (using /dev/shm for RAM-backed storage)
SHM_DIR = Path("/dev/shm/da3")
INPUT_SHM = SHM_DIR / "input.bin"
OUTPUT_SHM = SHM_DIR / "output.bin"
STATUS_SHM = SHM_DIR / "status"
REQUEST_SHM = SHM_DIR / "request"

# Fixed shapes for DA3-small @ 518x518
INPUT_SHAPE = (1, 1, 3, 518, 518)
OUTPUT_SHAPE = (1, 518, 518)


class SharedMemoryInference:
    """
    Shared memory inference client for host-container TRT communication.

    This class runs inside the container and communicates with the host-side
    TensorRT inference service via shared files.

    Architecture:
        [Container: ROS2 Node] <-- /tmp/da3_shared --> [Host: TRT Inference Service]

    The host service runs TensorRT 10.3 which can load DA3 engines.
    The container runs ROS2 with TRT 8.6.2 which cannot load TRT 10.3 engines.
    """

    def __init__(
        self,
        timeout: float = 1.0,
        fallback_wrapper: Optional["DA3InferenceWrapper"] = None,
    ):
        """
        Initialize shared memory inference client.

        Args:
            timeout: Max wait time for inference response (seconds)
            fallback_wrapper: Optional PyTorch wrapper to use if service unavailable
        """
        self.timeout = timeout
        self.fallback_wrapper = fallback_wrapper
        self._service_available = False
        self._last_check = 0
        self._check_interval = 5.0  # Re-check service every 5 seconds

        # Ensure shared directory exists
        SHARED_DIR.mkdir(parents=True, exist_ok=True)

        self._check_service()

    def _check_service(self) -> bool:
        """Check if host TRT service is available."""
        now = time.time()
        if now - self._last_check < self._check_interval:
            return self._service_available

        self._last_check = now

        if STATUS_PATH.exists():
            status = STATUS_PATH.read_text().strip()
            self._service_available = status.startswith(
                "ready"
            ) or status.startswith("complete")
            if self._service_available:
                logger.info("Host TRT inference service detected")
        else:
            self._service_available = False

        return self._service_available

    def inference(
        self,
        image: np.ndarray,
        return_confidence: bool = True,
        return_camera_params: bool = False,
    ) -> Dict[str, np.ndarray]:
        """
        Run inference via shared memory communication with host TRT service.

        Args:
            image: Input RGB image as numpy array (H, W, 3) with values in [0, 255]
            return_confidence: Whether to return confidence map
            return_camera_params: Whether to return camera extrinsics and intrinsics

        Returns:
            Dictionary containing depth map and optionally confidence/camera params

        Raises:
            RuntimeError: If inference fails and no fallback available
        """
        # Check if service is available
        if not self._check_service():
            if self.fallback_wrapper:
                logger.debug("TRT service unavailable, using PyTorch fallback")
                return self.fallback_wrapper.inference(
                    image, return_confidence, return_camera_params
                )
            raise RuntimeError(
                "Host TRT service not available and no fallback configured"
            )

        try:
            return self._inference_via_shared_memory(image)
        except Exception as e:
            logger.warning(f"Shared memory inference failed: {e}")
            if self.fallback_wrapper:
                logger.info("Falling back to PyTorch inference")
                return self.fallback_wrapper.inference(
                    image, return_confidence, return_camera_params
                )
            raise

    def _inference_via_shared_memory(self, image: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Perform inference via shared memory files.

        Protocol:
        1. Preprocess image to tensor format expected by TRT engine
        2. Write tensor to INPUT_PATH (atomic via temp file + rename)
        3. Write timestamp to REQUEST_PATH to signal new request
        4. Wait for STATUS_PATH to show "complete"
        5. Read depth from OUTPUT_PATH
        """
        # Preprocess image to tensor format
        # DA3 expects: (1, 1, 3, H, W) normalized float32
        input_tensor = self._preprocess_image(image)

        # Write input tensor atomically (temp file + fsync + rename)
        temp_path = INPUT_PATH.parent / "input_tmp.npy"
        with open(temp_path, 'wb') as f:
            np.save(f, input_tensor, allow_pickle=False)
            f.flush()
            os.fsync(f.fileno())
        temp_path.replace(INPUT_PATH)  # Atomic rename

        # Signal new request with timestamp (atomic write to prevent race condition)
        temp_request = REQUEST_PATH.parent / "request_tmp"
        temp_request.write_text(str(time.time()))
        temp_request.replace(REQUEST_PATH)  # Atomic rename

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if STATUS_PATH.exists():
                status = STATUS_PATH.read_text().strip()
                if status.startswith("complete"):
                    break
                elif status.startswith("error"):
                    raise RuntimeError(f"Host TRT service error: {status}")
            time.sleep(0.001)  # 1ms poll interval
        else:
            raise TimeoutError(
                f"TRT inference timeout after {self.timeout}s"
            )

        # Read output
        if not OUTPUT_PATH.exists():
            raise RuntimeError("Output file not created by TRT service")

        depth = np.load(OUTPUT_PATH)

        # Remove batch dimensions if present
        while depth.ndim > 2:
            depth = depth[0]

        # Build result
        result = {"depth": depth.astype(np.float32)}

        # Note: Confidence and camera params not available from TRT engine
        # Could be added by extending the host service

        return result

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for TensorRT inference.

        Args:
            image: RGB image (H, W, 3) uint8

        Returns:
            Preprocessed tensor (1, 1, 3, 518, 518) float32 normalized
        """
        from PIL import Image as PILImage
        import cv2

        # Target size for DA3
        target_size = (518, 518)

        # Resize
        if image.shape[:2] != target_size:
            image = cv2.resize(image, target_size, interpolation=cv2.INTER_LINEAR)

        # Convert to float and normalize
        tensor = image.astype(np.float32) / 255.0

        # Normalize with ImageNet stats
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = (tensor - mean) / std

        # Rearrange to (C, H, W)
        tensor = tensor.transpose(2, 0, 1)

        # Add batch dimensions: (1, 1, 3, H, W) for DA3 ONNX format
        tensor = tensor[np.newaxis, np.newaxis, ...]

        return tensor.astype(np.float32)

    @property
    def is_service_available(self) -> bool:
        """Check if host TRT service is currently available."""
        return self._check_service()

    def get_gpu_memory_usage(self) -> Optional[Dict[str, float]]:
        """
        Get GPU memory usage (not available for shared memory inference).

        Returns:
            None - GPU memory is managed by host TRT service
        """
        return None

    def clear_cache(self) -> None:
        """Clear cache (no-op for shared memory inference)."""
        pass


class SharedMemoryInferenceFast:
    """
    Fast shared memory inference using numpy.memmap on /dev/shm.

    This eliminates file I/O overhead by using RAM-backed memory mapping.
    Expected latency reduction: 15-25ms compared to file-based IPC.

    Requires the host to run trt_inference_service_shm.py instead of
    trt_inference_service.py.
    """

    def __init__(
        self,
        timeout: float = 0.5,
        fallback_wrapper: Optional["DA3InferenceWrapper"] = None,
    ):
        self.timeout = timeout
        self.fallback_wrapper = fallback_wrapper
        self._service_available = False
        self._last_check = 0
        self._check_interval = 5.0
        self._input_mmap = None
        self._output_mmap = None

        self._init_shared_memory()

    def _init_shared_memory(self):
        """Initialize memory-mapped arrays."""
        if not SHM_DIR.exists():
            logger.warning(f"SHM directory {SHM_DIR} does not exist")
            return

        try:
            if INPUT_SHM.exists():
                self._input_mmap = np.memmap(
                    INPUT_SHM, dtype=np.float32, mode='r+', shape=INPUT_SHAPE
                )
            if OUTPUT_SHM.exists():
                self._output_mmap = np.memmap(
                    OUTPUT_SHM, dtype=np.float32, mode='r', shape=OUTPUT_SHAPE
                )
            logger.info("Fast shared memory initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize shared memory: {e}")

    def _check_service(self) -> bool:
        """Check if host TRT service is available."""
        now = time.time()
        if now - self._last_check < self._check_interval:
            return self._service_available

        self._last_check = now

        if STATUS_SHM.exists():
            status = STATUS_SHM.read_text().strip()
            self._service_available = status.startswith(
                "ready"
            ) or status.startswith("complete")
            if self._service_available and self._input_mmap is None:
                self._init_shared_memory()
        else:
            self._service_available = False

        return self._service_available

    def inference(
        self,
        image: np.ndarray,
        return_confidence: bool = True,
        return_camera_params: bool = False,
    ) -> Dict[str, np.ndarray]:
        """Run inference via fast shared memory."""
        if not self._check_service() or self._input_mmap is None:
            if self.fallback_wrapper:
                return self.fallback_wrapper.inference(
                    image, return_confidence, return_camera_params
                )
            raise RuntimeError("Fast SHM service not available")

        try:
            return self._inference_via_memmap(image)
        except Exception as e:
            logger.warning(f"Fast SHM inference failed: {e}")
            if self.fallback_wrapper:
                return self.fallback_wrapper.inference(
                    image, return_confidence, return_camera_params
                )
            raise

    def _inference_via_memmap(self, image: np.ndarray) -> Dict[str, np.ndarray]:
        """Perform inference via memory-mapped shared memory."""
        # Preprocess image
        input_tensor = self._preprocess_image(image)

        # Write directly to memory map (no file I/O!)
        self._input_mmap[:] = input_tensor
        self._input_mmap.flush()

        # Signal request
        REQUEST_SHM.write_text(str(time.time()))

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if STATUS_SHM.exists():
                status = STATUS_SHM.read_text().strip()
                if status.startswith("complete"):
                    break
                elif status.startswith("error"):
                    raise RuntimeError(f"SHM service error: {status}")
            time.sleep(0.0005)  # 0.5ms poll
        else:
            raise TimeoutError(f"SHM inference timeout after {self.timeout}s")

        # CRITICAL: Re-open memmap to ensure we get fresh data after TRT write
        # This prevents reading stale cached data that causes color flickering
        self._output_mmap = np.memmap(
            OUTPUT_SHM, dtype=np.float32, mode='r', shape=OUTPUT_SHAPE
        )

        # Small sync delay to ensure TRT service has finished flushing
        time.sleep(0.001)  # 1ms sync delay

        # Read directly from memory map (no file I/O!)
        depth = np.array(self._output_mmap)

        while depth.ndim > 2:
            depth = depth[0]

        return {"depth": depth.astype(np.float32)}

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for TensorRT inference."""
        import cv2

        target_size = (518, 518)

        if image.shape[:2] != target_size:
            image = cv2.resize(image, target_size, interpolation=cv2.INTER_LINEAR)

        tensor = image.astype(np.float32) / 255.0

        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = (tensor - mean) / std

        tensor = tensor.transpose(2, 0, 1)
        tensor = tensor[np.newaxis, np.newaxis, ...]

        return tensor.astype(np.float32)

    @property
    def is_service_available(self) -> bool:
        """Check if fast SHM service is available."""
        return self._check_service()

    def get_gpu_memory_usage(self) -> Optional[Dict[str, float]]:
        """GPU memory managed by host service."""
        return None

    def clear_cache(self) -> None:
        """No-op for shared memory inference."""
        pass


class DA3InferenceWrapper:
    """
    PyTorch wrapper for Depth Anything 3 model inference.

    WARNING: This backend is for DEVELOPMENT/TESTING ONLY.
    For production deployment, use SharedMemoryInferenceFast with the host
    TensorRT service (./run.sh) which provides 8-10x better performance.

    This class handles model loading from Hugging Face Hub, inference execution,
    and provides utilities for depth map processing with proper error handling
    and resource management.

    Performance comparison (Jetson Orin NX 16GB):
    - PyTorch (this class): ~5 FPS, ~193ms latency
    - TensorRT (production): 23+ FPS, ~23ms latency
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
        self._use_raw_model = False  # True when using DepthAnything3Net directly

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

            # Fallback: Load model directly using registry (avoids api.py)
            # This avoids pycolmap/moviepy/open3d dependencies in api.py
            from huggingface_hub import hf_hub_download
            from safetensors.torch import load_file
            import json
            from depth_anything_3.cfg import create_object, load_config
            from depth_anything_3.registry import MODEL_REGISTRY

            logger.info(
                f"Loading model '{self.model_name}' directly from HuggingFace..."
            )

            # Download config to get model_name for registry
            config_path = hf_hub_download(
                repo_id=self.model_name,
                filename="config.json",
                cache_dir=self.cache_dir,
            )

            # Load HF config to get registry model name
            with open(config_path) as f:
                hf_config = json.load(f)

            # Map HuggingFace model to registry name (e.g., "da3-base")
            registry_name = hf_config.get("model_name", "da3-base")
            if registry_name not in MODEL_REGISTRY:
                # Fallback mapping for common names
                name_map = {
                    "DA3-BASE": "da3-base",
                    "DA3-SMALL": "da3-small",
                    "DA3-LARGE": "da3-large",
                    "DA3-GIANT": "da3-giant",
                }
                registry_name = name_map.get(
                    registry_name.upper(), registry_name.lower()
                )

            # Create model from registry config
            config = load_config(MODEL_REGISTRY[registry_name])
            self._model = create_object(config)

            # Download and load weights
            weights_path = hf_hub_download(
                repo_id=self.model_name,
                filename="model.safetensors",
                cache_dir=self.cache_dir,
            )
            state_dict = load_file(weights_path)

            # Strip "model." prefix from keys if present
            # (HF safetensors uses "model.backbone..." but the model expects "backbone...")
            cleaned = {}
            for k, v in state_dict.items():
                new_key = k.removeprefix("model.")
                cleaned[new_key] = v
            self._model.load_state_dict(cleaned, strict=False)

            # Move to device and set eval mode
            self._model = self._model.to(device=self.device)
            self._model.eval()
            self._use_raw_model = True

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
            if self._use_raw_model:
                # Direct forward pass for DepthAnything3Net (fallback path)
                import cv2

                # Preprocess: resize, normalize, to tensor
                target_size = (518, 518)
                input_img = cv2.resize(image, target_size, interpolation=cv2.INTER_LINEAR)
                tensor = input_img.astype(np.float32) / 255.0
                mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
                std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
                tensor = (tensor - mean) / std
                tensor = tensor.transpose(2, 0, 1)  # HWC -> CHW
                # DA3 expects (B, N, C, H, W) where N=num_images=1
                input_tensor = torch.from_numpy(tensor[np.newaxis, np.newaxis, ...]).to(self.device)

                with torch.no_grad():
                    prediction = self._model(input_tensor)

                # prediction keys: 'depth', 'depth_conf', 'extrinsics', 'intrinsics'
                depth = prediction["depth"][0, 0].cpu().numpy()
                result = {"depth": depth.astype(np.float32)}

                if return_confidence and "depth_conf" in prediction:
                    result["confidence"] = prediction["depth_conf"][0, 0].cpu().numpy().astype(np.float32)

                if return_camera_params:
                    if "extrinsics" in prediction:
                        result["extrinsics"] = prediction["extrinsics"][0, 0].cpu().numpy().astype(np.float32)
                    if "intrinsics" in prediction:
                        result["intrinsics"] = prediction["intrinsics"][0, 0].cpu().numpy().astype(np.float32)
            else:
                # DA3 API path (full installation with DepthAnything3.inference())
                pil_image = Image.fromarray(image)

                with torch.no_grad():
                    prediction = self._model.inference([pil_image])

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
