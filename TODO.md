# Depth Anything 3 Optimization Roadmap

## Executive Summary

**Current State:** PyTorch inference @ ~5.2 FPS (193ms latency) on Jetson Orin NX 16GB
**Target:** TensorRT FP16 @ >20 FPS (preferably >30 FPS) at 518x518 resolution
**Solution:** Upgrade to JetPack 6.2 (TensorRT 10.3)

---

## Root Cause Analysis

### Why TensorRT 8.6 Cannot Build DA3 Engines

The DINOv2 backbone at DA3's core uses `F.scaled_dot_product_attention()` which exports to ONNX as complex Einsum operations. TensorRT 8.6 has fundamental limitations:

| Limitation | Impact |
|------------|--------|
| **Einsum restrictions** | TRT 8.6 does not support >2 inputs, ellipsis notation, or diagonal operations |
| **Missing ViT optimizations** | No Multi-Head Attention fusion for Vision Transformers |
| **Format incompatibility** | "caskConvolutionV2Forward" error - no compatible CUDA kernels |

**Confirmed:** NVIDIA TensorRT GitHub Issue #4537 documents these DINOv2 compilation failures. Full fixes arrived in TensorRT 10.8+.

### Solution: JetPack 6.2 Upgrade

| Component | JetPack 6.0 (Current) | JetPack 6.2 (Target) |
|-----------|----------------------|---------------------|
| TensorRT | 8.6 | **10.3** |
| CUDA | 12.2 | 12.6 |
| cuDNN | 8.9 | 9.3 |
| ViT Support | Limited | Enhanced MHA fusion |
| Bonus | - | 70% AI TOPS boost (Super Mode) |

**Upgrade Command:**
```bash
sudo apt-add-repository universe
sudo apt-add-repository multiverse
sudo apt-get update
sudo apt-get install nvidia-jetpack
sudo reboot
```

**Documentation:** See `docs/TENSORRT_DA3_PLAN.md` for full analysis.

---

## Phase 1: TensorRT Validation [READY TO TEST]

**Goal:** Confirm TensorRT pipeline works end-to-end
**Status:** Dockerfile updated - ready for rebuild and test
**Started:** 2026-01-30 22:10 CST

### Completed Steps
- [x] Verify TensorRT Environment: TensorRT 8.6.2 confirmed on host
- [x] Identify root cause: Docker base image using L4T r36.2.0 (TRT 8.6)
- [x] Update Dockerfile: Changed to L4T r36.4.0 (TRT 10.3)
- [x] Created deployment guide: `docs/JETSON_DEPLOYMENT_GUIDE.md`
- [x] Created research analysis: `docs/TENSORRT_DA3_PLAN.md`

### Next Steps
- [ ] Rebuild Docker image with new base
- [ ] Test TensorRT engine build (should succeed with TRT 10.3)
- [ ] Verify FPS improvement

---

## Phase 2: Resolution Tuning [ON HOLD]

**Goal:** Optimize for target FPS (>20 or >30)
**Status:** ON HOLD pending TensorRT resolution

**Analysis (for when TensorRT works):**
- 518x518: Target 20-25 FPS
- 308x308: Target 40+ FPS
- Custom (e.g., 400x400): Sweet spot between 308 and 518

---

## Phase 3: Thermal and Stability Validation [ON HOLD]

**Goal:** Ensure sustained performance without throttling
**Status:** ON HOLD pending TensorRT resolution

---

## Current Performance Baseline

| Metric | Measured Value | Notes |
|--------|----------------|-------|
| **Model** | DA3-SMALL | PyTorch, FP32 |
| **Resolution** | 518x518 | Input size |
| **FPS** | ~5.2 | Measured on Orin NX 16GB |
| **Inference Time** | ~193ms | Per frame |
| **Platform** | JetPack 6.0 | L4T r36.2.0, CUDA 12.2 |
| **GPU Memory** | ~2GB | Estimated |

### Measurement Commands

```bash
# Terminal 1: Run node with logging
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw \
  model_name:=depth-anything/DA3-SMALL \
  log_inference_time:=true

# Terminal 2: Measure publish rate
ros2 topic hz /depth_anything_3/depth

# Terminal 3: Monitor GPU
watch -n 1 nvidia-smi
```

---

## Contingency Plans (Active)

### Current Strategy: PyTorch Optimization

Since TensorRT is blocked, focus on PyTorch-based optimizations:

1. **Use smaller models** - DA3-SMALL is current recommendation
2. **Reduce resolution** - 308x308 for faster inference
3. **Profile pipeline** - Identify non-inference bottlenecks

### Future Options

**Option 1: ONNX Runtime with CUDA EP**
- Expected: ~2x speedup over PyTorch
- Does not require opset 18 TensorRT support

**Option 2: Re-export models with opset 17**
- Requires access to PyTorch source
- May require patching DINOv2 backbone

**Option 3: Wait for TensorRT 10+**
- JetPack updates typically include TensorRT updates
- Timeline unknown

---

## Completed Work

### Docker/Jetson Deployment
- [x] Verified on Orin NX 16GB (L4T r36.2.0)
- [x] Fixed PyTorch/CUDA mismatch (NVIDIA wheels)
- [x] Fixed cv_bridge OpenCV conflict (source build)
- [x] Fixed torchvision NMS operator (source build required)
- [x] Patched ARM64 dependencies (api.py runtime patches)
- [x] Fixed Windows CRLF line endings in entrypoint

### Infrastructure
- [x] Added `scripts/build_tensorrt_engine.py` with auto-detection
- [x] Platform detection for Jetson modules
- [x] Pre-exported ONNX model pipeline configured

---

## Future Optimization Roadmap

### Post-TensorRT Resolution

1. **DLA Support (Experimental)**
   - Orin NX has 1x DLA core for power efficiency
   - May reduce power consumption by 30-40%
   - Trade-off: Some ViT ops (Gelu, LayerNorm) fall back to GPU

2. **INT8 Quantization**
   - Further 1.5x-2x speedup over FP16
   - Requires calibration dataset
   - May reduce accuracy by 3-5%

3. **Direct ONNX Export**
   - Remove dependency on pre-exported models
   - Requires patching DINOv2 backbone for dynamic shapes

---

## Known Issues

| Issue | Priority | Status | Notes |
|-------|----------|--------|-------|
| TensorRT opset 18 incompatibility | Critical | Blocked | JetPack 6.0 TensorRT 8.6.2 max opset 17 |
| ByteDance package size (7.4GB) | Low | Blocked | Upstream issue #20 |
| Resolution must be divisible by 14 | Medium | Fixed | Using 518 (ViT patch size requirement) |

---

**Last Updated:** 2026-01-30
**Current Focus:** Document baseline, investigate opset workarounds
**Blocker:** TensorRT opset 18 incompatibility
