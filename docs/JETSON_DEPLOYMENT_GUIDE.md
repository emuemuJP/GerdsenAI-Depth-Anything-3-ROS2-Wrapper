# Jetson Deployment Guide - Depth Anything V3

## Validated Configuration

| Component | Version | Notes |
|-----------|---------|-------|
| Platform | Jetson Orin NX 16GB | Seeed reComputer |
| JetPack | 6.2.1 (L4T R36.4.7) | Required for TRT 10.3 |
| TensorRT | 10.3.0.30 | Host-side inference |
| CUDA | 12.6.11 | Host |
| Performance | 35.3 FPS @ 518x518 FP16 | 6.8x speedup over PyTorch |

---

## Architecture: Host-Container Split

Due to broken TensorRT Python bindings in available Jetson containers ([Issue #714](https://github.com/dusty-nv/jetson-containers/issues/714)), we use a split architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                          HOST (JetPack 6.2+)                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │           TRT Inference Service (Python)                │    │
│  │  - Loads engine with host TensorRT 10.3                 │    │
│  │  - Watches /tmp/da3_shared/input.npy                    │    │
│  │  - Writes /tmp/da3_shared/output.npy                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              ▲                                   │
│                              │ shared memory                     │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Docker Container (L4T r36.2.0)             │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │              ROS2 Depth Node                    │    │    │
│  │  │  - Subscribes to /image_raw                     │    │    │
│  │  │  - Writes input to shared memory                │    │    │
│  │  │  - Reads depth from shared memory               │    │    │
│  │  │  - Publishes to /depth                          │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

**Why this approach:**
- `dustynv/l4t-pytorch:r36.4.0` has broken TensorRT Python bindings
- `dustynv/ros:humble-pytorch-l4t-r36.4.0` does not exist
- Container TRT 8.6.2 cannot build DA3 engines (DINOv2 incompatibility)
- Host TRT 10.3 works perfectly (validated at 29.8ms latency)

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
4. Starts host inference service
5. Starts Docker container with shared memory mount

---

## Manual Deployment

### Step 1: Verify Host TensorRT

```bash
/usr/src/tensorrt/bin/trtexec --version
# Expected: TensorRT v100300 (10.3.x)
```

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

**Build time:** ~2 minutes | **Engine size:** ~58 MB

### Step 3: Start Host Inference Service

```bash
# Terminal 1: Host inference service
python3 scripts/trt_inference_service.py \
  --engine models/tensorrt/da3-small-fp16.engine \
  --shared-dir /tmp/da3_shared
```

### Step 4: Start Container

```bash
# Terminal 2: ROS2 container
docker compose up depth-anything-3-jetson
```

### Step 5: Run ROS2 Node

Inside container:
```bash
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py use_shared_memory:=true
```

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

## Communication Protocol

The host service and container communicate via memory-mapped files:

| File | Direction | Format |
|------|-----------|--------|
| `/tmp/da3_shared/input.npy` | Container -> Host | float32 [1,1,3,518,518] |
| `/tmp/da3_shared/output.npy` | Host -> Container | float32 [1,518,518] |
| `/tmp/da3_shared/ready.flag` | Host -> Container | Empty file (signal) |
| `/tmp/da3_shared/request.flag` | Container -> Host | Empty file (signal) |

**Synchronization:**
1. Container writes `input.npy`, creates `request.flag`
2. Host detects `request.flag`, runs inference, writes `output.npy`, creates `ready.flag`
3. Container detects `ready.flag`, reads `output.npy`
4. Both delete flag files

---

## Troubleshooting

### Host service not detecting requests

Check shared directory permissions:
```bash
ls -la /tmp/da3_shared/
# Should be readable/writable by both host user and container
```

### Container cannot write to shared memory

Verify volume mount in `docker-compose.yml`:
```yaml
volumes:
  - /tmp/da3_shared:/tmp/da3_shared:rw
```

### Engine build fails with "Unknown option: --workspace"

TensorRT 10.x changed CLI syntax:
```bash
# Wrong (TRT 8.x)
--workspace=2048

# Correct (TRT 10.x)
--memPoolSize=workspace:2048MiB
```

### FPS lower than expected

1. Check host service is running
2. Verify GPU power mode: `sudo nvpmodel -q` (should be MAXN)
3. Enable max clocks: `sudo jetson_clocks`

---

## Files

| File | Purpose |
|------|---------|
| `scripts/deploy_jetson.sh` | Automated deployment |
| `scripts/trt_inference_service.py` | Host-side TRT inference |
| `depth_anything_3_ros2/da3_inference.py` | Inference wrapper (shared memory support) |
| `models/tensorrt/da3-small-fp16.engine` | TRT engine (58 MB) |
| `docker-compose.yml` | Container config |

---

**Last Updated:** 2026-01-31  
**Validated On:** Jetson Orin NX 16GB, JetPack 6.2.1, TensorRT 10.3.0.30
