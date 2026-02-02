"""
Utility functions for depth map processing and visualization.

This module provides helper functions for depth map normalization,
colorization, and image format conversions.
"""

from typing import Tuple, Optional
import numpy as np
import cv2


def normalize_depth(
    depth: np.ndarray, min_val: Optional[float] = None, max_val: Optional[float] = None
) -> np.ndarray:
    """
    Normalize depth map to [0, 1] range.

    Args:
        depth: Input depth map (H, W) as float32
        min_val: Optional minimum value for normalization (uses depth.min() if None)
        max_val: Optional maximum value for normalization (uses depth.max() if None)

    Returns:
        Normalized depth map in [0, 1] range
    """
    if min_val is None:
        min_val = np.min(depth)
    if max_val is None:
        max_val = np.max(depth)

    # Avoid division by zero
    if max_val - min_val < 1e-8:
        return np.zeros_like(depth)

    normalized = (depth - min_val) / (max_val - min_val)
    return np.clip(normalized, 0.0, 1.0).astype(np.float32)


def colorize_depth(
    depth: np.ndarray, colormap: str = "turbo", normalize: bool = True
) -> np.ndarray:
    """
    Colorize depth map for visualization.

    Args:
        depth: Input depth map (H, W) as float32
        colormap: OpenCV colormap name
            ('turbo', 'viridis', 'plasma', 'magma', 'jet', etc.)
        normalize: Whether to normalize depth to [0, 1] before colorization

    Returns:
        Colorized depth map (H, W, 3) as BGR uint8

    Raises:
        ValueError: If colormap name is invalid
    """
    # Map colormap names to OpenCV constants
    colormap_dict = {
        "turbo": cv2.COLORMAP_TURBO,
        "viridis": cv2.COLORMAP_VIRIDIS,
        "plasma": cv2.COLORMAP_PLASMA,
        "magma": cv2.COLORMAP_MAGMA,
        "jet": cv2.COLORMAP_JET,
        "hot": cv2.COLORMAP_HOT,
        "cool": cv2.COLORMAP_COOL,
        "spring": cv2.COLORMAP_SPRING,
        "summer": cv2.COLORMAP_SUMMER,
        "autumn": cv2.COLORMAP_AUTUMN,
        "winter": cv2.COLORMAP_WINTER,
        "bone": cv2.COLORMAP_BONE,
        "hsv": cv2.COLORMAP_HSV,
        "parula": cv2.COLORMAP_PARULA,
        "inferno": cv2.COLORMAP_INFERNO,
    }

    if colormap.lower() not in colormap_dict:
        raise ValueError(
            f"Invalid colormap '{colormap}'. "
            f"Valid options: {list(colormap_dict.keys())}"
        )

    # Normalize if requested
    if normalize:
        depth_normalized = normalize_depth(depth)
    else:
        depth_normalized = depth

    # Convert to uint8 for colormap application
    depth_uint8 = (depth_normalized * 255).astype(np.uint8)

    # Apply colormap
    colored = cv2.applyColorMap(depth_uint8, colormap_dict[colormap.lower()])

    return colored


