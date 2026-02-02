# TensorRT Optimization Plan for Jetson Deployment

## Executive Summary

The TensorRT optimization plan is **approved** with critical updates from the recent audit.

**Audit Findings (Jan 30 2026):**
1. **Resolution Mismatch**: 1024x1024 resolution (used for Large models) is NOT divisible by 14 (ViT patch size), which serves as a hard constraint.
2. **Opset Compatibility**: Custom `ika-rwth-aachen` models (Opset 20) fail on TensorRT 8.6 due to missing Gelu plugin. Our plan uses `onnx-community` models which must be verified for compatibility.

**Verdict: PROCEED with Plan + Resolution Fixes**

---

## 1. Audit Analysis & Fixes

### A. Resolution Constraint (Critical)
**Finding**: ViT models require input dimensions divisible by 14.
- `1024 / 14 = 73.14` (INVALID)
- `1022 / 14 = 73.0` (VALID)
- `1036 / 14 = 74.0` (VALID)

**Fix**: Update `model_catalog.yaml` and `OPTIMIZATION_GUIDE.md` to use **1022** instead of 1024.

### B. TensorRT Compatibility
**Finding**: Logs show Opset 20 `Gelu` operator failure on TensorRT 8.6.
**Mitigation**: 
- Phase 3 uses `onnx-community` models. We must verify if they use Opset < 20 or if TRT 8.6 supports them.
- **Fallback**: If FP16 build fails, fallback to ONNX Runtime with TensorRT execution provider (Phase 4 extension).

---

## 2. Implementation Plan

### Phase 1: Fix Dependencies in Dockerfile

**File:** `Dockerfile`

**Changes:**
1. Add `python3-dev` to system dependencies.
2. Add `pycuda`, `huggingface_hub`, `onnxruntime-gpu` (fallback).

```dockerfile
RUN if [ "$BUILD_TYPE" = "jetson-base" ]; then \
        pip3 install --no-cache-dir pycuda huggingface_hub onnxruntime-gpu; \
    fi
```

### Phase 2: Add TensorRT Build Arguments

**File:** `Dockerfile`

Add `BUILD_TENSORRT`, `TENSORRT_MODEL`, `TENSORRT_PRECISION`.

### Phase 3: Implement Optional Engine Building

**File:** `Dockerfile`

Use `--auto` flag. **CRITICAL**: Update `scripts/build_tensorrt_engine.py` to target 1022 resolution for 'large' models instead of 1024.

### Phase 4: Enhance Entrypoint Script

**File:** `docker/ros_entrypoint.sh`

Add runtime auto-build logic with fallback warning.

### Phase 5: Fix docker-compose.yml

Add `NVIDIA_DRIVER_CAPABILITIES` and volume mounts.

### Phase 6: Update Configurations (Audit Fix)

**File:** `config/model_catalog.yaml`

Update all `1024` references to `1022`.

```yaml
AGX_ORIN_64GB:
  height: 1022  # Changed from 1024 (must be divisible by 14)
  width: 1022
```

---

## 3. Build Strategy Options

### Option A: Build-Time (Baked into Image)
- **Pros:** Fastest startup
- **Cons:** Platform-specific

### Option B: Runtime Auto-Build (Recommended)
- **Pros:** Flexible, one-time delay
- **Cons:** Startup delay on first run

---

## 4. Verification Plan

1. **Resolution Check**: Verify 1022x1022 works with `trtexec`.
2. **Opset Check**: Verify `onnx-community` model Opset version matches TRT 8.6 support.
3. **End-to-End**: Run `ros2 launch ...` with `log_inference_time:=true`.

---

## 5. Risk Config

| Risk | Mitigation |
|------|------------|
| Opset 20 not supported | Use older Opset export or ONNX Runtime fallback |
| Resolution mismatch | Enforce mod-14 resolutions (1022, 518, 308) |
| System Memory OOM | 1022x1022 requires ~4.5GB VRAM (Safe for AGX) |

---

## Immediate Next Steps (Audit Response)

1. **Update `model_catalog.yaml`**: Change 1024 -> 1022.
2. **Update Docs**: Reflect 1022 as Ultra resolution.
3. **Proceed with Docker fixes**: Implement dependencies and build args.
