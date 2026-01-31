# Depth Anything 3 Optimization Roadmap

## Executive Summary

**Current State:** TensorRT FP16 @ 35.3 FPS (26.4ms latency) on Jetson Orin NX 16GB
**Previous:** PyTorch FP32 @ ~5.2 FPS (193ms latency)
**Speedup:** 6.8x achieved with TensorRT 10.3

---

## Phase 1: TensorRT Validation [COMPLETE]

**Goal:** Confirm TensorRT 10.3 can build DA3 engines
**Status:** VALIDATED - 6.8x speedup confirmed

### Validated Performance

| Metric | PyTorch Baseline | TensorRT 10.3 FP16 |
|--------|-----------------|-------------------|
| **FPS** | ~5.2 | **35.3** |
| **Inference** | ~193ms | **26.4ms** |
| **Speedup** | 1x | **6.8x** |
| **Engine Size** | N/A | 58MB |

### Completed Steps
- [x] Verify TensorRT 8.6.2 on host causes build failure
- [x] Identify root cause: Einsum/DINOv2 incompatibility with TRT 8.6
- [x] Update Dockerfile to L4T r36.4.0 (TensorRT 10.3)
- [x] Created deployment guide: `docs/JETSON_DEPLOYMENT_GUIDE.md`
- [x] Validate TRT 10.3 on host: `bash scripts/test_trt10.3_host.sh`
- [x] Confirmed: TensorRT 10.3 CAN build DA3 engines
- [x] Updated Dockerfile base image to `humble-pytorch-l4t-r36.4.0`

### Test Script Fixes Applied
- [x] TRT 10.x syntax: `--memPoolSize=workspace:2048MiB` (not `--workspace`)
- [x] 5D input shape: `pixel_values:1x1x3x518x518`
- [x] Robust version detection for TRT 10.x

---

## Phase 2: Docker Integration [IN PROGRESS]

**Goal:** Rebuild Docker image and verify full ROS2 integration
**Status:** Ready for Docker rebuild

### Next Steps
- [ ] Rebuild Docker image with new base
  ```bash
  cd ~/depth_anything_3_ros2
  docker compose build depth-anything-3-jetson
  ```
- [ ] Test TensorRT engine build inside container
- [ ] Verify ROS2 node with TensorRT backend
- [ ] Measure sustained FPS with camera input

### Test Commands
```bash
# Start with TensorRT auto-build
DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson

# Verify TensorRT version
docker exec -it da3_ros2_jetson python3 -c "import tensorrt; print(tensorrt.__version__)"
# Expected: 10.3.x

# Check engine was built
docker exec -it da3_ros2_jetson ls -lh /root/.cache/tensorrt/*.engine

# Measure FPS
ros2 topic hz /depth_anything_3/depth
# Expected: 30-35 FPS
```

---

## Phase 3: Resolution Tuning [PENDING]

**Goal:** Optimize for different use cases
**Status:** Pending Phase 2 completion

**Expected Performance (based on host validation):**
- 518x518: ~35 FPS (validated)
- 308x308: ~50+ FPS (estimated)

---

## Phase 4: Thermal and Stability Validation [PENDING]

**Goal:** Ensure sustained performance without throttling
**Status:** Pending Phase 2 completion

---

## Root Cause Analysis (Historical)

### Why TensorRT 8.6 Cannot Build DA3 Engines

The DINOv2 backbone at DA3's core uses `F.scaled_dot_product_attention()` which exports to ONNX as complex Einsum operations. TensorRT 8.6 has fundamental limitations:

| Limitation | Impact |
|------------|--------|
| **Einsum restrictions** | TRT 8.6 does not support >2 inputs, ellipsis notation, or diagonal operations |
| **Missing ViT optimizations** | No Multi-Head Attention fusion for Vision Transformers |
| **Format incompatibility** | "caskConvolutionV2Forward" error - no compatible CUDA kernels |

**Confirmed:** NVIDIA TensorRT GitHub Issue #4537 documents these DINOv2 compilation failures.

### Solution: L4T r36.4.0 Docker Image

| Component | L4T r36.2.0 (Previous) | L4T r36.4.0 (Current) |
|-----------|------------------------|----------------------|
| TensorRT | 8.6.2 | **10.3** |
| CUDA | 12.2 | 12.6 |
| cuDNN | 8.9 | 9.3 |
| ViT Support | Limited | Enhanced MHA fusion |
| Bonus | - | 70% AI TOPS boost (Super Mode) |

---

## Completed Work

### Docker Image Updates
- [x] Updated L4T_VERSION from r36.2.0 to r36.4.0
- [x] Changed base image to `humble-pytorch-l4t-r36.4.0`
- [x] TensorRT 10.3 now available in container
- [x] cv_bridge built from source (OpenCV 4.8.1 compatibility)
- [x] torchvision built from source (NVIDIA PyTorch ABI)
- [x] Windows CRLF line endings fix

### Infrastructure
- [x] `scripts/build_tensorrt_engine.py` with auto-detection
- [x] `scripts/test_trt10.3_host.sh` for pre-Docker validation
- [x] Platform detection for Jetson modules
- [x] Pre-exported ONNX model pipeline
- [x] TRT 10.x syntax fixes (`--memPoolSize`, 5D shapes)

---

## Known Issues

| Issue | Status | Notes |
|-------|--------|-------|
| TensorRT 8.6 incompatible | Resolved | Updated to TRT 10.3 via L4T r36.4.0 |
| torchvision NMS crash | Resolved | Source build in Dockerfile |
| ByteDance package size | Open | Upstream issue #20 (7.4GB) |

---

**Last Updated:** 2026-01-31
**Current Focus:** Docker rebuild and ROS2 integration test
**Next:** Rebuild Docker image with L4T r36.4.0
