# Changelog
01/30/2026
## Depth Anything 3

### Added

- **Dockerfile**:
  - `L4T_VERSION=r36.2.0` build argument.
  - New `jetson-base` stage using `nvcr.io/nvidia/l4t-ros:humble-ros-base-l4t-${L4T_VERSION}`.
  - PyTorch installation logic for Jetson using NVIDIA's Jetson AI Lab wheels.

- **docker-compose.yml**:
  - New `depth-anything-3-jetson` service with `BUILD_TYPE: jetson-base`.

- **Tests**:
  - Added `test/__init__.py` and `test/conftest.py` for shared fixtures and ROS2 availability detection.
  - Updated `test/test_node.py` and `test/test_generic_camera.py` to gracefully handle missing ROS2 modules (allows running tests in non-ROS environments).

- **.gitignore**:
  - Added `CLAUDE.md`, `nul`, and `.claude/settings.local.json`.
