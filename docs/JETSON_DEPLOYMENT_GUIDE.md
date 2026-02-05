# Jetson Deployment Guide - Depth Anything V3

## Validated Configuration

| Component | Version | Notes |
|-----------|---------|-------|
| Platform | Jetson Orin NX 16GB | [Seeed reComputer J4012](https://www.seeedstudio.com/reComputer-Robotics-J4012-with-GMSL-extension-board-p-6537.html) |
| JetPack | 6.2 (L4T R36.4) | Required for TRT 10.3 |
| TensorRT | 10.3.0.30 | Host-side inference |
| CUDA | 12.6 | Host |
| Performance | **40 FPS @ 518x518 FP16** | 7.7x speedup over PyTorch |
| Performance | **93 FPS @ 308x308 FP16** | 17.8x speedup over PyTorch |

---

## Architecture: Host-Container Split with Shared Memory IPC

Due to broken TensorRT Python bindings in available Jetson containers ([Issue #714](https://github.com/dusty-nv/jetson-containers/issues/714)), we use a split architecture with optimized shared memory IPC:

```
+---------------------------------------------------------------+
|                      HOST (JetPack 6.2+)                       |
|  +----------------------------------------------------------+  |
|  |      TRT Inference Service (trt_inference_service_shm.py) |  |
|  |  - Loads engine with host TensorRT 10.3                   |  |
|  |  - RAM-backed IPC via /dev/shm/da3 (numpy.memmap)         |  |
|  |  - ~15ms inference + ~8ms IPC = ~23ms total               |  |
|  +----------------------------------------------------------+  |
|                              ^                                  |
|                              | /dev/shm/da3 (shared memory)     |
|                              v                                  |
|  +----------------------------------------------------------+  |
|  |              Docker Container (L4T r36.4.0)               |  |
|  |  +----------------------------------------------------+  |  |
|  |  |              ROS2 Depth Node                       |  |  |
|  |  |  - SharedMemoryInferenceFast class                 |  |  |
|  |  |  - Subscribes to /image_raw                        |  |  |
|  |  |  - Publishes to /depth, /depth_colored             |  |  |
|  |  +----------------------------------------------------+  |  |
|  +----------------------------------------------------------+  |
+---------------------------------------------------------------+
```

**Why this approach:**
- `dustynv/l4t-pytorch:r36.4.0` has broken TensorRT Python bindings
- Using `dustynv/ros:humble-desktop-l4t-r36.4.0` (humble-pytorch variant doesn't exist)
- Container TRT 8.6.2 cannot build DA3 engines (DINOv2 incompatibility)
- Host TRT 10.3 works perfectly (validated at 25ms latency)

---

## Quick Start

```bash
cd ~/depth_anything_3_ros2
bash scripts/deploy_jetson.sh --host-trt
```

This script:
1. Verifies TensorRT 10.3 on host
2. Downloads ONNX model if missing (auto-installs huggingface_hub)
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

**Build time:** ~2 minutes | **Engine size:** ~64 MB

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

See [JETSON_BENCHMARKS.md](JETSON_BENCHMARKS.md) for comprehensive benchmarks.

### Quick Reference

| Configuration | FPS | Latency | Use Case |
|--------------|-----|---------|----------|
| DA3-Small @ 518x518 | 40 | 25ms | High quality |
| DA3-Small @ 400x400 | 64 | 16ms | Balanced |
| DA3-Small @ 308x308 | 93 | 11ms | Real-time robotics |
| DA3-Small @ 256x256 | 110 | 9ms | High-speed |

### Model Variants

| Model | FPS (518x518) | Latency | Engine Size |
|-------|---------------|---------|-------------|
| DA3-Small | 40 | 25ms | 64MB |
| DA3-Base | 19 | 51ms | 211MB |
| DA3-Large | 7.5 | 132ms | 674MB |

### Thermal Stability

10-minute sustained load test **PASSED**:
- Throughput: 40.79 FPS (stable)
- Latency variance: < 5%
- No thermal throttling detected

---

## Communication Protocol

### Production: Shared Memory IPC (`/dev/shm/da3`)

The host `trt_inference_service_shm.py` and container communicate via RAM-backed shared memory for minimal latency (~8ms IPC overhead):

| File | Direction | Format |
|------|-----------|--------|
| `/dev/shm/da3/input.bin` | Container -> Host | float32 memmap [1,1,3,518,518] |
| `/dev/shm/da3/output.bin` | Host -> Container | float32 memmap [1,518,518] |
| `/dev/shm/da3/request` | Container -> Host | Timestamp signal |
| `/dev/shm/da3/status` | Host -> Container | "ready", "complete:time", "error:msg" |

### Fallback: File-based IPC (`/tmp/da3_shared`)

The legacy file-based IPC is still supported for backward compatibility (~40ms IPC overhead):

| File | Direction | Format |
|------|-----------|--------|
| `/tmp/da3_shared/input.npy` | Container -> Host | float32 [1,1,3,518,518] |
| `/tmp/da3_shared/output.npy` | Host -> Container | float32 [1,518,518] |
| `/tmp/da3_shared/request` | Container -> Host | Timestamp signal |
| `/tmp/da3_shared/status` | Host -> Container | "ready", "complete:time", "error:msg" |

---

## Troubleshooting

### Host service not detecting requests

Check shared directory permissions (production uses `/dev/shm/da3`):
```bash
ls -la /dev/shm/da3/
# Should be readable/writable by both host user and container
# Fallback path: ls -la /tmp/da3_shared/
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
| `scripts/benchmark_resolutions.sh` | Resolution benchmark script |
| `scripts/benchmark_models.sh` | Model size benchmark script |
| `scripts/thermal_stability_test.sh` | Thermal validation script |
| `depth_anything_3_ros2/da3_inference.py` | Inference wrapper (shared memory support) |
| `models/tensorrt/da3-small-fp16.engine` | TRT engine (64 MB) |
| `docker-compose.yml` | Container config |

---

**Last Updated:** 2026-02-02
**Validated On:** Jetson Orin NX 16GB, JetPack 6.2, TensorRT 10.3.0.30
