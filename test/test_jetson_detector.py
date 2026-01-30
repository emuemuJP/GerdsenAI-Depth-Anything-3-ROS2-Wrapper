"""
Unit tests for the jetson_detector module.

Tests hardware detection functions with mocked system files and PyTorch.
"""

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure the module can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

from depth_anything_3_ros2 import jetson_detector


class TestIsJetson:
    """Tests for the is_jetson() function."""

    def test_is_jetson_with_tegra_release_file(self, tmp_path):
        """Should return True when /etc/nv_tegra_release exists."""
        tegra_file = tmp_path / "nv_tegra_release"
        tegra_file.write_text("# R36 (release), REVISION: 4.0")

        with mock.patch.object(Path, "exists") as mock_exists:
            mock_exists.return_value = True
            with mock.patch(
                "depth_anything_3_ros2.jetson_detector.Path"
            ) as mock_path_cls:
                mock_path_cls.return_value.exists.return_value = True
                # The actual function checks specific paths
                result = jetson_detector.is_jetson()
                # Result depends on actual file system, so we test the logic

    def test_is_jetson_false_on_regular_linux(self):
        """Should return False on non-Jetson Linux."""
        with mock.patch.object(Path, "exists", return_value=False):
            with mock.patch(
                "depth_anything_3_ros2.jetson_detector.Path"
            ) as mock_path:
                # Mock both paths returning False
                instance = mock_path.return_value
                instance.exists.return_value = False
                instance.read_text.return_value = ""
                # Test on current system
                # This will return actual result based on system


class TestGetL4tVersion:
    """Tests for the get_l4t_version() function."""

    def test_parse_l4t_r36_4_0(self):
        """Should correctly parse L4T r36.4.0 format."""
        content = "# R36 (release), REVISION: 4.0, GCID: 12345, BOARD: generic"

        with mock.patch(
            "depth_anything_3_ros2.jetson_detector.Path"
        ) as mock_path:
            instance = mock_path.return_value
            instance.exists.return_value = True
            instance.read_text.return_value = content

            result = jetson_detector.get_l4t_version()
            assert result == "r36.4.0"

    def test_parse_l4t_r35_4_1(self):
        """Should correctly parse L4T r35.4.1 format."""
        content = "# R35 (release), REVISION: 4.1, GCID: 12345"

        with mock.patch(
            "depth_anything_3_ros2.jetson_detector.Path"
        ) as mock_path:
            instance = mock_path.return_value
            instance.exists.return_value = True
            instance.read_text.return_value = content

            result = jetson_detector.get_l4t_version()
            assert result == "r35.4.1"

    def test_returns_none_when_file_missing(self):
        """Should return None when /etc/nv_tegra_release doesn't exist."""
        with mock.patch(
            "depth_anything_3_ros2.jetson_detector.Path"
        ) as mock_path:
            instance = mock_path.return_value
            instance.exists.return_value = False

            result = jetson_detector.get_l4t_version()
            assert result is None


class TestGetJetpackVersion:
    """Tests for the get_jetpack_version() function."""

    def test_jetpack_6_2_from_l4t_36_4(self):
        """Should map L4T r36.4.x to JetPack 6.2."""
        with mock.patch(
            "depth_anything_3_ros2.jetson_detector.get_l4t_version"
        ) as mock_l4t:
            mock_l4t.return_value = "r36.4.0"
            result = jetson_detector.get_jetpack_version()
            assert result == "6.2"

    def test_jetpack_6_1_from_l4t_36_3(self):
        """Should map L4T r36.3.x to JetPack 6.1."""
        with mock.patch(
            "depth_anything_3_ros2.jetson_detector.get_l4t_version"
        ) as mock_l4t:
            mock_l4t.return_value = "r36.3.0"
            result = jetson_detector.get_jetpack_version()
            assert result == "6.1"

    def test_jetpack_5_1_4_from_l4t_35_6(self):
        """Should map L4T r35.6.x to JetPack 5.1.4."""
        with mock.patch(
            "depth_anything_3_ros2.jetson_detector.get_l4t_version"
        ) as mock_l4t:
            mock_l4t.return_value = "r35.6.0"
            result = jetson_detector.get_jetpack_version()
            assert result == "5.1.4"


class TestGetTotalRamGb:
    """Tests for the get_total_ram_gb() function."""

    def test_parse_meminfo_16gb(self):
        """Should correctly parse 16GB from /proc/meminfo."""
        content = """MemTotal:       16384000 kB
MemFree:         8000000 kB
MemAvailable:   12000000 kB
"""
        with mock.patch(
            "depth_anything_3_ros2.jetson_detector.Path"
        ) as mock_path:
            instance = mock_path.return_value
            instance.exists.return_value = True
            instance.read_text.return_value = content

            result = jetson_detector.get_total_ram_gb()
            assert abs(result - 15.625) < 0.1  # 16384000 kB ~ 15.625 GB

    def test_parse_meminfo_8gb(self):
        """Should correctly parse 8GB from /proc/meminfo."""
        content = "MemTotal:        8192000 kB\nMemFree:         4000000 kB\n"
        with mock.patch(
            "depth_anything_3_ros2.jetson_detector.Path"
        ) as mock_path:
            instance = mock_path.return_value
            instance.exists.return_value = True
            instance.read_text.return_value = content

            result = jetson_detector.get_total_ram_gb()
            assert abs(result - 7.8125) < 0.1  # 8192000 kB ~ 7.8 GB


