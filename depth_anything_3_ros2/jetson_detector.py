"""
Hardware detection module for NVIDIA Jetson and GPU platforms.

This module provides functions to detect the current hardware platform,
available VRAM, JetPack version, and provide optimal model recommendations
for Depth Anything 3 deployment.
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


# Platform identification constants
PLATFORM_ORIN_NANO_4GB = "ORIN_NANO_4GB"
PLATFORM_ORIN_NANO_8GB = "ORIN_NANO_8GB"
PLATFORM_ORIN_NX_8GB = "ORIN_NX_8GB"
PLATFORM_ORIN_NX_16GB = "ORIN_NX_16GB"
PLATFORM_AGX_ORIN_32GB = "AGX_ORIN_32GB"
PLATFORM_AGX_ORIN_64GB = "AGX_ORIN_64GB"
PLATFORM_XAVIER_NX = "XAVIER_NX"
PLATFORM_AGX_XAVIER = "AGX_XAVIER"
PLATFORM_X86_GPU = "X86_GPU"
PLATFORM_CPU_ONLY = "CPU_ONLY"
PLATFORM_UNKNOWN = "UNKNOWN"

# RAM thresholds for Jetson platform identification (in GB)
JETSON_RAM_THRESHOLDS = {
    4: [PLATFORM_ORIN_NANO_4GB],
    8: [PLATFORM_ORIN_NANO_8GB, PLATFORM_ORIN_NX_8GB],
    16: [PLATFORM_ORIN_NX_16GB],
    32: [PLATFORM_AGX_ORIN_32GB],
    64: [PLATFORM_AGX_ORIN_64GB],
}


def is_jetson() -> bool:
    """
    Check if running on an NVIDIA Jetson platform.

    Returns:
        True if running on Jetson, False otherwise.
    """
    # Check for Jetson-specific file
    if Path("/etc/nv_tegra_release").exists():
        return True

    # Check device tree model (Linux)
    device_tree_model = Path("/proc/device-tree/model")
    if device_tree_model.exists():
        try:
            model = device_tree_model.read_text().lower()
            if "jetson" in model or "tegra" in model:
                return True
        except (OSError, IOError):
            pass

    return False


def get_device_model() -> str:
    """
    Get the device model name from the device tree.

    Returns:
        Device model string or "Unknown" if not available.
    """
    device_tree_model = Path("/proc/device-tree/model")
    if device_tree_model.exists():
        try:
            # Read and strip null bytes
            model = device_tree_model.read_text().replace("\x00", "").strip()
            return model
        except (OSError, IOError) as e:
            logger.warning(f"Failed to read device model: {e}")

    return "Unknown"


def get_l4t_version() -> Optional[str]:
    """
    Get the Linux for Tegra (L4T) version.

    Returns:
        L4T version string (e.g., "r36.4.0") or None if not available.
    """
    tegra_release = Path("/etc/nv_tegra_release")
    if not tegra_release.exists():
        return None

    try:
        content = tegra_release.read_text()
        # Parse: "# R36 (release), REVISION: 4.0, ..."
        match = re.search(r"R(\d+).*REVISION:\s*(\d+(?:\.\d+)?)", content)
        if match:
            major = match.group(1)
            revision = match.group(2)
            return f"r{major}.{revision}"
    except (OSError, IOError) as e:
        logger.warning(f"Failed to read L4T version: {e}")

    return None


def get_jetpack_version() -> Optional[str]:
    """
    Get the JetPack version.

    Returns:
        JetPack version string (e.g., "6.2") or None if not available.
    """
    # L4T to JetPack version mapping
    l4t_to_jetpack = {
        "r36.4": "6.2",
        "r36.3": "6.1",
        "r36.2": "6.0",
        "r35.6": "5.1.4",
        "r35.5": "5.1.3",
        "r35.4": "5.1.2",
        "r35.3": "5.1.1",
        "r35.2": "5.1",
        "r35.1": "5.0.2",
        "r34.1": "5.0.1",
        "r32.7": "4.6.6",
        "r32.6": "4.6.1",
    }

    l4t = get_l4t_version()
    if l4t:
        # Try exact match first, then prefix match
        for l4t_prefix, jetpack in l4t_to_jetpack.items():
            if l4t.startswith(l4t_prefix):
                return jetpack

    # Fallback: check dpkg for nvidia-jetpack package
    try:
        import subprocess

        result = subprocess.run(
            ["dpkg", "-l", "nvidia-jetpack"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse output for version
            for line in result.stdout.split("\n"):
                if "nvidia-jetpack" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2].split("-")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return None


def get_total_ram_gb() -> float:
    """
    Get total system RAM in gigabytes.

    Returns:
        Total RAM in GB.
    """
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            content = meminfo.read_text()
            match = re.search(r"MemTotal:\s*(\d+)\s*kB", content)
            if match:
                kb = int(match.group(1))
                return kb / (1024 * 1024)
        except (OSError, IOError) as e:
            logger.warning(f"Failed to read /proc/meminfo: {e}")

    # Fallback: use psutil if available
    try:
        import psutil

        return psutil.virtual_memory().total / (1024**3)
    except ImportError:
        pass

    return 0.0


def get_gpu_memory_mb() -> int:
    """
    Get total GPU memory in megabytes.

    For Jetson devices with unified memory, this returns total system RAM
    as GPU memory is shared with CPU.

    Returns:
        GPU memory in MB, or 0 if not available.
    """
    try:
        import torch

        if torch.cuda.is_available():
            device = torch.cuda.current_device()
            total = torch.cuda.get_device_properties(device).total_memory
            return int(total / (1024 * 1024))
    except ImportError:
        pass

    # Fallback for Jetson: use total RAM (unified memory)
    if is_jetson():
        ram_gb = get_total_ram_gb()
        return int(ram_gb * 1024)

    return 0


def get_available_gpu_memory_mb() -> int:
    """
    Get currently available GPU memory in megabytes.

    Returns:
        Available GPU memory in MB, or 0 if not available.
    """
    try:
        import torch

        if torch.cuda.is_available():
            device = torch.cuda.current_device()
            total = torch.cuda.get_device_properties(device).total_memory
            allocated = torch.cuda.memory_allocated(device)
            reserved = torch.cuda.memory_reserved(device)
            return int((total - max(allocated, reserved)) / (1024 * 1024))
    except ImportError:
        pass

    return get_gpu_memory_mb()


def get_gpu_name() -> str:
    """
    Get the GPU device name.

    Returns:
        GPU name string or "Unknown" if not available.
    """
    try:
        import torch

        if torch.cuda.is_available():
            device = torch.cuda.current_device()
            return torch.cuda.get_device_name(device)
    except ImportError:
        pass

    # Fallback for Jetson
    if is_jetson():
        model = get_device_model()
        if model != "Unknown":
            return f"Tegra ({model})"

    return "Unknown"


def identify_jetson_platform(ram_gb: float, model_name: str) -> str:
    """
    Identify the specific Jetson platform based on RAM and model name.

    Args:
        ram_gb: Total system RAM in GB.
        model_name: Device model name string.

    Returns:
        Platform identifier constant.
    """
    model_lower = model_name.lower()

    # AGX Orin detection
    if "agx" in model_lower and "orin" in model_lower:
        if ram_gb >= 56:
            return PLATFORM_AGX_ORIN_64GB
        elif ram_gb >= 24:
            return PLATFORM_AGX_ORIN_32GB

    # Orin NX detection
    if "orin" in model_lower and ("nx" in model_lower or "p3767" in model_lower):
        if ram_gb >= 12:
            return PLATFORM_ORIN_NX_16GB
        else:
            return PLATFORM_ORIN_NX_8GB

    # Orin Nano detection
    if "orin" in model_lower and "nano" in model_lower:
        if ram_gb >= 6:
            return PLATFORM_ORIN_NANO_8GB
        else:
            return PLATFORM_ORIN_NANO_4GB

    # Xavier NX detection
    if "xavier" in model_lower and "nx" in model_lower:
        return PLATFORM_XAVIER_NX

    # AGX Xavier detection
    if "agx" in model_lower and "xavier" in model_lower:
        return PLATFORM_AGX_XAVIER

    # Generic Orin detection by RAM
    if "orin" in model_lower:
        if ram_gb >= 56:
            return PLATFORM_AGX_ORIN_64GB
        elif ram_gb >= 24:
            return PLATFORM_AGX_ORIN_32GB
        elif ram_gb >= 12:
            return PLATFORM_ORIN_NX_16GB
        elif ram_gb >= 6:
            return PLATFORM_ORIN_NX_8GB
        else:
            return PLATFORM_ORIN_NANO_4GB

    return PLATFORM_UNKNOWN


def detect_platform() -> Dict[str, Any]:
    """
    Detect the current hardware platform and return comprehensive info.

    Returns:
        Dictionary containing:
        - platform: Platform identifier constant
        - display_name: Human-readable platform name
        - is_jetson: Whether running on Jetson
        - device_model: Raw device model string
        - ram_gb: Total RAM in GB
        - gpu_memory_mb: Total GPU memory in MB
        - available_gpu_memory_mb: Available GPU memory in MB
        - gpu_name: GPU device name
        - jetpack_version: JetPack version (Jetson only)
        - l4t_version: L4T version (Jetson only)
        - cuda_available: Whether CUDA is available
    """
    info = {
        "platform": PLATFORM_UNKNOWN,
        "display_name": "Unknown Platform",
        "is_jetson": False,
        "device_model": "Unknown",
        "ram_gb": 0.0,
        "gpu_memory_mb": 0,
        "available_gpu_memory_mb": 0,
        "gpu_name": "Unknown",
        "jetpack_version": None,
        "l4t_version": None,
        "cuda_available": False,
    }

    # Check CUDA availability
    try:
        import torch

        info["cuda_available"] = torch.cuda.is_available()
    except ImportError:
        pass

    # Get basic system info
    info["ram_gb"] = round(get_total_ram_gb(), 1)
    info["device_model"] = get_device_model()
    info["gpu_memory_mb"] = get_gpu_memory_mb()
    info["available_gpu_memory_mb"] = get_available_gpu_memory_mb()
    info["gpu_name"] = get_gpu_name()

    # Check if Jetson
    if is_jetson():
        info["is_jetson"] = True
        info["jetpack_version"] = get_jetpack_version()
        info["l4t_version"] = get_l4t_version()

        # Identify specific Jetson platform
        platform = identify_jetson_platform(info["ram_gb"], info["device_model"])
        info["platform"] = platform

        # Set display name
        display_names = {
            PLATFORM_ORIN_NANO_4GB: "Jetson Orin Nano 4GB",
            PLATFORM_ORIN_NANO_8GB: "Jetson Orin Nano 8GB",
            PLATFORM_ORIN_NX_8GB: "Jetson Orin NX 8GB",
            PLATFORM_ORIN_NX_16GB: "Jetson Orin NX 16GB",
            PLATFORM_AGX_ORIN_32GB: "Jetson AGX Orin 32GB",
            PLATFORM_AGX_ORIN_64GB: "Jetson AGX Orin 64GB",
            PLATFORM_XAVIER_NX: "Jetson Xavier NX",
            PLATFORM_AGX_XAVIER: "Jetson AGX Xavier",
        }
        info["display_name"] = display_names.get(platform, f"Jetson ({platform})")

    elif info["cuda_available"]:
        # x86 with GPU
        info["platform"] = PLATFORM_X86_GPU
        gpu_name = info["gpu_name"]
        gpu_mem_gb = info["gpu_memory_mb"] / 1024
        info["display_name"] = f"x86 GPU ({gpu_name}, {gpu_mem_gb:.0f}GB)"

    else:
        # CPU only
        info["platform"] = PLATFORM_CPU_ONLY
        info["display_name"] = "CPU Only"

    logger.info(f"Detected platform: {info['display_name']}")
    return info


def get_platform_recommendations(platform: str) -> Dict[str, Any]:
    """
    Get recommended model configurations for a given platform.

    Args:
        platform: Platform identifier constant.

    Returns:
        Dictionary with recommended model name, resolution, and expected FPS.
    """
    # Default recommendations per platform
    recommendations = {
        PLATFORM_ORIN_NANO_4GB: {
            "recommended_model": "DA3-SMALL",
            "recommended_resolution": (308, 308),
            "max_model": "DA3-SMALL",
            "expected_fps": 30,
            "vram_budget_mb": 800,
        },
        PLATFORM_ORIN_NANO_8GB: {
            "recommended_model": "DA3-SMALL",
            "recommended_resolution": (308, 308),
            "max_model": "DA3-SMALL",
            "expected_fps": 42,
            "vram_budget_mb": 1500,
        },
        PLATFORM_ORIN_NX_8GB: {
            "recommended_model": "DA3-SMALL",
            "recommended_resolution": (308, 308),
            "max_model": "DA3-SMALL",
            "expected_fps": 42,
            "vram_budget_mb": 1500,
        },
        PLATFORM_ORIN_NX_16GB: {
            "recommended_model": "DA3-SMALL",
            "recommended_resolution": (518, 518),
            "max_model": "DA3-BASE",
            "expected_fps": 20,
            "vram_budget_mb": 4000,
        },
        PLATFORM_AGX_ORIN_32GB: {
            "recommended_model": "DA3-LARGE-1.1",
            "recommended_resolution": (518, 518),
            "max_model": "DA3-LARGE-1.1",
            "expected_fps": 50,
            "vram_budget_mb": 8000,
        },
        PLATFORM_AGX_ORIN_64GB: {
            "recommended_model": "DA3-LARGE-1.1",
            "recommended_resolution": (1024, 1024),
            "max_model": "DA3-GIANT-1.1",
            "expected_fps": 30,
            "vram_budget_mb": 16000,
        },
        PLATFORM_XAVIER_NX: {
            "recommended_model": "DA3-SMALL",
            "recommended_resolution": (308, 308),
            "max_model": "DA3-SMALL",
            "expected_fps": 20,
            "vram_budget_mb": 1500,
        },
        PLATFORM_AGX_XAVIER: {
            "recommended_model": "DA3-SMALL",
            "recommended_resolution": (518, 518),
            "max_model": "DA3-BASE",
            "expected_fps": 25,
            "vram_budget_mb": 4000,
        },
        PLATFORM_X86_GPU: {
            "recommended_model": "DA3-BASE",
            "recommended_resolution": (518, 518),
            "max_model": "DA3-LARGE-1.1",
            "expected_fps": 60,
            "vram_budget_mb": 8000,
        },
        PLATFORM_CPU_ONLY: {
            "recommended_model": "DA3-SMALL",
            "recommended_resolution": (308, 308),
            "max_model": "DA3-SMALL",
            "expected_fps": 2,
            "vram_budget_mb": 0,
        },
    }

    return recommendations.get(
        platform,
        {
            "recommended_model": "DA3-SMALL",
            "recommended_resolution": (308, 308),
            "max_model": "DA3-SMALL",
            "expected_fps": 10,
            "vram_budget_mb": 1000,
        },
    )


def check_model_compatibility(
    model_name: str, platform: str, vram_mb: Optional[int] = None
) -> Tuple[bool, str]:
    """
    Check if a model is compatible with a given platform.

    Args:
        model_name: Model identifier (e.g., "DA3-SMALL", "DA3-LARGE-1.1").
        platform: Platform identifier constant.
        vram_mb: Override VRAM value in MB (optional).

    Returns:
        Tuple of (is_compatible, reason_message).
    """
    # Model VRAM requirements (approximate, in MB)
    model_vram_requirements = {
        "DA3-SMALL": 1000,
        "DA3-BASE": 2000,
        "DA3-LARGE-1.1": 4000,
        "DA3-GIANT-1.1": 12000,
        "DA3METRIC-LARGE": 4000,
        "DA3MONO-LARGE": 4000,
    }

    required_vram = model_vram_requirements.get(model_name.upper())
    if required_vram is None:
        return False, f"Unknown model: {model_name}"

    # Get platform recommendations
    recommendations = get_platform_recommendations(platform)

    # Use override VRAM or platform budget
    available_vram = vram_mb if vram_mb is not None else recommendations["vram_budget_mb"]

    if required_vram > available_vram:
        return (
            False,
            f"{model_name} requires ~{required_vram}MB VRAM, "
            f"but only {available_vram}MB available",
        )

    # Warn about non-commercial license for larger models
    if model_name.upper() in ["DA3-BASE", "DA3-LARGE-1.1", "DA3-GIANT-1.1"]:
        return (
            True,
            f"Compatible. Note: {model_name} uses CC-BY-NC-4.0 license "
            f"(non-commercial use only)",
        )

    return True, f"Compatible with {model_name}"


def format_platform_info(info: Dict[str, Any]) -> str:
    """
    Format platform information as a human-readable string.

    Args:
        info: Platform info dictionary from detect_platform().

    Returns:
        Formatted multi-line string.
    """
    lines = [
        "=== Detected Hardware ===",
        f"  Platform: {info['display_name']}",
        f"  RAM: {info['ram_gb']:.1f} GB",
        f"  GPU Memory: {info['gpu_memory_mb']} MB",
        f"  GPU: {info['gpu_name']}",
    ]

    if info["is_jetson"]:
        if info["jetpack_version"]:
            lines.append(f"  JetPack: {info['jetpack_version']}")
        if info["l4t_version"]:
            lines.append(f"  L4T: {info['l4t_version']}")

    lines.append(f"  CUDA Available: {'Yes' if info['cuda_available'] else 'No'}")

    return "\n".join(lines)
