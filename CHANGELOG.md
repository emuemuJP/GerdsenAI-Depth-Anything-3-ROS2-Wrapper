# Changelog

## [Unreleased] - 2026-02-04

### Shared Memory IPC Optimization - 4x Performance Improvement

- **Shared Memory TRT Service** (`scripts/trt_inference_service_shm.py`):
  - RAM-backed IPC via `/dev/shm/da3` using numpy.memmap
  - Eliminates file I/O overhead from previous `/tmp/da3_shared` approach
  - Pre-allocated fixed-size memory regions for zero-copy data transfer
  - Performance: 23+ FPS (limited by camera), 43+ FPS processing capacity

- **SharedMemoryInferenceFast Class** (`depth_anything_3_ros2/da3_inference.py`):
  - New inference backend for fast shared memory communication
  - Auto-detection of SHM service availability
  - Fallback to file-based IPC if SHM not available

- **Auto-Detection in Depth Node** (`depth_anything_3_ros2/depth_anything_3_node.py`):
  - Automatically selects SharedMemoryInferenceFast when `/dev/shm/da3/status` exists
  - Seamless fallback to SharedMemoryInference for backward compatibility

- **Updated Scripts**:
  - `run.sh`: Now uses `trt_inference_service_shm.py` by default
  - `docker-compose.yml`: Added `/dev/shm/da3` volume mount

| Metric | Before (File IPC) | After (Shared Memory) |
|--------|-------------------|----------------------|
| FPS | 5-12 | 23+ (camera-limited) |
| Inference | ~50ms + 40ms IPC | ~15ms + 8ms IPC |
| Total | ~90ms | ~23ms |
| Capacity | ~11 FPS | 43+ FPS |

### Documentation Updates

- **README.md**:
  - Added "Production Architecture" section with host-container split diagram
  - Clarified TensorRT is the production backend, PyTorch is library dependency only
  - Updated Performance section to show TensorRT as primary, PyTorch as baseline reference
  - Added notes to CPU-only mode example clarifying it's for development/testing only
  - Updated Key Files table to reference `trt_inference_service_shm.py`

- **Architecture Clarification**:
  - TensorRT 10.3 runs on Jetson HOST (not in container)
  - Container uses SharedMemoryInferenceFast for IPC with host TRT service
  - PyTorch installed in container as DA3 library dependency, not for inference
  - `DA3InferenceWrapper` (PyTorch backend) exists only as development/fallback mode

---

## [0.2.0] - 2026-01-31

### TensorRT 10.3 Validation - Phase 1 Complete

- **TensorRT 10.3 Performance Validated**:
  - Platform: Jetson Orin NX 16GB
  - Model: DA3-SMALL at 518x518 FP16
  - Throughput: 35.3 FPS
  - GPU Latency: 26.4ms median (25.5ms min)
  - Engine Size: 58MB
  - Speedup: 6.8x over PyTorch baseline (~5.2 FPS)
  - Test Date: 2026-01-31
  - Validation: Host script `scripts/test_trt10.3_host.sh`

### Critical Findings (Resolved)

- **TensorRT 8.6 Fundamentally Incompatible with DA3**:
  - Root cause: DINOv2 backbone exports Einsum operations unsupported by TRT 8.6
  - Error: "caskConvolutionV2Forward could not find any supported formats"
  - NVIDIA GitHub Issue #4537 confirms DINOv2 failures persist until TRT 10.8+
  - Workarounds (opset 17 re-export, graph surgery) not viable
  - **Solution Validated:** Docker base image L4T r36.4.0 (TensorRT 10.3)
  - Full analysis: `docs/TENSORRT_DA3_PLAN.md`

### Docker Base Image Update

- **Updated Jetson base image to L4T r36.4.0**:
  - Previous: `dustynv/ros:humble-ros-base-l4t-r36.2.0` (TensorRT 8.6.2)
  - Current: `dustynv/ros:humble-pytorch-l4t-r36.4.0` (TensorRT 10.3)
  - Benefits: Full DINOv2/ViT support, validated 6.8x speedup
  - TRT 10.x syntax: `--memPoolSize=workspace:2048MiB`
  - ONNX 5D input: `pixel_values:1x1x3x518x518`

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

---

## [0.1.1] - 2025-12-09

### Fixed (PR #19)

- **CI/CD Pipeline Fixes**:
  - Resolved lint failures in flake8 configuration
  - Fixed test mocking for ROS2 module imports
  - Docker build improvements for reliability
  - Updated `.github/workflows/ci.yml` for proper testing

- **Code Quality**:
  - Added `.flake8` configuration
  - Updated `mypy.ini` and `pyproject.toml`
  - Improved test coverage in `test/test_inference.py` and `test/test_node.py`

---

## [0.1.0] - 2025-11-19

### Added (PR #13)

- **Optimized Inference Pipeline**:
  - `depth_anything_3_ros2/da3_inference_optimized.py`: TensorRT-optimized inference wrapper
  - `depth_anything_3_ros2/depth_anything_3_node_optimized.py`: High-performance ROS2 node
  - `depth_anything_3_ros2/gpu_utils.py`: GPU memory management utilities
  - `launch/depth_anything_3_optimized.launch.py`: Launch file for optimized node

- **TensorRT Conversion Tools**:
  - `scripts/convert_to_tensorrt.py`: ONNX to TensorRT engine converter
  - Support for FP16 and INT8 quantization

- **OPTIMIZATION_GUIDE.md**:
  - Comprehensive guide for achieving 30+ FPS on Jetson
  - Performance benchmarks and tuning recommendations
  - TensorRT engine building instructions

### Performance Targets

- Target: 30+ FPS on Jetson Orin AGX
- TensorRT FP16: 7.7x speedup over PyTorch baseline
- Validated: 40 FPS @ 518x518, 93 FPS @ 308x308
