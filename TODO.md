# Depth Anything 3 Optimization Roadmap

## Executive Summary

| Metric | PyTorch Baseline | TensorRT 10.3 FP16 |
|--------|------------------|-------------------|
| FPS | 5.2 | **35.3** |
| Latency | 193ms | **26.4ms** |
| Speedup | 1x | **6.8x** |
| Engine | N/A | 58MB |

**Platform:** Jetson Orin NX 16GB, JetPack 6.2.1, TensorRT 10.3.0.30

---

## Phase 1: TensorRT Validation [COMPLETE]

- [x] Confirmed TRT 8.6 cannot build DA3 (DINOv2/Einsum incompatibility)
- [x] Validated TRT 10.3 builds DA3 successfully on host
- [x] Fixed trtexec syntax for TRT 10.x (`--memPoolSize`, 5D shapes)
- [x] Host inference validated at 29.8ms latency

---

## Phase 2: Host-Container Split Architecture [COMPLETE]

**Problem:** Container TensorRT Python bindings are broken:
- `dustynv/l4t-pytorch:r36.4.0` - TRT import fails ([Issue #714](https://github.com/dusty-nv/jetson-containers/issues/714))
- `dustynv/ros:humble-pytorch-l4t-r36.4.0` - Does not exist
- Volume mounting TRT .so files works, but Python `tensorrt` module still broken

**Solution:** Host-container split architecture

```
HOST (TRT 10.3)                    CONTAINER (ROS2)
+------------------+               +------------------+
| TRT Inference    | <-- shared -> | ROS2 Node        |
| Service (Python) |    memory     | - /image_raw sub |
| - Loads engine   |               | - /depth pub     |
+------------------+               +------------------+
```

### Implementation (Complete)
- [x] `scripts/trt_inference_service.py` - Host TRT service with file-based IPC
- [x] `depth_anything_3_ros2/da3_inference.py` - SharedMemoryInference class with PyTorch fallback
- [x] `scripts/deploy_jetson.sh --host-trt` - Orchestrates host service + container startup

### Communication Protocol
| File | Direction | Format |
|------|-----------|--------|
| `/tmp/da3_shared/input.npy` | Container -> Host | float32 [1,1,3,518,518] |
| `/tmp/da3_shared/output.npy` | Host -> Container | float32 [1,518,518] |
| `/tmp/da3_shared/request` | Container -> Host | Timestamp signal |
| `/tmp/da3_shared/status` | Host -> Container | "ready", "complete:time", "error:msg" |

### Deployment
```bash
# Fresh Jetson deployment
cd ~
rm -rf ~/depth_anything_3_ros2 ~/ros2_ws ~/da3_fresh_test
git clone https://github.com/GerdsenAI/Depth-Anything-3-ROS2-Wrapper.git depth_anything_3_ros2
cd depth_anything_3_ros2
pip3 install pycuda --break-system-packages
bash scripts/deploy_jetson.sh --host-trt
```

---

## Phase 3: Resolution Tuning [PENDING]

| Resolution | Expected FPS |
|------------|--------------|
| 518x518 | 35 (validated) |
| 400x400 | ~45 |
| 308x308 | ~55 |

---

## Phase 4: Thermal/Stability Validation [PENDING]

- [ ] 10-minute sustained load test
- [ ] GPU temp monitoring (<80C target)
- [ ] FPS stability check

---

## Root Cause Summary

1. **TRT 8.6 fails** - DA3's DINOv2 uses Einsum ops TRT 8.6 can't compile
2. **TRT 10.3 works** - Validated on host at 29.8ms
3. **Container Python TRT broken** - `dustynv/l4t-pytorch:r36.4.0` has import error
4. **Solution** - Run TRT inference on host, ROS2 in container, communicate via shared memory

---

**Last Updated:** 2026-02-02
