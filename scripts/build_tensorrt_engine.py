#!/usr/bin/env python3
"""
Build TensorRT Engine from Pre-exported ONNX Models.

This script downloads pre-exported ONNX models from HuggingFace and converts
them to TensorRT engines optimized for the target Jetson platform.

This approach bypasses the ONNX export issue (Issue #22) by using community
pre-exported ONNX models.

Requirements:
    - NVIDIA JetPack 6.x (includes TensorRT and trtexec)
    - huggingface_hub: pip install huggingface_hub

Usage:
    # Build FP16 engine for DA3-Small (recommended)
    python build_tensorrt_engine.py --model da3-small --precision fp16

    # Build INT8 engine (faster but may reduce accuracy)
    python build_tensorrt_engine.py --model da3-small --precision int8

    # Specify custom resolution
    python build_tensorrt_engine.py --model da3-small --resolution 518

    # List available models
    python build_tensorrt_engine.py --list-models

    # Auto-detect platform and build optimal engine
    python build_tensorrt_engine.py --auto
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# Add parent directory to path for imports
script_dir = Path(__file__).parent
repo_root = script_dir.parent
sys.path.insert(0, str(repo_root))


# ONNX model catalog - pre-exported models that bypass Issue #22
ONNX_MODELS = {
    "da3-small": {
        "hf_repo": "onnx-community/depth-anything-v3-small",
        "onnx_file": "onnx/model.onnx",
        "display_name": "Depth Anything 3 Small",
        "parameters": "30M",
        "default_resolution": 518,
        "supported_resolutions": [308, 518, 728],
    },
    "da3-base": {
        "hf_repo": "onnx-community/depth-anything-v3-base",
        "onnx_file": "onnx/model.onnx",
        "display_name": "Depth Anything 3 Base",
        "parameters": "100M",
        "default_resolution": 518,
        "supported_resolutions": [308, 518, 728],
    },
    "da3-large": {
        "hf_repo": "onnx-community/depth-anything-v3-large",
        "onnx_file": "onnx/model.onnx",
        "display_name": "Depth Anything 3 Large",
        "parameters": "350M",
        "default_resolution": 518,
        "supported_resolutions": [308, 518, 728, 1024],
    },
}

# Platform-specific TensorRT optimization settings
PLATFORM_CONFIGS = {
    "ORIN_NANO_4GB": {
        "max_workspace_mb": 512,
        "recommended_precision": "fp16",
        "recommended_resolution": 308,
        "dla_enabled": False,
    },
    "ORIN_NANO_8GB": {
        "max_workspace_mb": 1024,
        "recommended_precision": "fp16",
        "recommended_resolution": 308,
        "dla_enabled": False,
    },
    "ORIN_NX_8GB": {
        "max_workspace_mb": 1024,
        "recommended_precision": "fp16",
        "recommended_resolution": 308,
        "dla_enabled": True,
    },
    "ORIN_NX_16GB": {
        "max_workspace_mb": 2048,
        "recommended_precision": "fp16",
        "recommended_resolution": 518,
        "dla_enabled": True,
    },
    "AGX_ORIN_32GB": {
        "max_workspace_mb": 4096,
        "recommended_precision": "fp16",
        "recommended_resolution": 518,
        "dla_enabled": True,
    },
    "AGX_ORIN_64GB": {
        "max_workspace_mb": 8192,
        "recommended_precision": "fp16",
        "recommended_resolution": 518,
        "dla_enabled": True,
    },
    "X86_GPU": {
        "max_workspace_mb": 4096,
        "recommended_precision": "fp16",
        "recommended_resolution": 518,
        "dla_enabled": False,
    },
}


def detect_platform() -> Dict:
    """Detect the current Jetson platform."""
    try:
        from depth_anything_3_ros2.jetson_detector import detect_platform
        return detect_platform()
    except ImportError:
        pass

    # Fallback detection
    platform_info = {
        "platform": "UNKNOWN",
        "display_name": "Unknown Platform",
        "is_jetson": False,
    }

    # Check for Jetson
    try:
        with open("/etc/nv_tegra_release", "r") as f:
            content = f.read()
            platform_info["is_jetson"] = True

            # Parse L4T version
            if "R36" in content:
                platform_info["l4t_version"] = "36.x"
            elif "R35" in content:
                platform_info["l4t_version"] = "35.x"
    except FileNotFoundError:
        pass

    # Check device model
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read().strip()
            platform_info["device_model"] = model

            if "Orin Nano" in model:
                if "4GB" in model or "Developer Kit" in model:
                    platform_info["platform"] = "ORIN_NANO_8GB"
                else:
                    platform_info["platform"] = "ORIN_NANO_8GB"
                platform_info["display_name"] = "Jetson Orin Nano"
            elif "Orin NX" in model:
                if "16GB" in model:
                    platform_info["platform"] = "ORIN_NX_16GB"
                else:
                    platform_info["platform"] = "ORIN_NX_8GB"
                platform_info["display_name"] = "Jetson Orin NX"
            elif "AGX Orin" in model:
                if "64GB" in model:
                    platform_info["platform"] = "AGX_ORIN_64GB"
                else:
                    platform_info["platform"] = "AGX_ORIN_32GB"
                platform_info["display_name"] = "Jetson AGX Orin"
    except FileNotFoundError:
        pass

    # Fallback to GPU detection for x86
    if platform_info["platform"] == "UNKNOWN":
        try:
            import torch
            if torch.cuda.is_available():
                platform_info["platform"] = "X86_GPU"
                platform_info["display_name"] = f"x86 GPU ({torch.cuda.get_device_name(0)})"
        except ImportError:
            pass

    return platform_info


def download_onnx_model(model_key: str, output_dir: Path) -> Path:
    """
    Download pre-exported ONNX model from HuggingFace.

    Args:
        model_key: Model identifier (e.g., 'da3-small')
        output_dir: Directory to save the ONNX file

    Returns:
        Path to the downloaded ONNX file
    """
    if model_key not in ONNX_MODELS:
        raise ValueError(
            f"Unknown model: {model_key}. "
            f"Available: {list(ONNX_MODELS.keys())}"
        )

    model_info = ONNX_MODELS[model_key]

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface_hub not installed")
        print("Install with: pip install huggingface_hub")
        sys.exit(1)

    print(f"Downloading ONNX model: {model_info['display_name']}")
    print(f"  Repository: {model_info['hf_repo']}")

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        onnx_path = hf_hub_download(
            repo_id=model_info["hf_repo"],
            filename=model_info["onnx_file"],
            local_dir=output_dir,
        )
        print(f"  Downloaded: {onnx_path}")
        return Path(onnx_path)

    except Exception as e:
        print(f"ERROR: Failed to download ONNX model: {e}")
        print("\nAlternative: Download manually from HuggingFace:")
        print(f"  https://huggingface.co/{model_info['hf_repo']}")
        sys.exit(1)


def find_trtexec() -> Optional[str]:
    """Find the trtexec binary."""
    # Common locations for trtexec
    search_paths = [
        "/usr/src/tensorrt/bin/trtexec",
        "/usr/bin/trtexec",
        "/opt/tensorrt/bin/trtexec",
    ]

    # Check PATH first
    import shutil
    trtexec = shutil.which("trtexec")
    if trtexec:
        return trtexec

    # Check known locations
    for path in search_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path

    return None


def build_tensorrt_engine(
    onnx_path: Path,
    output_path: Path,
    precision: str = "fp16",
    resolution: int = 518,
    max_workspace_mb: int = 2048,
    dla_core: Optional[int] = None,
    verbose: bool = False,
) -> bool:
    """
    Build TensorRT engine from ONNX model using trtexec.

    Args:
        onnx_path: Path to the ONNX model
        output_path: Path for the output .engine file
        precision: Precision mode ('fp32', 'fp16', 'int8')
        resolution: Input resolution (height and width)
        max_workspace_mb: Maximum workspace size in MB
        dla_core: DLA core to use (None for GPU only)
        verbose: Enable verbose output

    Returns:
        True if successful, False otherwise
    """
    trtexec = find_trtexec()
    if trtexec is None:
        print("ERROR: trtexec not found")
        print("On Jetson, trtexec is included in JetPack.")
        print("Ensure JetPack 6.x is installed correctly.")
        return False

    print(f"\nBuilding TensorRT engine:")
    print(f"  ONNX model: {onnx_path}")
    print(f"  Output: {output_path}")
    print(f"  Precision: {precision}")
    print(f"  Resolution: {resolution}x{resolution}")
    print(f"  Workspace: {max_workspace_mb} MB")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build trtexec command
    cmd = [
        trtexec,
        f"--onnx={onnx_path}",
        f"--saveEngine={output_path}",
        f"--workspace={max_workspace_mb}",
    ]

    # Set precision flags
    if precision == "fp16":
        cmd.append("--fp16")
    elif precision == "int8":
        cmd.extend(["--fp16", "--int8"])
        # INT8 requires calibration for best accuracy
        print("  Note: INT8 without calibration may reduce accuracy")

    # Set input shape (batch=1, channels=3, height, width)
    cmd.append(f"--shapes=input:1x3x{resolution}x{resolution}")

    # DLA support (Jetson specific)
    if dla_core is not None:
        cmd.extend([
            f"--useDLACore={dla_core}",
            "--allowGPUFallback",
        ])
        print(f"  DLA Core: {dla_core}")

    # Verbose output
    if verbose:
        cmd.append("--verbose")

    print(f"\nRunning trtexec...")
    print(f"  Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=not verbose,
            text=True,
            check=True,
        )

        if result.returncode == 0:
            print(f"\nEngine built successfully: {output_path}")
            print(f"  Size: {output_path.stat().st_size / (1024*1024):.2f} MB")
            return True

    except subprocess.CalledProcessError as e:
        print(f"\nERROR: trtexec failed with exit code {e.returncode}")
        if e.stdout:
            print(f"STDOUT:\n{e.stdout}")
        if e.stderr:
            print(f"STDERR:\n{e.stderr}")
        return False

    except Exception as e:
        print(f"\nERROR: Failed to run trtexec: {e}")
        return False

    return False


def get_engine_filename(
    model_key: str,
    precision: str,
    resolution: int,
    platform: str,
) -> str:
    """Generate standardized engine filename."""
    return f"{model_key}_{precision}_{resolution}x{resolution}_{platform}.engine"


def list_available_models():
    """Print available models."""
    print("\nAvailable ONNX Models:")
    print("-" * 60)

    for key, info in ONNX_MODELS.items():
        print(f"\n  {key}:")
        print(f"    Name: {info['display_name']}")
        print(f"    Parameters: {info['parameters']}")
        print(f"    HuggingFace: {info['hf_repo']}")
        print(f"    Resolutions: {info['supported_resolutions']}")

    print("\n" + "-" * 60)


def auto_build(output_dir: Path, verbose: bool = False) -> bool:
    """
    Auto-detect platform and build optimal TensorRT engine.

    Args:
        output_dir: Directory to save engines
        verbose: Enable verbose output

    Returns:
        True if successful
    """
    print("Auto-detecting platform and building optimal engine...")

    # Detect platform
    platform_info = detect_platform()
    platform = platform_info.get("platform", "UNKNOWN")

    print(f"\nDetected Platform: {platform_info.get('display_name', 'Unknown')}")

    if platform not in PLATFORM_CONFIGS:
        print(f"WARNING: Unknown platform '{platform}', using default settings")
        platform_config = PLATFORM_CONFIGS["X86_GPU"]
    else:
        platform_config = PLATFORM_CONFIGS[platform]

    # Get recommended settings
    precision = platform_config["recommended_precision"]
    resolution = platform_config["recommended_resolution"]
    workspace = platform_config["max_workspace_mb"]

    print(f"\nRecommended settings for {platform}:")
    print(f"  Precision: {precision}")
    print(f"  Resolution: {resolution}x{resolution}")
    print(f"  Workspace: {workspace} MB")

    # Use DA3-Small as default (best balance for Jetson)
    model_key = "da3-small"

    # Download ONNX model
    onnx_dir = output_dir / "onnx"
    onnx_path = download_onnx_model(model_key, onnx_dir)

    # Build engine
    engine_name = get_engine_filename(model_key, precision, resolution, platform)
    engine_path = output_dir / "tensorrt" / engine_name

    success = build_tensorrt_engine(
        onnx_path=onnx_path,
        output_path=engine_path,
        precision=precision,
        resolution=resolution,
        max_workspace_mb=workspace,
        verbose=verbose,
    )

    if success:
        print("\n" + "=" * 60)
        print("ENGINE BUILD COMPLETE")
        print("=" * 60)
        print(f"\nEngine saved to: {engine_path}")
        print("\nTo use in ROS2:")
        print(f"  ros2 launch depth_anything_3_ros2 depth_anything_3_optimized.launch.py \\")
        print(f"    backend:=tensorrt_native \\")
        print(f"    trt_model_path:={engine_path.absolute()}")

    return success


def main():
    parser = argparse.ArgumentParser(
        description="Build TensorRT engine from pre-exported ONNX models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--model", "-m",
        type=str,
        choices=list(ONNX_MODELS.keys()),
        default="da3-small",
        help="Model to build (default: da3-small)",
    )
    parser.add_argument(
        "--precision", "-p",
        type=str,
        choices=["fp32", "fp16", "int8"],
        default="fp16",
        help="Precision mode (default: fp16)",
    )
    parser.add_argument(
        "--resolution", "-r",
        type=int,
        default=None,
        help="Input resolution (default: model-specific)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=str(repo_root / "models"),
        help="Output directory for models (default: ./models)",
    )
    parser.add_argument(
        "--workspace",
        type=int,
        default=2048,
        help="Max workspace size in MB (default: 2048)",
    )
    parser.add_argument(
        "--dla-core",
        type=int,
        default=None,
        help="DLA core to use (Jetson only, default: GPU only)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-detect platform and build optimal engine",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip ONNX download (use existing file)",
    )
    parser.add_argument(
        "--onnx-path",
        type=str,
        default=None,
        help="Path to existing ONNX file (skips download)",
    )

    args = parser.parse_args()

    # List models
    if args.list_models:
        list_available_models()
        sys.exit(0)

    output_dir = Path(args.output_dir)

    # Auto mode
    if args.auto:
        success = auto_build(output_dir, args.verbose)
        sys.exit(0 if success else 1)

    # Manual mode
    model_info = ONNX_MODELS[args.model]

    # Determine resolution
    resolution = args.resolution
    if resolution is None:
        resolution = model_info["default_resolution"]

    # Validate resolution
    if resolution not in model_info["supported_resolutions"]:
        print(f"WARNING: Resolution {resolution} not in recommended list")
        print(f"  Recommended: {model_info['supported_resolutions']}")

    # Get or download ONNX model
    if args.onnx_path:
        onnx_path = Path(args.onnx_path)
        if not onnx_path.exists():
            print(f"ERROR: ONNX file not found: {onnx_path}")
            sys.exit(1)
    elif args.skip_download:
        onnx_path = output_dir / "onnx" / model_info["onnx_file"]
        if not onnx_path.exists():
            print(f"ERROR: ONNX file not found: {onnx_path}")
            print("Run without --skip-download to download the model")
            sys.exit(1)
    else:
        onnx_dir = output_dir / "onnx"
        onnx_path = download_onnx_model(args.model, onnx_dir)

    # Detect platform for filename
    platform_info = detect_platform()
    platform = platform_info.get("platform", "unknown")

    # Generate output filename
    engine_name = get_engine_filename(
        args.model, args.precision, resolution, platform
    )
    engine_path = output_dir / "tensorrt" / engine_name

    # Build engine
    success = build_tensorrt_engine(
        onnx_path=onnx_path,
        output_path=engine_path,
        precision=args.precision,
        resolution=resolution,
        max_workspace_mb=args.workspace,
        dla_core=args.dla_core,
        verbose=args.verbose,
    )

    if success:
        print("\n" + "=" * 60)
        print("ENGINE BUILD COMPLETE")
        print("=" * 60)
        print(f"\nEngine saved to: {engine_path}")
        print("\nTo use in ROS2:")
        print(f"  ros2 launch depth_anything_3_ros2 depth_anything_3_optimized.launch.py \\")
        print(f"    backend:=tensorrt_native \\")
        print(f"    trt_model_path:={engine_path.absolute()}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