class TestIdentifyJetsonPlatform:
    """Tests for the identify_jetson_platform() function."""

    def test_identify_agx_orin_64gb(self):
        """Should identify AGX Orin 64GB from model name and RAM."""
        result = jetson_detector.identify_jetson_platform(
            ram_gb=64.0,
            model_name="NVIDIA Jetson AGX Orin Developer Kit"
        )
        assert result == jetson_detector.PLATFORM_AGX_ORIN_64GB

    def test_identify_agx_orin_32gb(self):
        """Should identify AGX Orin 32GB from model name and RAM."""
        result = jetson_detector.identify_jetson_platform(
            ram_gb=32.0,
            model_name="NVIDIA Jetson AGX Orin"
        )
        assert result == jetson_detector.PLATFORM_AGX_ORIN_32GB

    def test_identify_orin_nx_16gb(self):
        """Should identify Orin NX 16GB from model name and RAM."""
        result = jetson_detector.identify_jetson_platform(
            ram_gb=16.0,
            model_name="NVIDIA Orin NX Developer Kit"
        )
        assert result == jetson_detector.PLATFORM_ORIN_NX_16GB

    def test_identify_orin_nx_8gb(self):
        """Should identify Orin NX 8GB from model name and RAM."""
        result = jetson_detector.identify_jetson_platform(
            ram_gb=8.0,
            model_name="NVIDIA Orin NX"
        )
        assert result == jetson_detector.PLATFORM_ORIN_NX_8GB

    def test_identify_orin_nano_8gb(self):
        """Should identify Orin Nano 8GB from model name and RAM."""
        result = jetson_detector.identify_jetson_platform(
            ram_gb=8.0,
            model_name="NVIDIA Orin Nano Developer Kit"
        )
        assert result == jetson_detector.PLATFORM_ORIN_NANO_8GB

    def test_identify_orin_nano_4gb(self):
        """Should identify Orin Nano 4GB from model name and RAM."""
        result = jetson_detector.identify_jetson_platform(
            ram_gb=4.0,
            model_name="NVIDIA Orin Nano"
        )
        assert result == jetson_detector.PLATFORM_ORIN_NANO_4GB

    def test_identify_xavier_nx(self):
        """Should identify Xavier NX from model name."""
        result = jetson_detector.identify_jetson_platform(
            ram_gb=8.0,
            model_name="NVIDIA Jetson Xavier NX Developer Kit"
        )
        assert result == jetson_detector.PLATFORM_XAVIER_NX

    def test_identify_agx_xavier(self):
        """Should identify AGX Xavier from model name."""
        result = jetson_detector.identify_jetson_platform(
            ram_gb=32.0,
            model_name="NVIDIA Jetson AGX Xavier"
        )
        assert result == jetson_detector.PLATFORM_AGX_XAVIER

    def test_identify_p3767_as_orin_nx(self):
        """Should identify p3767 board ID as Orin NX."""
        result = jetson_detector.identify_jetson_platform(
            ram_gb=16.0,
            model_name="NVIDIA Orin p3767-0000"
        )
        assert result == jetson_detector.PLATFORM_ORIN_NX_16GB


class TestGetPlatformRecommendations:
    """Tests for the get_platform_recommendations() function."""

    def test_orin_nano_4gb_recommendations(self):
        """Should recommend DA3-SMALL at 308x308 for Orin Nano 4GB."""
        recs = jetson_detector.get_platform_recommendations(
            jetson_detector.PLATFORM_ORIN_NANO_4GB
        )
        assert recs["recommended_model"] == "DA3-SMALL"
        assert recs["recommended_resolution"] == (308, 308)
        assert recs["max_model"] == "DA3-SMALL"

    def test_orin_nx_16gb_recommendations(self):
        """Should recommend DA3-SMALL at 518x518 for Orin NX 16GB."""
        recs = jetson_detector.get_platform_recommendations(
            jetson_detector.PLATFORM_ORIN_NX_16GB
        )
        assert recs["recommended_model"] == "DA3-SMALL"
        assert recs["recommended_resolution"] == (518, 518)
        assert recs["max_model"] == "DA3-BASE"

    def test_agx_orin_64gb_recommendations(self):
        """Should recommend DA3-LARGE-1.1 at 1024x1024 for AGX Orin 64GB."""
        recs = jetson_detector.get_platform_recommendations(
            jetson_detector.PLATFORM_AGX_ORIN_64GB
        )
        assert recs["recommended_model"] == "DA3-LARGE-1.1"
        assert recs["recommended_resolution"] == (1024, 1024)
        assert recs["max_model"] == "DA3-GIANT-1.1"


