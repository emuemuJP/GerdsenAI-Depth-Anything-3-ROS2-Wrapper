# Depth Anything 3 Optimization Roadmap

## Executive Summary

**Current State:** PyTorch inference @ ~5.2 FPS (193ms latency) on Jetson Orin NX 16GB
**Target:** TensorRT FP16 @ >20 FPS (preferably >30 FPS) at 518x518 resolution
**Status:** TensorRT BLOCKED - opset incompatibility discovered

---

## Critical Discovery: TensorRT Opset Incompatibility

### Issue Details

| Aspect | Details |
|--------|---------|
| **Problem** | TensorRT 8.6.2 (JetPack 6.0) supports max ONNX opset 17 |
| **DA3 Models** | Export with opset 18+ |
| **Result** | Native TensorRT acceleration blocked |
| **Discovered** | 2026-01-30 |

### Workaround Options (Under Investigation)

1. **ONNX Runtime with CUDA EP** - Use CUDA execution provider instead of TRT EP
2. **Re-export with opset 17** - Rebuild DA3 models from PyTorch source with lower opset
3. **Wait for JetPack upgrade** - TensorRT 10+ supports higher opsets

---

## Phase 1: TensorRT Validation [BLOCKED]

**Goal:** Confirm TensorRT pipeline works end-to-end
**Status:** BLOCKED by opset incompatibility
**Started:** 2026-01-30 22:10 CST

### Completed Checks
- [x] Verify TensorRT Environment: TensorRT 8.6.2 confirmed
- [x] Verify `trtexec` available
- [x] Confirm JetPack 6.x: L4T r36.2.0
- [x] Created deployment guide: `docs/JETSON_DEPLOYMENT_GUIDE.md`

### Blocked Items
- [ ] Build TensorRT engine - fails due to opset 18 operators
- [ ] Verify FPS improvement - blocked by above

**Root Cause:**
- Opset incompatibility confirmed (not the 5% risk scenario - it's 100%)
- DA3 models use opset 18 features not available in TensorRT 8.6.2

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
