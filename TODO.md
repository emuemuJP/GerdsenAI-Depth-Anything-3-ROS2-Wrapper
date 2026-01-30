# TODO - Open GitHub Issues

## Overview

This document tracks open GitHub issues and their current status in the `bug-fixes-01302026` branch.

| Issue | Title | Priority | Status |
|-------|-------|----------|--------|
| #22 | [Bug] Optimize scripts problem | High | Not addressed |
| #21 | [Bug] Test failed | - | Addressed in current branch |
| #20 | [Question] Package dependencies too large | Low | Not addressed (upstream issue) |
| - | Docker/Jetson Deployment | - | COMPLETED |

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

## Issue #22: Optimize Scripts Problem [NOT ADDRESSED]

**GitHub**: https://github.com/GerdsenAI/Depth-Anything-3-ROS2-Wrapper/issues/22

**Problem**: TensorRT/ONNX export fails with:
```
ValueError: not enough values to unpack (expected 5, got 4)
```

**Location**: `depth_anything_3/model/dinov2/vision_transformer.py:301`
```python
B, S, _, H, W = x.shape  # expects 5D tensor, gets 4D
```

**Root Cause**: Depth Anything 3's DINOv2 backbone has a different tensor shape during tracing/export than during normal inference. The `get_intermediate_layers` method expects 5D input but receives 4D during ONNX tracing.

**Affected Files**:
- `examples/scripts/optimize_tensorrt.py`
- `examples/scripts/performance_tuning.py`

**Next Steps**:
1. Investigate torch2trt compatibility with DA3's DINOv2 backbone
2. Consider custom ONNX export wrapper that handles tensor shape differences during tracing
3. May require patching the upstream model's forward pass for export mode

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

1. **Issue #22** (High) - Blocks users from TensorRT optimization on Jetson, which is a core use case
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
- CLAUDE.md updates with specialized agent instructions
- Documentation and changelog updates
- .gitignore updates for IDE, temporary files, and line endings
- Test suite enhancements (fixes #21)
- New `test/test_jetson_detector.py`
- New `config/model_catalog.yaml` and `scripts/setup_models.py`
- New `depth_anything_3_ros2/jetson_detector.py` for hardware detection

**Ready for Merge**:
- Issue #21 resolved
- Docker/Jetson deployment fully functional
- PyTorch CUDA verified on Jetson Orin AGX
