# Project Tasks & Status

## Open Issues

| Issue | Title | Priority | Status | Notes |
|-------|-------|----------|--------|-------|
| #20 | [Question] Package dependencies too large | Low | Blocked | Upstream issue with ByteDance package size (7.4GB) |
| - | **Monitor Thermal Performance** | Medium | Planned | Check throttling during sustained TensorRT runs |
| - | **Verify TensorRT Performance** | High | In Progress | Validate >20FPS target on Orin NX |

## Future Optimization Roadmap

1.  **Direct ONNX Export Support**
    *   *Goal*: Remove dependency on pre-exported models.
    *   *Task*: Patch DA3's DINOv2 backbone to handle dynamic tensor shapes during tracing.

## Recently Completed (bug-fixes-01302026)

*   **Docker/Jetson Deployment**
    *   Verified working on Orin AGX (L4T r36.2.0).
    *   Solved PyTorch/CUDA mismatch (Fixed: use NVIDIA wheels).
    *   Solved `cv_bridge` OpenCV version conflict (Fixed: build without tests).
    *   Solved `torchvision` NMS operator issue (Fixed: source build).
    *   Patched `api.py` for missing ARM64 dependencies (`evo`, `pycolmap`).

*   **TensorRT Infrastructure**
    *   Added `scripts/build_tensorrt_engine.py` (Auto-builds from ONNX).
    *   Integrated transparent engine building into `ros_entrypoint.sh`.
    *   Updated Dockerfile with `pycuda` and `tensorrt` dependencies.

*   **Testing & CI**
    *   Added `test_jetson_detector.py`.
    *   Fixed `colcon test` failures (ROS2 availability detection).
