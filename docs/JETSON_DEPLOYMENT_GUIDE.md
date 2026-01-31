# Jetson Deployment Guide - Depth Anything V3

## Validated Configuration

| Component | Version | Notes |
|-----------|---------|-------|
| Platform | Jetson Orin NX 16GB | Seeed reComputer |
| JetPack | 6.2.1 (L4T R36.4.7) | Required for TRT 10.3 |
| TensorRT | 10.3.0.30 | Host install, mounted into container |
| CUDA | 12.6.11 | Host |
| Performance | 35.3 FPS @ 518x518 FP16 | 6.8x speedup over PyTorch |

**Key Discovery:** TensorRT 8.6 (in older containers) cannot compile DA3's DINOv2 backbone. TRT 10.3+ required.

---

## Quick Start

```bash
cd ~/depth_anything_3_ros2
bash scripts/deploy_jetson.sh
```

This script:
1. Verifies TensorRT 10.3 on host
2. Downloads ONNX model if missing
3. Builds TensorRT FP16 engine (~2 min)
4. Starts Docker container with engine mounted

---

## Manual Deployment

### Step 1: Verify Host TensorRT

```bash
/usr/src/tensorrt/bin/trtexec --version
# Expected: TensorRT v100300 (10.3.x)
```

If TensorRT <10.3, upgrade to JetPack 6.2+.

### Step 2: Build TensorRT Engine

```bash
mkdir -p models/tensorrt

/usr/src/tensorrt/bin/trtexec \
  --onnx=models/onnx/da3-small-embedded.onnx \
  --saveEngine=models/tensorrt/da3-small-fp16.engine \
  --fp16 \
  --memPoolSize=workspace:2048MiB \
  --optShapes=pixel_values:1x1x3x518x518
```

**Build time:** ~2 minutes  
**Engine size:** ~58 MB

### Step 3: Start Container

```bash
docker compose up depth-anything-3-jetson
```

The `docker-compose.yml` mounts:
- Pre-built engine from `./models/tensorrt/`
- Host TensorRT 10.3 libraries into container

### Step 4: Run Inference

Inside container:
```bash
source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash

ros2 launch depth_anything_3_ros2 depth_inference.launch.py
```

---

## Architecture

```
Host (JetPack 6.2+)
+-- TensorRT 10.3.0.30 (/usr/lib/aarch64-linux-gnu/libnvinfer.so.10.3.0)
+-- trtexec (/usr/src/tensorrt/bin/trtexec)
+-- Pre-built engine (models/tensorrt/da3-small-fp16.engine)
    |
    | volume mounts
    v
Container (L4T r36.2.0 base)
+-- ROS2 Humble
+-- PyTorch 2.3.0
+-- TensorRT 10.3 (mounted from host)
+-- Engine (mounted from host)
```

**Why this approach:**
- `dustynv/ros:humble-pytorch-l4t-r36.4.0` does not exist
- Container TRT 8.6 cannot build DA3 engines
- Host TRT 10.3 works, so we mount it

---

## Performance Results

| Metric | Value |
|--------|-------|
| Throughput | 35.3 FPS |
| Latency (median) | 26.7 ms |
| Latency (p95) | 33.3 ms |
| GPU Temp | 44-45C |
| Speedup | 6.8x vs PyTorch |

### Resolution Options

| Resolution | Expected FPS | Use Case |
|------------|--------------|----------|
| 518x518 | ~35 FPS | High quality |
| 400x400 | ~45 FPS | Balanced |
| 308x308 | ~55 FPS | High speed |

---

## Troubleshooting

### Engine build fails with "Unknown option: --workspace"

TensorRT 10.x changed CLI syntax:
```bash
# Wrong (TRT 8.x)
--workspace=2048

# Correct (TRT 10.x)
--memPoolSize=workspace:2048MiB
```

### "caskConvolutionV2Forward could not find any supported formats"

TensorRT version too old. DA3's DINOv2 backbone requires TRT 10.3+.

**Solution:** Use host TRT 10.3, not container TRT 8.6.

### Container cannot find libnvinfer.so.10

Volume mount paths incorrect. Verify in `docker-compose.yml`:
```yaml
volumes:
  - /usr/lib/aarch64-linux-gnu/libnvinfer.so.10.3.0:/usr/lib/aarch64-linux-gnu/libnvinfer.so.10:ro
```

### FPS lower than expected

1. Verify engine loaded (not falling back to PyTorch)
2. Check GPU power mode: `sudo nvpmodel -q` (should be MAXN)
3. Enable max clocks: `sudo jetson_clocks`

---

## Files

| File | Purpose |
|------|---------|
| `scripts/deploy_jetson.sh` | Automated deployment |
| `scripts/test_trt10.3_host.sh` | Host TRT validation |
| `models/onnx/da3-small-embedded.onnx` | ONNX model (101 MB) |
| `models/tensorrt/da3-small-fp16.engine` | TRT engine (58 MB) |
| `docker-compose.yml` | Container config with TRT mounts |

---

**Last Updated:** 2026-01-31  
**Validated On:** Jetson Orin NX 16GB, JetPack 6.2.1, TensorRT 10.3.0.30
