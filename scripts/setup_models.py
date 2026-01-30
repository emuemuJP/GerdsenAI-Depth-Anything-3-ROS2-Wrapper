#!/usr/bin/env python3
"""
Interactive setup script for Depth Anything 3 model selection.

This script detects hardware, displays model recommendations, and allows
users to select and download models optimized for their platform.

Usage:
    python setup_models.py                    # Interactive mode
    python setup_models.py --detect           # Show hardware info only
    python setup_models.py --list-models      # Show all available models
    python setup_models.py --model DA3-SMALL  # Non-interactive install
    python setup_models.py --vram 8192        # Override detected VRAM (MB)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add parent directory to path for imports
script_dir = Path(__file__).parent
repo_root = script_dir.parent
sys.path.insert(0, str(repo_root))

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)


def load_model_catalog() -> Dict[str, Any]:
    """Load the model catalog from YAML file."""
    catalog_paths = [
        repo_root / "config" / "model_catalog.yaml",
        Path("/app/config/model_catalog.yaml"),  # Docker path
        script_dir / "model_catalog.yaml",
    ]

    for path in catalog_paths:
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f)

    raise FileNotFoundError(
        "model_catalog.yaml not found. Searched paths:\n"
        + "\n".join(f"  - {p}" for p in catalog_paths)
    )


def get_platform_info() -> Dict[str, Any]:
    """Get platform information using jetson_detector."""
    try:
        from depth_anything_3_ros2.jetson_detector import detect_platform

        return detect_platform()
    except ImportError:
        # Fallback if module not available
        return create_fallback_platform_info()


def create_fallback_platform_info() -> Dict[str, Any]:
    """Create platform info without jetson_detector module."""
    info = {
        "platform": "UNKNOWN",
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

    # Try to detect CUDA
    try:
        import torch

        if torch.cuda.is_available():
            info["cuda_available"] = True
            device = torch.cuda.current_device()
            info["gpu_name"] = torch.cuda.get_device_name(device)
            total_mem = torch.cuda.get_device_properties(device).total_memory
            info["gpu_memory_mb"] = int(total_mem / (1024 * 1024))
            info["available_gpu_memory_mb"] = info["gpu_memory_mb"]
            info["platform"] = "X86_GPU"
            info["display_name"] = f"x86 GPU ({info['gpu_name']})"
    except ImportError:
        pass

    # Try to get RAM
    try:
        import psutil

        info["ram_gb"] = round(psutil.virtual_memory().total / (1024**3), 1)
    except ImportError:
        pass

    if not info["cuda_available"]:
        info["platform"] = "CPU_ONLY"
        info["display_name"] = "CPU Only"

    return info


def format_vram(mb: int) -> str:
    """Format VRAM value for display."""
    if mb >= 1024:
        return f"{mb / 1024:.1f}GB"
    return f"{mb}MB"


def get_model_status(
    model_id: str,
    model_info: Dict[str, Any],
    platform: str,
    vram_mb: int,
) -> tuple:
    """
    Determine model compatibility status.

    Returns:
        Tuple of (status_code, status_message)
        status_code: 'recommended', 'compatible', 'warning', 'incompatible'
    """
    required_vram = model_info.get("vram_required_mb", 0)
    recommended_for = model_info.get("recommended_for", [])
    compatible_with = model_info.get("compatible_with", [])

    # Check VRAM compatibility
    if required_vram > vram_mb and vram_mb > 0:
        return (
            "incompatible",
            f"Requires {format_vram(required_vram)}, only {format_vram(vram_mb)} available",
        )

    # Check if recommended
    if platform in recommended_for:
        return ("recommended", "RECOMMENDED for your hardware")

    # Check if compatible
    if "ALL" in compatible_with or platform in compatible_with:
        return ("compatible", "Compatible")

    # Check for potential warning
    if required_vram > 0 and vram_mb > 0 and required_vram > vram_mb * 0.7:
        return ("warning", f"May cause OOM at higher resolutions")

    return ("incompatible", "Not compatible with your platform")


def print_header():
    """Print script header."""
    print()
    print("=" * 60)
    print("     Depth Anything 3 - Model Setup")
    print("=" * 60)
    print()


def print_platform_info(info: Dict[str, Any]):
    """Print detected platform information."""
    print("Detected Hardware:")
    print(f"  Platform: {info['display_name']}")
    print(f"  RAM: {info['ram_gb']:.1f} GB")

    if info["gpu_memory_mb"] > 0:
        print(f"  GPU Memory: {format_vram(info['gpu_memory_mb'])}")
    if info["gpu_name"] and info["gpu_name"] != "Unknown":
        print(f"  GPU: {info['gpu_name']}")
    if info.get("jetpack_version"):
        print(f"  JetPack: {info['jetpack_version']}")
    if info.get("l4t_version"):
        print(f"  L4T: {info['l4t_version']}")

    print(f"  CUDA Available: {'Yes' if info['cuda_available'] else 'No'}")
    print()


def print_model_list(
    catalog: Dict[str, Any],
    platform: str,
    vram_mb: int,
    show_all: bool = False,
):
    """Print formatted list of available models."""
    models = catalog.get("models", {})

    print("Available Models:")
    print("-" * 60)

    # Group models by status
    recommended = []
    compatible = []
    warnings = []
    incompatible = []

    for model_id, model_info in models.items():
        status_code, status_msg = get_model_status(
            model_id, model_info, platform, vram_mb
        )
        entry = (model_id, model_info, status_code, status_msg)

        if status_code == "recommended":
            recommended.append(entry)
        elif status_code == "compatible":
            compatible.append(entry)
        elif status_code == "warning":
            warnings.append(entry)
        else:
            incompatible.append(entry)

    # Print in order
    for entries, show_marker in [
        (recommended, True),
        (compatible, True),
        (warnings, True),
        (incompatible, show_all),
    ]:
        for model_id, model_info, status_code, status_msg in entries:
            marker = {
                "recommended": "[*]",
                "compatible": "[+]",
                "warning": "[!]",
                "incompatible": "[ ]",
            }.get(status_code, "[ ]")

            params = model_info.get("parameters", "?")
            vram = format_vram(model_info.get("vram_required_mb", 0))
            license_info = model_info.get("license", "Unknown")

            print(f"  {marker} {model_id:<18} ({params}, {vram})")
            print(f"      License: {license_info}")
            print(f"      Status: {status_msg}")

            if model_info.get("description"):
                print(f"      {model_info['description']}")
            print()

    if not show_all and incompatible:
        print(f"  ({len(incompatible)} incompatible models hidden, use --all to show)")
        print()

    print("Legend: [*] Recommended  [+] Compatible  [!] May have issues  [ ] Incompatible")
    print()


def get_optimal_settings(
    model_id: str,
    model_info: Dict[str, Any],
    platform: str,
) -> Dict[str, Any]:
    """Get optimal settings for a model on a given platform."""
    optimal = model_info.get("optimal_resolutions", {})

    if platform in optimal:
        settings = optimal[platform].copy()
        settings["model_name"] = model_info.get("hf_id", model_id)
        return settings

    # Fallback to first available or defaults
    if optimal:
        first_platform = list(optimal.keys())[0]
        settings = optimal[first_platform].copy()
        settings["model_name"] = model_info.get("hf_id", model_id)
        return settings

    return {
        "model_name": model_info.get("hf_id", model_id),
        "height": 518,
        "width": 518,
        "fps_estimate": 10,
        "vram_usage_mb": model_info.get("vram_required_mb", 1000),
    }


def interactive_select(
    catalog: Dict[str, Any],
    platform: str,
    vram_mb: int,
) -> Optional[List[str]]:
    """Interactive model selection."""
    models = catalog.get("models", {})

    # Get available models
    available = []
    for model_id, model_info in models.items():
        status_code, _ = get_model_status(model_id, model_info, platform, vram_mb)
        if status_code in ["recommended", "compatible", "warning"]:
            available.append((model_id, model_info, status_code))

    if not available:
        print("No compatible models found for your hardware.")
        print("Consider using --vram to override detected VRAM if incorrect.")
        return None

    print("Select models to install (enter numbers separated by spaces):")
    print()

    for i, (model_id, model_info, status_code) in enumerate(available, 1):
        marker = {"recommended": "*", "compatible": "+", "warning": "!"}.get(
            status_code, " "
        )
        params = model_info.get("parameters", "?")
        print(f"  {i}. [{marker}] {model_id} ({params})")

    print()
    print("  a. Install all compatible models")
    print("  q. Quit without installing")
    print()

    while True:
        try:
            choice = input("Your choice: ").strip().lower()

            if choice == "q":
                return None

            if choice == "a":
                return [m[0] for m in available]

            # Parse numbers
            selections = []
            for part in choice.replace(",", " ").split():
                idx = int(part) - 1
                if 0 <= idx < len(available):
                    selections.append(available[idx][0])
                else:
                    print(f"Invalid number: {part}")
                    continue

            if selections:
                return selections

        except ValueError:
            print("Please enter valid numbers, 'a' for all, or 'q' to quit.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None


def download_model(model_id: str, hf_id: str) -> bool:
    """Download a model from HuggingFace."""
    print(f"Downloading {model_id}...")

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=hf_id)
        print(f"  Downloaded: {hf_id}")
        return True
    except ImportError:
        print("  Error: huggingface_hub not installed")
        print("  Run: pip install huggingface_hub")
        return False
    except Exception as e:
        print(f"  Error downloading {hf_id}: {e}")
        return False


def generate_user_config(
    model_id: str,
    settings: Dict[str, Any],
    output_path: Path,
) -> bool:
    """Generate user configuration file."""
    config = {
        "depth_anything_3": {
            "ros__parameters": {
                "model_name": settings.get("model_name", f"depth-anything/{model_id}"),
                "inference_height": settings.get("height", 518),
                "inference_width": settings.get("width", 518),
                "device": "cuda",
            }
        },
        "_meta": {
            "generated_by": "setup_models.py",
            "model_id": model_id,
            "expected_fps": settings.get("fps_estimate"),
            "expected_vram_mb": settings.get("vram_usage_mb"),
        },
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"Generated config: {output_path}")
        return True
    except Exception as e:
        print(f"Error writing config: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Setup Depth Anything 3 models for your hardware",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Show hardware detection info only",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List all available models",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all models including incompatible ones",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Model to install (non-interactive mode)",
    )
    parser.add_argument(
        "--vram",
        type=int,
        help="Override detected VRAM in MB",
    )
    parser.add_argument(
        "--platform",
        type=str,
        help="Override detected platform",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Skip downloading models",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="Skip generating config file",
    )
    parser.add_argument(
        "--config-output",
        type=str,
        default=str(repo_root / "config" / "user_config.yaml"),
        help="Output path for generated config",
    )

    args = parser.parse_args()

    # Load catalog
    try:
        catalog = load_model_catalog()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Get platform info
    platform_info = get_platform_info()

    # Apply overrides
    if args.vram:
        platform_info["gpu_memory_mb"] = args.vram
        platform_info["available_gpu_memory_mb"] = args.vram
    if args.platform:
        platform_info["platform"] = args.platform

    platform = platform_info["platform"]
    vram_mb = platform_info["gpu_memory_mb"]

    # Handle --detect
    if args.detect:
        print_header()
        print_platform_info(platform_info)
        sys.exit(0)

    # Handle --list-models
    if args.list_models:
        print_header()
        print_platform_info(platform_info)
        print_model_list(catalog, platform, vram_mb, show_all=args.all)
        sys.exit(0)

    # Main flow
    print_header()
    print_platform_info(platform_info)
    print_model_list(catalog, platform, vram_mb, show_all=args.all)

    # Non-interactive mode
    if args.model:
        selected_models = [args.model.upper()]
    else:
        # Interactive selection
        selected_models = interactive_select(catalog, platform, vram_mb)

    if not selected_models:
        print("No models selected. Exiting.")
        sys.exit(0)

    print()
    print(f"Selected models: {', '.join(selected_models)}")
    print()

    # Process each selected model
    models = catalog.get("models", {})
    for model_id in selected_models:
        model_info = models.get(model_id)
        if not model_info:
            print(f"Warning: Unknown model {model_id}, skipping")
            continue

        hf_id = model_info.get("hf_id", f"depth-anything/{model_id}")
        settings = get_optimal_settings(model_id, model_info, platform)

        print(f"\n{model_id}:")
        print(f"  HuggingFace ID: {hf_id}")
        print(f"  Optimal Resolution: {settings['height']}x{settings['width']}")
        print(f"  Expected FPS: ~{settings.get('fps_estimate', '?')}")
        print(f"  Expected VRAM: ~{format_vram(settings.get('vram_usage_mb', 0))}")

        # Download
        if not args.no_download:
            success = download_model(model_id, hf_id)
            if not success:
                print(f"  Warning: Failed to download {model_id}")

    # Generate config for first selected model
    if not args.no_config and selected_models:
        first_model = selected_models[0]
        model_info = models.get(first_model, {})
        settings = get_optimal_settings(first_model, model_info, platform)
        output_path = Path(args.config_output)
        print()
        generate_user_config(first_model, settings, output_path)

    print()
    print("Setup complete!")
    print()
    print("Next steps:")
    print("  1. Review the generated config: config/user_config.yaml")
    print("  2. Launch the node:")
    print("     ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py")
    print()


if __name__ == "__main__":
    main()
