# Performance Baselines

This document records measured performance baselines for future reference and comparison.

---

## Jetson Orin NX 16GB

**Test Date**: 2026-01-30
**JetPack**: 6.0 (L4T r36.2.0)
**CUDA**: 12.2
**PyTorch**: 2.3.0
**torchvision**: 0.18.0 (built from source)
**TensorRT**: 8.6.2 (not currently usable - opset incompatibility)

### DA3-SMALL (PyTorch FP32)

| Metric | Value |
|--------|-------|
| Input Resolution | 518x518 |
| Inference Time | ~193ms |
| FPS | ~5.2 |
| GPU Memory | ~2GB (estimated) |
| Backend | PyTorch FP32 |

### Test Conditions

- **Image Source**: Static test images
- **Warm-up**: 10 frames discarded before measurement
- **Measurement**: Average over 100 frames
- **Power Mode**: MAXN (15W)
- **Cooling**: Stock heatsink with fan

### Docker Build Statistics

| Metric | Value |
|--------|-------|
| Base Image | dustynv/ros:humble-ros-base-l4t-r36.2.0 |
| Final Image Size | ~14.9GB |
| Build Time | ~45 minutes |

---

## TensorRT Status

### Solution Implemented

| Aspect | Details |
|--------|---------|
| **Previous Issue** | TensorRT 8.6.2 incompatible with DINOv2 Einsum ops |
| **Solution** | Docker image updated to L4T r36.4.0 (TensorRT 10.3) |
| **Status** | Ready for testing - rebuild Docker image |
| **Expected FPS** | 20-30 FPS with TensorRT FP16 |

### torchvision Build Requirement

| Aspect | Details |
|--------|---------|
| **Issue** | NVIDIA PyTorch wheel ABI mismatch |
| **Impact** | pip-installed torchvision crashes on NMS operator |
| **Solution** | Build torchvision from source |
| **Build Time** | ~15 minutes additional |

### ARM64 Runtime Patches

| Package | Issue | Workaround |
|---------|-------|------------|
| pycolmap | No ARM64 wheel | Runtime patch in api.py |
| evo | No ARM64 wheel | Runtime patch in api.py |

---

## Desktop GPU (Reference)

*To be measured on desktop GPU for comparison*

### Expected Test Configuration

| Component | Specification |
|-----------|---------------|
| GPU | NVIDIA RTX 3090 / 4090 |
| CUDA | 12.x |
| PyTorch | 2.x |
| TensorRT | 10.x (opset 18+ support) |

### Expected Performance Targets

| Model | Backend | Expected FPS |
|-------|---------|--------------|
| DA3-SMALL | PyTorch FP32 | ~30-40 |
| DA3-SMALL | TensorRT FP16 | ~60-80 |
| DA3-BASE | PyTorch FP32 | ~20-25 |
| DA3-BASE | TensorRT FP16 | ~40-50 |

---

## Comparison Targets

### TensorRT Performance (When Available)

Based on typical TensorRT speedups (2-4x over PyTorch), expected performance on Jetson Orin NX 16GB:

| Model | Resolution | Backend | Expected FPS |
|-------|------------|---------|--------------|
| DA3-SMALL | 518x518 | TensorRT FP16 | ~15-20 |
| DA3-SMALL | 308x308 | TensorRT FP16 | ~30-40 |
| DA3-BASE | 518x518 | TensorRT FP16 | ~10-15 |

**Note**: These are projected values. Actual performance depends on opset compatibility resolution.

---

## Measurement Methodology

### Standard Test Procedure

1. **Start Container**
   ```bash
   docker compose up -d depth-anything-3-jetson
   docker exec -it da3_jetson bash
   ```

2. **Run Node with Logging**
   ```bash
   ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
     image_topic:=/camera/image_raw \
     model_name:=depth-anything/DA3-SMALL \
     log_inference_time:=true
   ```

3. **Measure Topic Rate**
   ```bash
   ros2 topic hz /depth_anything_3/depth
   ```

4. **Monitor System**
   ```bash
   # GPU utilization
   watch -n 1 nvidia-smi

   # Thermal (Jetson)
   tegrastats --interval 1000
   ```

### Reporting Format

When adding new baselines, include:
- Test date
- Hardware specification
- Software versions (JetPack, CUDA, PyTorch)
- Model and resolution
- Inference time and FPS
- Test conditions (power mode, cooling, etc.)

---

**Last Updated**: 2026-01-30
