# Optimization Guide: Achieving >30 FPS on Jetson

This guide explains how to achieve optimal performance with Depth Anything 3 on NVIDIA Jetson platforms.

---

## Quick Reference by Platform

Use this table to find the recommended configuration for your Jetson:

| Platform | VRAM | Recommended Model | Resolution | Expected FPS | Memory Usage |
|----------|------|-------------------|------------|--------------|--------------|
| **Orin Nano 4GB** | 4GB shared | DA3-Small | 308x308 | 40-45 | ~1.2GB |
| **Orin Nano 8GB** | 8GB shared | DA3-Small | 308x308 | 45-50 | ~1.2GB |
| **Orin NX 8GB** | 8GB shared | DA3-Small | 308x308 | 50-55 | ~1.2GB |
| **Jetson Orin NX 16GB**\* | 16GB shared | DA3-Small | 518x518 | **43+ (validated)** | ~1.8GB |
| **AGX Orin 32GB** | 32GB shared | DA3-Base | 518x518 | 25-35 | ~2.5GB |
| **AGX Orin 64GB** | 64GB shared | DA3-Base/Large | 518x518 | 20-35 | ~2.5-4GB |
| **Xavier NX** | 8GB shared | DA3-Small | 308x308 | 15-25* | ~1.2GB |

*Xavier NX requires JetPack 5.x with TensorRT 8.5+ (limited DA3 support)