def resize_image(
    image: np.ndarray,
    target_size: Tuple[int, int],
    keep_aspect_ratio: bool = True,
    interpolation: int = cv2.INTER_LINEAR,
) -> np.ndarray:
    """
    Resize image to target size.

    Args:
        image: Input image (H, W, C) or (H, W)
        target_size: Target size as (height, width)
        keep_aspect_ratio: Whether to maintain aspect ratio (pads with zeros if True)
        interpolation: OpenCV interpolation method

    Returns:
        Resized image
    """
    h, w = image.shape[:2]
    target_h, target_w = target_size

    if keep_aspect_ratio:
        # Calculate scaling factor to fit within target size
        scale = min(target_w / w, target_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)

        # Resize image
        resized = cv2.resize(image, (new_w, new_h), interpolation=interpolation)

        # Create padded image
        if len(image.shape) == 3:
            padded = np.zeros((target_h, target_w, image.shape[2]), dtype=image.dtype)
        else:
            padded = np.zeros((target_h, target_w), dtype=image.dtype)

        # Center the resized image in padded image
        y_offset = (target_h - new_h) // 2
        x_offset = (target_w - new_w) // 2
        padded[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized

        return padded
    else:
        # Direct resize without maintaining aspect ratio
        return cv2.resize(image, (target_w, target_h), interpolation=interpolation)


def depth_to_meters(
    depth: np.ndarray, depth_range: Tuple[float, float] = (0.1, 10.0)
) -> np.ndarray:
    """
    Convert normalized depth [0, 1] to metric depth in meters.

    Args:
        depth: Normalized depth map [0, 1]
        depth_range: Physical depth range as (min_meters, max_meters)

    Returns:
        Depth map in meters
    """
    min_depth, max_depth = depth_range
    return depth * (max_depth - min_depth) + min_depth


def compute_confidence_mask(
    confidence: np.ndarray, threshold: float = 0.5
) -> np.ndarray:
    """
    Compute binary confidence mask.

    Args:
        confidence: Confidence map (H, W) with values in [0, 1]
        threshold: Confidence threshold for binary mask

    Returns:
        Binary mask (H, W) as uint8 (0 or 255)
    """
    mask = (confidence >= threshold).astype(np.uint8) * 255
    return mask


class PerformanceMetrics:
    """
    Performance metrics tracker for monitoring inference performance.

    Tracks timing, confidence, and GPU memory usage for depth estimation.
    """

    def __init__(self, window_size: int = 30):
        """
        Initialize performance metrics tracker.

        Args:
            window_size: Number of samples for moving average
        """
        self.window_size = window_size
        self.inference_times = []
        self.total_times = []
        self.confidence_values = []
        self.frame_count = 0
        self._gpu_mem_allocated = 0.0
        self._gpu_mem_reserved = 0.0

    def update(
        self,
        inference_time: float,
        total_time: float,
        confidence: Optional[float] = None,
    ) -> None:
        """
        Update metrics with new timing measurements.

        Args:
            inference_time: Time spent in inference (seconds)
            total_time: Total processing time (seconds)
            confidence: Optional mean confidence value [0, 1]
        """
        self.inference_times.append(inference_time)
        self.total_times.append(total_time)
        self.frame_count += 1

        if confidence is not None:
            self.confidence_values.append(confidence)
            if len(self.confidence_values) > self.window_size:
                self.confidence_values.pop(0)

        # Keep only last window_size samples
        if len(self.inference_times) > self.window_size:
            self.inference_times.pop(0)
        if len(self.total_times) > self.window_size:
            self.total_times.pop(0)

        # Update GPU memory stats
        self._update_gpu_memory()

    def _update_gpu_memory(self) -> None:
        """Update GPU memory statistics if torch is available."""
        try:
            import torch

            if torch.cuda.is_available():
                self._gpu_mem_allocated = (
                    torch.cuda.memory_allocated() / 1024 / 1024
                )  # MB
                self._gpu_mem_reserved = (
                    torch.cuda.memory_reserved() / 1024 / 1024
                )  # MB
        except (ImportError, RuntimeError):
            pass

    def get_metrics(self) -> dict:
        """
        Get current performance metrics.

        Returns:
            Dictionary with performance metrics including:
            - avg_inference_ms: Average inference time in milliseconds
            - avg_total_ms: Average total processing time in milliseconds
            - fps: Frames per second
            - frame_count: Total frames processed
            - avg_confidence: Average confidence (if tracked)
            - gpu_mem_allocated_mb: GPU memory allocated in MB
            - gpu_mem_reserved_mb: GPU memory reserved in MB
        """
        if not self.inference_times:
            return {
                "avg_inference_ms": 0.0,
                "avg_total_ms": 0.0,
                "fps": 0.0,
                "frame_count": 0,
                "avg_confidence": 0.0,
                "gpu_mem_allocated_mb": 0.0,
                "gpu_mem_reserved_mb": 0.0,
            }

        avg_inference = np.mean(self.inference_times) * 1000  # Convert to ms
        avg_total = np.mean(self.total_times) * 1000
        fps = 1.0 / np.mean(self.total_times) if np.mean(self.total_times) > 0 else 0.0
        avg_confidence = np.mean(self.confidence_values) if self.confidence_values else 0.0

        return {
            "avg_inference_ms": avg_inference,
            "avg_total_ms": avg_total,
            "fps": fps,
            "frame_count": self.frame_count,
            "avg_confidence": avg_confidence,
            "gpu_mem_allocated_mb": self._gpu_mem_allocated,
            "gpu_mem_reserved_mb": self._gpu_mem_reserved,
        }

    def format_string(self) -> str:
        """
        Format metrics as a human-readable string.

        Returns:
            Formatted string with performance metrics
        """
        metrics = self.get_metrics()
        lines = [
            f"FPS: {metrics['fps']:.1f}",
            f"Inference: {metrics['avg_inference_ms']:.1f} ms",
            f"Total: {metrics['avg_total_ms']:.1f} ms",
            f"Frames: {metrics['frame_count']}",
        ]

        if metrics["avg_confidence"] > 0:
            lines.append(f"Confidence: {metrics['avg_confidence']:.2f}")

        if metrics["gpu_mem_allocated_mb"] > 0:
            lines.append(
                f"GPU Memory: {metrics['gpu_mem_allocated_mb']:.0f} / "
                f"{metrics['gpu_mem_reserved_mb']:.0f} MB"
            )

        return " | ".join(lines)

    def to_json(self) -> str:
        """
        Convert metrics to JSON string.

        Returns:
            JSON-formatted string with all metrics
        """
        import json

        metrics = self.get_metrics()
        return json.dumps(metrics)

    def reset(self) -> None:
        """Reset all metrics."""
        self.inference_times.clear()
        self.total_times.clear()
        self.confidence_values.clear()
        self.frame_count = 0
        self._gpu_mem_allocated = 0.0
        self._gpu_mem_reserved = 0.0
