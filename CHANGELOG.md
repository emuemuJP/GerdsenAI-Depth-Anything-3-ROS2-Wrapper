# Changelog

## [Unreleased] - 2026-01-30

### Critical Findings

- **TensorRT Opset Incompatibility Discovered**:
  - TensorRT 8.6.2 (bundled with JetPack 6.0) only supports ONNX opset 17
  - DA3 models export with opset 18+ (incompatible)
  - Result: TensorRT native acceleration currently blocked
  - Workaround options documented in TODO.md

### Performance Baseline

- **Measured on Jetson Orin NX 16GB** (JetPack 6.0, L4T r36.2.0, CUDA 12.2):
  - Model: DA3-SMALL (PyTorch, FP32)
  - Resolution: 518x518
  - Inference Time: ~193ms per frame
  - FPS: ~5.2 FPS

### Added

- **Jetson Hardware Detection** (`depth_anything_3_ros2/jetson_detector.py`):
  - Platform detection for Jetson modules (Orin AGX, Orin NX, Orin Nano, Xavier AGX, Xavier NX)
  - GPU memory and VRAM detection
  - JetPack and L4T version detection
  - CUDA availability checking

- **Model Setup System**:
  - `config/model_catalog.yaml`: Model catalog with VRAM requirements and platform recommendations
  - `scripts/setup_models.py`: Interactive model selection and download script
  - Hardware-aware model recommendations based on detected platform

- **Dockerfile - Jetson Support**:
  - `L4T_VERSION=r36.2.0` build argument
  - New `jetson-base` stage using `dustynv/ros:humble-ros-base-l4t-${L4T_VERSION}`
  - OpenCV 4.8.1 version verification check
  - cv_bridge and image_geometry built from source (resolves OpenCV 4.8.1 vs 4.5.4 conflict)
  - `-DBUILD_TESTING=OFF` flag for cv_bridge build (avoids ament_lint_auto dependency)
  - PyTorch 2.3.0 via direct NVIDIA wheel download (CUDA 12.2 support for L4T r36.2.0)
  - torchvision 0.18.0 compatible with PyTorch 2.3.0
  - OpenMPI and OpenBLAS runtime dependencies for PyTorch on ARM64
  - Depth Anything 3 installation with `--no-deps` flag (avoids pycolmap/open3d ARM64 build failures)
  - Windows line ending fix (`sed -i 's/\r$//'`) for ros_entrypoint.sh
  - Model download at build time via `DOWNLOAD_MODELS_AT_BUILD` and `INSTALL_MODELS` args

- **docker-compose.yml**:
  - New `depth-anything-3-jetson` service with `BUILD_TYPE: jetson-base`
  - Enhanced GPU access configuration with nvidia-container-runtime

- **Tests**:
  - `test/__init__.py`: Package marker for test directory
  - `test/conftest.py`: Shared fixtures and ROS2 availability detection
  - `test/test_jetson_detector.py`: Unit tests for Jetson hardware detection
  - Updated `test/test_node.py` with conditional imports and skipif decorators
  - Updated `test/test_generic_camera.py` with graceful ROS2 module handling

- **.gitignore**:
  - Added `CLAUDE.md`, `nul`, `.claude/settings.local.json`
  - Line ending rules (`eol=lf`) for shell scripts

### Fixed

- **PyTorch CUDA Support on Jetson**:
  - Changed from cu126 index to direct NVIDIA wheel (cu122 for L4T r36.2.0)
  - Added libopenmpi3 and libopenblas0 to both builder and runtime stages
  - `torch.cuda.is_available()` now returns `True` in container

- **cv_bridge OpenCV Conflict**:
  - ROS Humble apt packages expect OpenCV 4.5.4
  - dustynv base image ships with OpenCV 4.8.1 (CUDA-enabled)
  - Solution: Build cv_bridge from source against existing OpenCV 4.8.1

- **ARM64 Python Package Dependencies**:
  - pycolmap and open3d lack ARM64 wheels
  - Solution: Install Depth Anything 3 with `--no-deps`, manually install required inference dependencies
  - Runtime patch: api.py patched at container startup to handle missing pycolmap/evo imports

- **torchvision Source Build Required**:
  - NVIDIA PyTorch wheel has ABI mismatch with pip torchvision
  - NMS operator crashes at runtime with pip-installed torchvision
  - Solution: Build torchvision 0.18.0 from source against NVIDIA PyTorch wheel

- **Windows CRLF Line Endings**:
  - ros_entrypoint.sh fails with CRLF line endings on Windows-cloned repos
  - Solution: Added `sed -i 's/\r$//'` in Dockerfile for entrypoint scripts

- **Test Collection Failures (Issue #21)**:
  - Tests failed when ROS2 environment not sourced
  - Solution: Added ROS2 availability detection and pytest skipif decorators

### Changed

- **Dockerfile**:
  - Base image for Jetson changed from `nvcr.io/nvidia/l4t-ros` to `dustynv/ros` (no NGC auth required)
  - PyTorch installation method changed from pip index to direct wheel download
  - cv_bridge installation changed from apt to source build
