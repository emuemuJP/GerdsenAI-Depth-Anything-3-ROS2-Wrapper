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
- [x] Created `scripts/deploy_jetson.sh` for automated deployment
- [x] Updated `docker-compose.yml` to mount host TRT 10.3

---

## Phase 2: Docker Integration [READY]

**Approach:** Mount host TensorRT 10.3 into r36.2.0 container (r36.4.0 ROS+PyTorch image doesn't exist)

### Deploy Command
```bash
bash scripts/deploy_jetson.sh
```

### What it does:
1. Verifies host TRT 10.3
2. Downloads ONNX model if missing  
3. Builds engine with host trtexec (~2 min)
4. Starts container with mounted TRT libs + engine

### Volume Mounts (docker-compose.yml)
```yaml
# Host TensorRT 10.3
- /usr/lib/aarch64-linux-gnu/libnvinfer.so.10.3.0:/usr/lib/aarch64-linux-gnu/libnvinfer.so.10:ro
- /usr/lib/aarch64-linux-gnu/libnvinfer_plugin.so.10.3.0:/usr/lib/aarch64-linux-gnu/libnvinfer_plugin.so.10:ro
- /usr/lib/aarch64-linux-gnu/libnvonnxparser.so.10.3.0:/usr/lib/aarch64-linux-gnu/libnvonnxparser.so.10:ro
- /usr/src/tensorrt:/usr/src/tensorrt:ro
# Pre-built engine
- ./models/tensorrt:/app/models/tensorrt:rw
```

---

## Phase 3: Resolution Tuning [PENDING]

| Resolution | Expected FPS |
|------------|--------------|
| 518x518 | 35 (validated) |
| 400x400 | ~45 |
| 308x308 | ~55 |

---

## Phase 4: Thermal Validation [PENDING]

- [ ] 10-minute sustained load test
- [ ] GPU temp monitoring (<80C target)
- [ ] FPS stability check

---

## Root Cause: Why TRT 8.6 Fails

DA3's DINOv2 backbone uses `F.scaled_dot_product_attention()` which exports as Einsum ops. TRT 8.6 cannot handle:
- Einsum with >2 inputs
- Missing ViT/MHA optimizations
- "caskConvolutionV2Forward" format errors

**Solution:** TRT 10.3+ has full DINOv2 support.

---

## Files

| File | Purpose |
|------|---------|
| `scripts/deploy_jetson.sh` | One-command deployment |
| `scripts/test_trt10.3_host.sh` | Host TRT validation |
| `models/onnx/da3-small-embedded.onnx` | ONNX model (101MB) |
| `models/tensorrt/da3-small-fp16.engine` | TRT engine (58MB) |
| `docs/JETSON_DEPLOYMENT_GUIDE.md` | Full documentation |

---

**Last Updated:** 2026-01-31
