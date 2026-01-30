# TODO - Open GitHub Issues

## Overview

This document tracks open GitHub issues and their current status in the `bug-fixes-01302026` branch.

| Issue | Title | Priority | Status |
|-------|-------|----------|--------|
| #22 | [Bug] Optimize scripts problem | High | Workaround implemented |
| #21 | [Bug] Test failed | - | Addressed in current branch |
| #20 | [Question] Package dependencies too large | Low | Not addressed (upstream issue) |
| - | Docker/Jetson Deployment | - | COMPLETED |
| - | TensorRT Optimization Implementation | - | COMPLETED |

---

## Docker/Jetson Deployment [COMPLETED]

**Problem**: Multiple issues preventing Docker image from building and running on NVIDIA Jetson Orin AGX with L4T r36.2.0 (JetPack 6.x).

**Issues Resolved**:

1. **Missing Files in Docker Build**
   - Added `config/model_catalog.yaml` to version control
   - Added `scripts/setup_models.py` for automated model downloads
   - Added `depth_anything_3_ros2/jetson_detector.py` for hardware detection

2. **cv_bridge Build Conflict**
   - Root cause: ROS2 apt packages include pre-built cv_bridge linked to OpenCV 4.8.1, conflicting with JetPack's OpenCV 4.10.0
   - Fix: Added `-DBUILD_TESTING=OFF` flag to cv_bridge colcon build to reduce build time and avoid test conflicts

3. **ARM64 Python Package Dependencies**
   - Root cause: `pycolmap` and `open3d` don't provide ARM64 wheels, tried to build from source requiring incompatible dependencies
   - Fix: Added `--no-deps` flag to pip install commands for these packages (only needed for scripts, not runtime)

4. **Windows Line Endings in Entrypoint Script**
   - Root cause: Git on Windows converted `ros_entrypoint.sh` to CRLF line endings
   - Fix: Updated `.gitignore` with proper `eol=lf` handling

5. **PyTorch CUDA Support on Jetson**
   - Root cause: Dockerfile used wrong CUDA index URL (`cu126` instead of `cu122`) for PyTorch installation
   - L4T r36.2.0 ships with CUDA 12.2, but pip was trying to install CPU-only or incompatible CUDA versions
   - Fix: Changed to direct NVIDIA wheel download for PyTorch 2.3.0 with CUDA 12.2 support
   - Added OpenMPI and OpenBLAS runtime dependencies required by NVIDIA PyTorch wheels
   - Verified: `torch.cuda.is_available()` returns `True` in container

**Files Modified**:
- `Dockerfile` - Fixed CUDA index, added OpenMPI/OpenBLAS deps, improved cv_bridge build flags
- `docker-compose.yml` - Enhanced GPU access configuration
- `.gitignore` - Added line ending rules for shell scripts

**Verification**:
- Docker image builds successfully on Jetson Orin AGX
- PyTorch 2.3.0 detects CUDA 12.2 correctly
- Container has GPU access via nvidia-container-runtime
- ROS2 Humble environment sources correctly

---

## TensorRT Optimization Implementation [COMPLETED]

**Problem**: TensorRT optimization was planned but not fully integrated into the Docker deployment workflow. Users had to manually run optimization scripts after deployment, and dependencies were missing.

**Implementation Completed** (2026-01-30):

### Changes Made

1. **Added TensorRT Dependencies to Dockerfile**:
   - `python3-dev` - Required for building Python C extensions
   - `pycuda` - CUDA Python bindings for TensorRT
   - `huggingface_hub` - Model downloading from HuggingFace

2. **Implemented Build-Time TensorRT Engine Building**:
   - Added Docker build arguments:
     - `BUILD_TENSORRT=true/false` - Enable engine building during image creation
     - `TENSORRT_MODEL=da3-small/da3-base/da3-large` - Model selection
     - `TENSORRT_PRECISION=fp16/fp32` - Precision mode (FP16 recommended)
     - `TENSORRT_RESOLUTION=308/518/etc` - Input resolution
   - Conditional engine building at Docker build time (optional)
   - Uses `scripts/build_tensorrt_engine.py` with `--auto` flag for platform detection

3. **Enhanced ros_entrypoint.sh with Auto-Build**:
   - Added TensorRT engine detection logic
   - Environment variable `DA3_TENSORRT_AUTO=true` triggers automatic building on first run
   - Checks for existing engines in `/root/.cache/tensorrt`
   - Builds missing engines automatically with platform-appropriate settings
   - 5-10 minute delay on first container start (one-time only)

4. **Fixed docker-compose.yml Configuration**:
   - Added `NVIDIA_DRIVER_CAPABILITIES=all` for compute, graphics, and utility access
   - Added volume mount: `./models/tensorrt:/root/.cache/tensorrt:rw` for engine caching
   - Added volume mount: `./models/onnx:/root/.cache/onnx:rw` for ONNX model caching
   - Added `DA3_TENSORRT_AUTO` environment variable support
   - Engines persist across container restarts