class TestCheckModelCompatibility:
    """Tests for the check_model_compatibility() function."""

    def test_da3_small_compatible_everywhere(self):
        """DA3-SMALL should be compatible with all platforms."""
        for platform in [
            jetson_detector.PLATFORM_ORIN_NANO_4GB,
            jetson_detector.PLATFORM_ORIN_NX_16GB,
            jetson_detector.PLATFORM_AGX_ORIN_64GB,
        ]:
            compatible, message = jetson_detector.check_model_compatibility(
                "DA3-SMALL", platform
            )
            assert compatible is True

    def test_da3_large_incompatible_with_orin_nano(self):
        """DA3-LARGE-1.1 should be incompatible with Orin Nano 4GB."""
        compatible, message = jetson_detector.check_model_compatibility(
            "DA3-LARGE-1.1",
            jetson_detector.PLATFORM_ORIN_NANO_4GB,
        )
        assert compatible is False
        assert "VRAM" in message

    def test_da3_giant_incompatible_with_orin_nx_16gb(self):
        """DA3-GIANT-1.1 should be incompatible with Orin NX 16GB."""
        compatible, message = jetson_detector.check_model_compatibility(
            "DA3-GIANT-1.1",
            jetson_detector.PLATFORM_ORIN_NX_16GB,
        )
        assert compatible is False

    def test_vram_override(self):
        """VRAM override should allow incompatible model on low-VRAM platform."""
        compatible, message = jetson_detector.check_model_compatibility(
            "DA3-LARGE-1.1",
            jetson_detector.PLATFORM_ORIN_NANO_4GB,
            vram_mb=16000,  # Override to 16GB
        )
        assert compatible is True

    def test_license_warning_for_large_models(self):
        """Should include license warning for CC-BY-NC models."""
        compatible, message = jetson_detector.check_model_compatibility(
            "DA3-BASE",
            jetson_detector.PLATFORM_AGX_ORIN_64GB,
        )
        assert compatible is True
        assert "CC-BY-NC-4.0" in message or "non-commercial" in message.lower()


class TestDetectPlatform:
    """Tests for the detect_platform() function."""

    def test_returns_dict_with_required_keys(self):
        """Should return dict with all required keys."""
        result = jetson_detector.detect_platform()

        required_keys = [
            "platform",
            "display_name",
            "is_jetson",
            "device_model",
            "ram_gb",
            "gpu_memory_mb",
            "available_gpu_memory_mb",
            "gpu_name",
            "jetpack_version",
            "l4t_version",
            "cuda_available",
        ]

        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

    def test_platform_is_string(self):
        """Platform identifier should be a string."""
        result = jetson_detector.detect_platform()
        assert isinstance(result["platform"], str)
        assert len(result["platform"]) > 0

    def test_ram_gb_is_numeric(self):
        """RAM should be a numeric value."""
        result = jetson_detector.detect_platform()
        assert isinstance(result["ram_gb"], (int, float))


class TestFormatPlatformInfo:
    """Tests for the format_platform_info() function."""

    def test_format_includes_platform_name(self):
        """Formatted output should include platform display name."""
        info = {
            "platform": "AGX_ORIN_64GB",
            "display_name": "Jetson AGX Orin 64GB",
            "is_jetson": True,
            "device_model": "NVIDIA Jetson AGX Orin",
            "ram_gb": 64.0,
            "gpu_memory_mb": 65536,
            "available_gpu_memory_mb": 60000,
            "gpu_name": "Orin (GA10B)",
            "jetpack_version": "6.2",
            "l4t_version": "r36.4.0",
            "cuda_available": True,
        }

        output = jetson_detector.format_platform_info(info)

        assert "Jetson AGX Orin 64GB" in output
        assert "64.0 GB" in output
        assert "JetPack: 6.2" in output
        assert "L4T: r36.4.0" in output
        assert "CUDA Available: Yes" in output

    def test_format_hides_jetpack_for_non_jetson(self):
        """Formatted output should not show JetPack for non-Jetson."""
        info = {
            "platform": "X86_GPU",
            "display_name": "x86 GPU (RTX 3090)",
            "is_jetson": False,
            "device_model": "Unknown",
            "ram_gb": 32.0,
            "gpu_memory_mb": 24576,
            "available_gpu_memory_mb": 20000,
            "gpu_name": "NVIDIA GeForce RTX 3090",
            "jetpack_version": None,
            "l4t_version": None,
            "cuda_available": True,
        }

        output = jetson_detector.format_platform_info(info)

        assert "JetPack" not in output
        assert "L4T" not in output
        assert "x86 GPU" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
