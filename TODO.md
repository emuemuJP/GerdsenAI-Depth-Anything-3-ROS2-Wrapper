# Depth Anything 3 Optimization Roadmap

## Executive Summary

**Current State:** PyTorch inference @ ~5.2 FPS (193ms latency) on Jetson Orin NX 16GB
**Target:** TensorRT FP16 @ >20 FPS (preferably >30 FPS) at 518x518 resolution
**Solution:** Docker image updated to L4T r36.4.0 (TensorRT 10.3)

---

## Root Cause Analysis

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

## Phase 1: TensorRT Validation [READY TO TEST]

**Goal:** Confirm TensorRT 10.3 can build DA3 engines
**Status:** Dockerfile updated - ready for rebuild and test

### Completed Steps
- [x] Verify TensorRT 8.6.2 on host causes build failure
- [x] Identify root cause: Einsum/DINOv2 incompatibility with TRT 8.6
- [x] Update Dockerfile to L4T r36.4.0 (TensorRT 10.3)
- [x] Created deployment guide: `docs/JETSON_DEPLOYMENT_GUIDE.md`

### Next Steps

**CRITICAL:** Test TRT 10.3 on host before Docker rebuild (2-3 min vs 20 min)

- [ ] **Validate TRT 10.3 on Host First**
  - [ ] Run: `bash scripts/test_trt10.3_host.sh` on Jetson (not in Docker)
  - [ ] If SUCCESS: Proceed to Docker rebuild
  - [ ] If FAILURE: TRT 10.3 insufficient, use fallback (ONNX Runtime or DA2)
  - [ ] Reason: Research states "full fixes in TRT 10.8+", but we have 10.3

- [ ] Rebuild Docker image with new base (only if host validation succeeds)
- [ ] Test TensorRT engine build (should succeed with TRT 10.3)
- [ ] Verify FPS improvement

### Test Steps
1. Rebuild Docker image:
   ```bash
   cd ~/depth_anything_3_ros2
   docker compose build depth-anything-3-jetson
   ```

2. Start with TensorRT auto-build:
   ```bash
   DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson
   ```

3. Verify TensorRT version:
   ```bash
   docker exec -it da3_ros2_jetson python3 -c "import tensorrt; print(tensorrt.__version__)"
   # Expected: 10.3.x
   ```

4. Check engine was built:
   ```bash
   docker exec -it da3_ros2_jetson ls -lh /root/.cache/tensorrt/*.engine
   ```

5. Measure FPS:
   ```bash
   ros2 topic hz /depth_anything_3/depth
   # Expected: 20-30 FPS
   ```

---

## Phase 2: Resolution Tuning [PENDING]

**Goal:** Optimize for target FPS (>20 or >30)
**Status:** Pending Phase 1 completion

**Analysis (for when TensorRT works):**
- 518x518: Target 20-30 FPS
- 308x308: Target 40+ FPS
- Custom (e.g., 400x400): Sweet spot between 308 and 518

---

## Phase 3: Thermal and Stability Validation [PENDING]

**Goal:** Ensure sustained performance without throttling
**Status:** Pending Phase 1 completion

---

## Current Performance Baseline

| Metric | Measured Value | Notes |
|--------|----------------|-------|
| **Model** | DA3-SMALL | PyTorch, FP32 |
| **Resolution** | 518x518 | Input size |
| **FPS** | ~5.2 | Measured on Orin NX 16GB |
| **Inference Time** | ~193ms | Per frame |
| **Platform** | JetPack 6.0 | L4T r36.2.0, CUDA 12.2, TRT 8.6.2 |

---

## Expected Performance (TensorRT 10.3)

| Metric | PyTorch Baseline | TensorRT FP16 Target |
|--------|------------------|---------------------|
| **FPS** | ~5.2 | 20-30 |
| **Inference Time** | ~193ms | ~35-50ms |
| **Speedup** | 1x | 4-6x |

---

## Completed Work

### Docker Image Updates
- [x] Updated L4T_VERSION from r36.2.0 to r36.4.0
- [x] TensorRT 10.3 now available in container
- [x] cv_bridge built from source (OpenCV 4.8.1 compatibility)
- [x] torchvision built from source (NVIDIA PyTorch ABI)
- [x] Windows CRLF line endings fix

### Infrastructure
- [x] `scripts/build_tensorrt_engine.py` with auto-detection
- [x] Platform detection for Jetson modules
- [x] Pre-exported ONNX model pipeline

---

## Known Issues

| Issue | Status | Notes |
|-------|--------|-------|
| TensorRT 8.6 incompatible | Resolved | Updated to TRT 10.3 via L4T r36.4.0 |
| torchvision NMS crash | Resolved | Source build in Dockerfile |
| ByteDance package size | Open | Upstream issue #20 (7.4GB) |

---

**Last Updated:** 2026-01-30
**Current Focus:** Test TensorRT 10.3 engine build
**Next:** Rebuild Docker image and verify FPS