5. **Updated OPTIMIZATION_GUIDE.md**:
   - Changed precision recommendation from INT8 to FP16
   - Rationale: INT8 requires calibration dataset which is not implemented
   - FP16 provides best speed/accuracy tradeoff on Jetson with minimal setup
   - Aligned platform-specific recommendations with `model_catalog.yaml`

### Critical Technical Insight

**TensorRT Verification Deferred to Runtime**: The dustynv NVIDIA base images use stub libraries during Docker build time. This means:
- `pycuda` installation succeeds at build time (pip install works)
- `import tensorrt` only works at runtime when GPU access is available
- Solution: Install dependencies at build time, verify TensorRT import at runtime
- This is a known limitation of NVIDIA's container architecture

### Three Build Strategies Implemented

**Option A: Build-Time Engine (Baked into Image)**
```bash
docker compose build depth-anything-3-jetson \
    --build-arg BUILD_TENSORRT=true \
    --build-arg TENSORRT_MODEL=da3-small \
    --build-arg TENSORRT_PRECISION=fp16 \
    --build-arg TENSORRT_RESOLUTION=308
```
- Pros: Fastest startup, engine ready immediately
- Cons: Longer build time, platform-specific images

**Option B: Runtime Auto-Build (RECOMMENDED)**
```bash
DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson
```
- Pros: Flexible, works on any platform, one-time setup
- Cons: 5-10 minute delay on first container start

**Option C: Manual Build**
```bash
docker run --rm --runtime=nvidia \
    -v ./models/tensorrt:/root/.cache/tensorrt:rw \
    depth_anything_3_ros2:jetson \
    python3 /ros2_ws/src/depth_anything_3_ros2/scripts/build_tensorrt_engine.py --auto
```
- Pros: Maximum control, explicit workflow
- Cons: Requires user intervention

### Files Modified

- `Dockerfile` - Added dependencies, TensorRT build arguments, conditional engine building
- `docker/ros_entrypoint.sh` - Added TensorRT detection and auto-build logic
- `docker-compose.yml` - Added NVIDIA_DRIVER_CAPABILITIES, volume mounts, environment variables
- `OPTIMIZATION_GUIDE.md` - Updated precision recommendations from INT8 to FP16

### Verification Results (Jetson Orin AGX)

- Docker build: SUCCESS
- TensorRT 8.6.2: OK (verified at runtime)
- pycuda: OK
- huggingface_hub: OK
- Engine building: SUCCESS
- Engine caching: SUCCESS (persists across container restarts)

### Related to Issue #22

This implementation provides a workaround for Issue #22 (ONNX export failures) by using pre-exported ONNX models from upstream or community sources instead of attempting direct PyTorch-to-ONNX conversion. The original export issue remains unresolved and requires upstream fixes.

---

## Issue #21: Test Failed [ADDRESSED]

**GitHub**: https://github.com/GerdsenAI/Depth-Anything-3-ROS2-Wrapper/issues/21

**Problem**: `colcon test` fails with "collection failure" when ROS2 environment is not sourced.

**Root Cause**: Tests attempted to import ROS2 packages at collection time, causing failures when ROS2 was not available.

**Fix Applied** (in `bug-fixes-01302026` branch):
- Added `test/conftest.py` with ROS2 availability detection
- Added `test/__init__.py` to make test directory a proper package
- Updated `test/test_node.py` with conditional imports and `@pytest.mark.skipif` decorators
- Updated `test/test_generic_camera.py` with the same pattern

---

## Issue #22: Optimize Scripts Problem [WORKAROUND IMPLEMENTED]

**GitHub**: https://github.com/GerdsenAI/Depth-Anything-3-ROS2-Wrapper/issues/22

**Original Problem**: TensorRT/ONNX export fails with:
```
ValueError: not enough values to unpack (expected 5, got 4)
```

**Location**: `depth_anything_3/model/dinov2/vision_transformer.py:301`
```python
B, S, _, H, W = x.shape  # expects 5D tensor, gets 4D
```

**Root Cause**: Depth Anything 3's DINOv2 backbone has a different tensor shape during tracing/export than during normal inference. The `get_intermediate_layers` method expects 5D input but receives 4D during ONNX tracing.

**Workaround Implemented** (2026-01-30):

Since direct ONNX export from the model fails, we implemented a Docker-based TensorRT optimization solution that:

1. **Added Missing Dependencies**:
   - `python3-dev` - Required for building Python extensions
   - `pycuda` - CUDA Python bindings for TensorRT
   - `huggingface_hub` - Model downloading for ONNX pre-exports

2. **Implemented Build-Time TensorRT Engine Building**:
   - Added Docker build arguments: `BUILD_TENSORRT`, `TENSORRT_MODEL`, `TENSORRT_PRECISION`, `TENSORRT_RESOLUTION`
   - Conditional engine building during Docker image creation
   - Uses pre-exported ONNX models from upstream or community sources

3. **Enhanced Runtime Auto-Build Capability**:
   - Modified `ros_entrypoint.sh` with TensorRT detection logic
   - Environment variable `DA3_TENSORRT_AUTO=true` triggers automatic engine building on first run
   - Engines cached in `/root/.cache/tensorrt` and persisted via Docker volumes