\*Validated on [Seeed reComputer J4012](https://www.seeedstudio.com/reComputer-Robotics-J4012-with-GMSL-extension-board-p-6537.html)

**Key Notes:**
- FPS values are TensorRT processing capacity. Real-world FPS may be limited by camera input rate (~24 FPS for USB cameras)
- Use `./run.sh` for one-click deployment with automatic configuration
- All platforms use FP16 precision for optimal speed/accuracy balance

### Model Selection Guide

| Model | Parameters | Best For | Min VRAM |
|-------|------------|----------|----------|
| **DA3-Small** | ~24M | Real-time robotics, obstacle avoidance | 4GB |
| **DA3-Base** | ~97M | Balanced quality/speed, general use | 8GB |
| **DA3-Large** | ~335M | High-quality depth, slower inference | 16GB |

---

## TensorRT Status (2026-02-05)

**TensorRT acceleration validated on Jetson Orin NX 16GB ([Seeed reComputer J4012](https://www.seeedstudio.com/reComputer-Robotics-J4012-with-GMSL-extension-board-p-6537.html)).**

| Component | Previous (L4T r36.2.0) | Current (L4T r36.4.0) |
|-----------|------------------------|----------------------|
| TensorRT | 8.6.2 (incompatible) | **10.3** (validated) |
| CUDA | 12.2 | 12.6 |
| cuDNN | 8.9 | 9.3 |

**Root Cause (Resolved)**: TensorRT 8.6 could not compile DINOv2's Einsum operations. TensorRT 10.3 has enhanced ViT/MHA support.

**Validated Performance (2026-01-31)**:
- Platform: Jetson Orin NX 16GB
- Model: DA3-SMALL at 518x518 FP16
- Throughput: 35.3 FPS
- GPU Latency: 26.4ms median (25.5ms min)
- Engine Size: 58MB
- Speedup: 6.8x over PyTorch baseline

**To enable TensorRT:**
```bash
# Rebuild Docker image with new base
docker compose build depth-anything-3-jetson

# Run with auto TensorRT engine build
DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson
```

---

## Current Architecture (2026-02-04) - Optimized

**Shared Memory IPC** (`/dev/shm/da3`) achieves 23+ FPS, limited only by camera input rate.

| Architecture | TRT Inference | IPC Overhead | Total | FPS |
|--------------|---------------|--------------|-------|-----|
| Native (target) | ~26ms | 0ms | ~26ms | ~38 |
| Host-Container File IPC (old) | ~50ms | ~40ms | ~90ms | ~11 |
| **Host-Container Shared Memory (current)** | **~15ms** | **~8ms** | **~23ms** | **43+ capacity** |

**Optimization Complete:** TensorRT runs on host, ROS2 in container. Communication via `/dev/shm/da3/` using numpy.memmap reduces IPC overhead to ~8ms. Processing capacity is 43+ FPS; actual output limited by camera input (~24 FPS).

**To use optimized mode:**
```bash
# run.sh automatically uses shared memory TRT service
./run.sh
```

---

## Validated Performance on Jetson Orin NX 16GB

### PyTorch Baseline

Measured on Jetson Orin NX 16GB (JetPack 6.0, L4T r36.2.0, CUDA 12.2):

| Model | Backend | Resolution | FPS | Inference Time |
|-------|---------|------------|-----|----------------|
| DA3-SMALL | PyTorch FP32 | 518x518 | ~5.2 | ~193ms |

### TensorRT 10.3 (Validated 2026-01-31)

Measured on Jetson Orin NX 16GB (L4T r36.4.0, TensorRT 10.3):

| Model | Backend | Resolution | FPS | GPU Latency | Engine Size | Speedup |
|-------|---------|------------|-----|-------------|-------------|---------|
| DA3-SMALL | TensorRT FP16 | 518x518 | 35.3 | 26.4ms median (25.5ms min) | 58MB | 6.8x |

---

## Performance Targets (Future - TensorRT)

- **Input**: 1080p camera (1920x1080) at 30 FPS
- **Output**: 1080p depth + confidence maps
- **Target FPS**: >30 FPS sustained
- **Platform**: NVIDIA Jetson Orin AGX 64GB

## Quick Start

### Option 1: PyTorch FP32 (Development/Baseline Only) - ~5 FPS

**WARNING: NOT for production use.** PyTorch mode is provided only for development testing and as a performance baseline. For production deployment, use Option 2 (TensorRT).

Works out of the box, no TensorRT engine build required:

```bash
# Configure your webcam for 1080p MJPEG
ros2 run v4l2_camera v4l2_camera_node --ros-args \
  -p image_size:="[1920,1080]" \
  -p pixel_format:="MJPEG" \
  -r __ns:=/camera &

# Launch optimized node
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw \
  model_name:=depth-anything/DA3-SMALL \
  backend:=pytorch \
  model_input_height:=384 \
  model_input_width:=384
```

### Option 2: TensorRT FP16 (Recommended) - >30 FPS Target

Requires Docker image rebuild and one-time model conversion:

```bash
# Step 1: Build TensorRT engine with auto-detection (recommended)
# This auto-detects your Jetson platform and uses optimal settings
python3 scripts/build_tensorrt_engine.py --auto

# Or specify model and precision manually:
python3 scripts/build_tensorrt_engine.py \
  --model da3-small \
  --precision fp16 \
  --resolution 308

# Step 2: Launch with TensorRT backend
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw \
  backend:=tensorrt_native \
  trt_model_path:=/root/.cache/tensorrt/da3-small_fp16_308x308_*.engine
```

### Option 3: Docker Deployment (Recommended)

Build with L4T r36.4.0 base and run with automatic TensorRT engine building:

```bash
# Build the Jetson image
docker compose build depth-anything-3-jetson

# Run with auto TensorRT engine building on first start
DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson

# Or build engine at image build time (slower build, faster first run)
docker compose build depth-anything-3-jetson \
  --build-arg BUILD_TENSORRT=true \
  --build-arg TENSORRT_MODEL=da3-small
```

## Implementation Details

### Key Optimizations Implemented

1. **Model Input Resolution: Platform-Aware**
   - Orin Nano/NX 8GB: 308x308 (optimal for memory constraints)
   - Orin NX 16GB / AGX Orin: 518x518 (higher quality)
   - Reduces inference time significantly vs larger resolutions

2. **TensorRT FP16 Quantization (Recommended)**
   - 2-3x faster inference vs PyTorch
   - Excellent accuracy (no calibration required)
   - Alternative: TensorRT INT8 (3-4x speedup, requires calibration dataset)

3. **GPU-Accelerated Upsampling**
   - Upsamples 384x384 depth → 1080p on GPU
   - Bilinear mode: ~4ms (fast, smooth)
   - Bicubic mode: ~6ms (higher quality)
   - All operations stay on GPU (no CPU bottleneck)

4. **Async Colorization**
   - Colorization runs in background thread
   - Off critical path (doesn't block depth processing)
   - Saves ~15-20ms per frame

5. **Subscriber Checks**
   - Only colorizes if someone is subscribed to colored topic
   - Saves processing when visualization not needed

6. **DA3-SMALL Model**
   - Faster than DA3-BASE (~1.25x speedup)
   - Good accuracy for most use cases
   - Can switch to DA3-BASE if quality is critical

### Performance Breakdown (Expected on Jetson Orin AGX)

**TensorRT FP16 Pipeline (>30 FPS):**
```
1080p camera capture          ~5ms
GPU resize (1080p→518x518)    ~3ms
TensorRT FP16 inference       ~20ms
GPU upsample (518→1080p)      ~4ms
Publishing depth+confidence   ~2ms
────────────────────────────────────
Total:                        ~34ms = 29.4 FPS
```

**With optimizations:**
- Async colorization: +0ms (off critical path)
- Subscriber checks: Skip work when not needed
- Expected real-world: **32-36 FPS**

**PyTorch FP16 Pipeline (~25 FPS):**
```
1080p camera capture          ~5ms
GPU resize (1080p→384x384)    ~3ms
PyTorch FP16 inference        ~30ms
GPU upsample (384→1080p)      ~4ms
Publishing depth+confidence   ~2ms
────────────────────────────────────
Total:                        ~44ms = 22.7 FPS
```

With optimizations: **24-28 FPS**

## Step-by-Step Setup

### 1. Install Dependencies

```bash
# Install torch2trt for TensorRT conversion
pip3 install torch2trt

# Verify CUDA and TensorRT are available
python3 -c "import torch; print('CUDA:', torch.cuda.is_available())"
python3 -c "import torch2trt; print('torch2trt available')"
```

### 2. Build TensorRT Engine

```bash
# Create models directory
mkdir -p models/tensorrt models/onnx

# Auto-detect platform and build optimal engine (recommended)
python3 scripts/build_tensorrt_engine.py --auto

# Or build with specific settings:
# For Orin Nano/NX 8GB (use 308x308)
python3 scripts/build_tensorrt_engine.py \
  --model da3-small \
  --precision fp16 \
  --resolution 308

# For AGX Orin (use 518x518)
python3 scripts/build_tensorrt_engine.py \
  --model da3-small \
  --precision fp16 \
  --resolution 518

# List available models
python3 scripts/build_tensorrt_engine.py --list-models
```

Expected output:
```
Detected Platform: Jetson AGX Orin

Recommended settings for AGX_ORIN_64GB:
  Precision: fp16
  Resolution: 518x518
  Workspace: 8192 MB

Downloading ONNX model: Depth Anything 3 Small
Building TensorRT engine...
Engine built successfully: models/tensorrt/da3-small_fp16_518x518_AGX_ORIN_64GB.engine
```

### 3. Configure Your Camera

For Anker PowerConf C200 webcam:

```bash
# Check available formats
v4l2-ctl --list-formats-ext -d /dev/video0

# Launch camera at 1080p with MJPEG encoding
ros2 run v4l2_camera v4l2_camera_node --ros-args \
  -p video_device:="/dev/video0" \
  -p image_size:="[1920,1080]" \
  -p pixel_format:="MJPEG" \
  -p camera_frame_id:="camera_optical_frame" \
  -r __ns:=/camera
```

### 4. Launch Optimized Node

```bash
# TensorRT FP16 (>30 FPS)
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw \
  backend:=tensorrt_native \
  trt_model_path:=/root/.cache/tensorrt/da3-small_fp16_518x518_AGX_ORIN_64GB.engine \
  output_height:=1080 \
  output_width:=1920 \
  log_inference_time:=true
```

### 5. Monitor Performance

Watch the console output for performance metrics (logged every 5 seconds):

```
[depth_anything_3_optimized]: Performance - FPS: 33.45, Inference: 18.2ms, Total: 29.9ms, Frames: 167
[depth_anything_3_optimized]: GPU Memory - Allocated: 2458.3MB, Reserved: 2560.0MB, Free: 61541.7MB
```

## Configuration Options

### Backend Selection

| Backend | Speed | Quality | Setup |
|---------|-------|---------|-------|
| `pytorch` | Baseline | Best | No conversion needed |
| `tensorrt_native` (FP16) | 2-3x faster | Excellent | One-time engine build |
| `tensorrt_native` (INT8) | 3-4x faster | Very Good | Requires calibration dataset |

### Model Selection

| Model | Speed | Quality | FPS (TRT FP16 @ 518) |
|-------|-------|---------|----------------------|
| DA3-SMALL | Fastest | Good | 30-35 FPS |
| DA3-BASE | Medium | Better | 25-30 FPS |
| DA3-LARGE | Slow | Best | 15-20 FPS |

### Input Resolution Trade-offs

| Resolution | Platform | Inference Time (TRT FP16) | Recommendation |
|------------|----------|---------------------------|----------------|
| 308x308 | Orin Nano 4GB/8GB | ~15ms | **Recommended for memory-constrained** |
| 308x308 | Orin NX 8GB | ~12ms | Good balance |
| 518x518 | Orin NX 16GB | ~25ms | **Recommended for 16GB+** |
| 518x518 | AGX Orin 32GB/64GB | ~20ms | **Recommended for AGX** |

### Upsampling Mode

| Mode | Speed | Quality | Use Case |
|------|-------|---------|----------|
| `bilinear` | Fastest (~4ms) | Good | **Recommended for >30 FPS** |
| `bicubic` | Medium (~6ms) | Better | Balance quality/speed |
| `nearest` | Fastest (~2ms) | Blocky | Not recommended |

## Troubleshooting

### Issue: FPS below 30

**Check 1: Verify backend**
```bash
# Should see "Backend: tensorrt_int8" in console output
# If seeing "Backend: pytorch", TensorRT model not loaded
```

**Check 2: Verify model input size**
```bash
# Should see "input_size=(384, 384)" in console
# If seeing 518x518, inference will be slower
```

**Check 3: Disable colorization temporarily**
```bash
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  ... \
  publish_colored:=false
```

**Check 4: Check GPU utilization**
```bash
# Run in another terminal
watch -n 1 nvidia-smi

# GPU utilization should be 80-95%
# If low, check for CPU bottlenecks
```

### Issue: TensorRT engine build fails

```bash
# Check TensorRT and pycuda installation
python3 -c "import tensorrt; print(f'TensorRT {tensorrt.__version__}')"
python3 -c "import pycuda.driver; print('pycuda OK')"

# Verify trtexec is available
which trtexec || ls /usr/src/tensorrt/bin/trtexec

# Verify TensorRT libraries
ls /usr/lib/aarch64-linux-gnu/libnvinfer*

# Try building with verbose output
python3 scripts/build_tensorrt_engine.py --auto --verbose
```

### Issue: Out of memory

```bash
# Use smaller model
model_name:=depth-anything/DA3-SMALL

# Or reduce output resolution
output_height:=720
output_width:=1280
```

## Advanced Optimization (Experimental)

### CUDA Streams

Enable pipeline parallelism (experimental):

```bash
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  ... \
  use_cuda_streams:=true
```

Expected: Additional 5-10% speedup

### Lower Camera Resolution

If 1080p output not required:

```bash
# Camera at 720p
v4l2_camera ... -p image_size:="[1280,720]"

# Output at 720p
output_height:=720
output_width:=1280
```

Expected: 40-45 FPS (720p output)

## Benchmark Results

### Measured Results (PyTorch - Current)

Tested on Jetson Orin NX 16GB (JetPack 6.0, L4T r36.2.0):

| Configuration | Model Input | Backend | FPS | Inference Time | Notes |
|--------------|-------------|---------|-----|----------------|-------|
| **Current Baseline** | 518x518 | PyTorch FP32 | ~5.2 | ~193ms | Functional |

### Validated Results (TensorRT 10.3)

Measured on Jetson Orin NX 16GB (L4T r36.4.0, TensorRT 10.3, 2026-01-31):

| Configuration | Model Input | Backend | FPS | GPU Latency | Quality |
|--------------|-------------|---------|-----|-------------|---------|
| Baseline | 518x518 | PyTorch FP32 | 5.2 | ~193ms | Excellent |
| TensorRT FP16 | 518x518 | TensorRT FP16 | 35.3 | 26.4ms median | Excellent |

**Key Technical Details:**
- Dockerfile base: `dustynv/ros:humble-pytorch-l4t-r36.4.0`
- TRT 10.x syntax: `--memPoolSize=workspace:2048MiB` (not deprecated `--workspace`)
- ONNX input shape: 5D `pixel_values:1x1x3x518x518`
- Engine size: 58MB

### Platform-Specific Performance Projections

Based on validated Orin NX 16GB results, projected performance for other platforms:

| Platform | Model | Resolution | Precision | Projected FPS |
|----------|-------|------------|-----------|---------------|
| Orin Nano 4GB | da3-small | 308 | FP16 | ~40-45 |
| Orin Nano 8GB | da3-small | 308 | FP16 | ~45-50 |
| Orin NX 8GB | da3-small | 308 | FP16 | ~50-55 |
| **Orin NX 16GB** | **da3-small** | **518** | **FP16** | **35.3 (validated)** |
| AGX Orin 32GB | da3-small | 518 | FP16 | ~45-55 |
| AGX Orin 64GB | da3-small | 518 | FP16 | ~50-60 |

**Notes:**
- Projections based on proportional compute capacity. Only Orin NX 16GB has validated measurements.
- Real-world FPS limited by camera input (~24 FPS for USB). See [Quick Reference](#quick-reference-by-platform) for recommended configurations.
- For DA3-Base/Large projections, expect ~50% and ~25% of DA3-Small FPS respectively.

## Quality Comparison

**FP16 vs INT8 Quantization:**
- FP16: No accuracy loss, recommended default
- INT8: ~3-5% accuracy reduction, requires calibration dataset
- Recommendation: Use FP16 unless maximum speed is critical and you have calibration data

**308x308 vs 518x518 Input:**
- When upsampled to 1080p, both produce good results
- 518x518 better for fine details and edges
- 308x308 recommended for memory-constrained devices (Orin Nano)

## Summary

To achieve >30 FPS with 1080p depth + confidence on Jetson:

**Quick Start (Docker):**
```bash
# Build Jetson image
docker compose build depth-anything-3-jetson

# Run with auto TensorRT engine building
DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson
```

**Manual Setup:**
1. Run `python3 scripts/build_tensorrt_engine.py --auto` (auto-detects platform)
2. Launch with `backend:=tensorrt_native`
3. Configure camera for 1080p MJPEG

**Platform-specific settings are automatically selected:**
- Orin Nano/NX 8GB: 308x308 FP16
- Orin NX 16GB / AGX Orin: 518x518 FP16

Expected performance: **30-50 FPS** depending on platform.

For questions or issues, please open a GitHub issue.