4. **Fixed Docker Compose Configuration**:
   - Added `NVIDIA_DRIVER_CAPABILITIES=all` for proper GPU access
   - Added volume mounts for TensorRT and ONNX caching
   - Added `DA3_TENSORRT_AUTO` environment variable support

5. **Updated Documentation**:
   - `OPTIMIZATION_GUIDE.md` now recommends FP16 over INT8 (INT8 requires calibration dataset)
   - Platform-specific resolution and model recommendations aligned with `model_catalog.yaml`

**Critical Learning**: TensorRT verification must be deferred to runtime because dustynv base images use stub NVIDIA libraries during Docker build time. The solution:
- Install `pycuda` at build time (installation verification succeeds)
- Defer `import tensorrt` verification to runtime when GPU access is available
- This is a known limitation of NVIDIA container base images

**Verification Results** (Jetson Orin AGX):
- Docker build: SUCCESS
- Dependencies installed: python3-dev, pycuda, huggingface_hub
- TensorRT 8.6.2: OK (verified at runtime)
- pycuda: OK
- huggingface_hub: OK

**Files Modified**:
- `Dockerfile` - Added dependencies and conditional TensorRT engine building
- `docker/ros_entrypoint.sh` - Added automatic engine building logic
- `docker-compose.yml` - Fixed GPU access and added volume mounts
- `OPTIMIZATION_GUIDE.md` - Updated precision recommendations

**Usage Examples**:

```bash
# Option A: Build with TensorRT engine baked in
docker compose build depth-anything-3-jetson \
    --build-arg BUILD_TENSORRT=true \
    --build-arg TENSORRT_MODEL=da3-small \
    --build-arg TENSORRT_PRECISION=fp16 \
    --build-arg TENSORRT_RESOLUTION=308

# Option B: Auto-build on first run (RECOMMENDED)
DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson

# Option C: Manual build
docker run --rm --runtime=nvidia \
    -v ./models/tensorrt:/root/.cache/tensorrt:rw \
    depth_anything_3_ros2:jetson \
    python3 /ros2_ws/src/depth_anything_3_ros2/scripts/build_tensorrt_engine.py --auto
```

**Outstanding Issue**: The original ONNX export problem remains unresolved. This workaround uses pre-exported ONNX models instead of direct PyTorch-to-ONNX conversion. Future work should investigate:
1. Patching DA3's DINOv2 forward pass for export compatibility
2. Implementing custom ONNX export wrapper that handles tensor shape differences
3. Contributing fix upstream to ByteDance/Depth-Anything-3

---

## Issue #20: Package Dependencies Too Large [NOT ADDRESSED]

**GitHub**: https://github.com/GerdsenAI/Depth-Anything-3-ROS2-Wrapper/issues/20

**Problem**: `pip install git+https://github.com/ByteDance-Seed/Depth-Anything-3.git` installs 7.4GB of packages.

**Root Cause**: This is an upstream dependency issue with ByteDance's Depth Anything 3 package.

**Possible Approaches**:
1. Fork and modify ByteDance's package to reduce dependencies
2. Create a minimal requirements subset for this wrapper
3. Document which dependencies are actually required at runtime vs. development

**Notes**: This is a quality-of-life improvement with limited control since it depends on upstream packaging decisions.

---

## Priority Order

1. **Issue #22** (High) - WORKAROUND IMPLEMENTED - TensorRT optimization now available via Docker
2. **Issue #20** (Low) - Quality-of-life improvement, upstream dependency issue

---

## Branch Status

**Branch**: `bug-fixes-01302026`

**Commits since main**:
- Docker configuration for Jetson deployment (COMPLETED)
  - Fixed PyTorch CUDA support (cu122 for L4T r36.2.0)
  - Fixed cv_bridge OpenCV version conflict
  - Fixed ARM64 package dependencies (pycolmap, open3d)
  - Fixed Windows line endings in ros_entrypoint.sh
  - Added OpenMPI and OpenBLAS runtime dependencies
- TensorRT optimization implementation (COMPLETED)
  - Added python3-dev, pycuda, huggingface_hub dependencies
  - Implemented build-time TensorRT engine building (optional)
  - Enhanced ros_entrypoint.sh with auto-build capability
  - Fixed docker-compose.yml GPU access and volume mounts
  - Updated OPTIMIZATION_GUIDE.md with FP16 recommendations
- CLAUDE.md updates with specialized agent instructions
- Documentation and changelog updates
- .gitignore updates for IDE, temporary files, and line endings
- Test suite enhancements (fixes #21)
- New `test/test_jetson_detector.py`
- New `config/model_catalog.yaml` and `scripts/setup_models.py`
- New `depth_anything_3_ros2/jetson_detector.py` for hardware detection

**Ready for Merge**:
- Issue #21 resolved
- Issue #22 workaround implemented
- Docker/Jetson deployment fully functional
- PyTorch CUDA verified on Jetson Orin AGX
- TensorRT optimization available via three build strategies
