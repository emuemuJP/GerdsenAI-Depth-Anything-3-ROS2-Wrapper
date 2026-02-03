# Performance Baselines

This document records measured performance baselines for the Depth Anything 3 ROS2 Wrapper.

---

## Jetson Orin NX 16GB - Validated Results

**Test Date**: 2026-02-02
**JetPack**: 6.2 (L4T r36.4)
**TensorRT**: 10.3.0.30
**CUDA**: 12.6

### TensorRT FP16 Performance

#### Resolution Benchmarks (DA3-Small)

| Resolution | Throughput | Latency (mean) | Latency (p99) | Speedup vs PyTorch |
|------------|------------|----------------|---------------|-------------------|
| 518x518 | **40.1 FPS** | 25.0ms | 25.6ms | 7.7x |
| 400x400 | **63.6 FPS** | 15.8ms | 16.4ms | 12.2x |
| 308x308 | **92.6 FPS** | 10.9ms | 11.1ms | 17.8x |
| 256x256 | **110.2 FPS** | 9.1ms | 9.3ms | 21.2x |

#### Model Size Benchmarks (518x518)

| Model | Parameters | Throughput | Latency (mean) | Engine Size |
|-------|------------|------------|----------------|-------------|
| DA3-Small | ~24M | **40.0 FPS** | 25.0ms | 64MB |
| DA3-Base | ~97M | **19.2 FPS** | 51.4ms | 211MB |
| DA3-Large | ~335M | **7.5 FPS** | 132.2ms | 674MB |

#### Thermal Stability (10-Minute Sustained Load)

| Metric | Value |
|--------|-------|
| Duration | 600.06 seconds |
| Status | **PASSED** |
| Throughput | 40.79 FPS (stable) |
| Latency (mean) | 24.73ms |
| Latency (min) | 24.25ms |
| Latency (max) | 27.88ms |
| Latency (p99) | 25.19ms |
| Thermal Throttling | None detected |

### PyTorch Baseline (Pre-TensorRT)

| Model | Backend | Resolution | FPS | Inference Time |
|-------|---------|------------|-----|----------------|
| DA3-Small | PyTorch FP32 | 518x518 | ~5.2 | ~193ms |

---

## Test Conditions

- **Power Mode**: MAXN (15W)
- **Cooling**: Active fan cooling
- **Benchmark Tool**: trtexec (TensorRT benchmark utility)
- **Iterations**: 100 inference passes
- **Warmup**: 2000ms

---

## Key Technical Details

- **Architecture**: Host-Container Split (TRT on host, ROS2 in container)
- **Base Image**: dustynv/ros:humble-ros-base-l4t-r36.2.0
- **Build Command**: `--memPoolSize=workspace:2048MiB` (TRT 10.x syntax)
- **ONNX Input Shape**: 5D `pixel_values:1x1x3xHxW`

---

## Recommendations

| Use Case | Configuration | FPS | Latency |
|----------|---------------|-----|---------|
| Real-time robotics | DA3-Small @ 308x308 | 93 | 11ms |
| Balanced | DA3-Small @ 400x400 | 64 | 16ms |
| High quality | DA3-Small @ 518x518 | 40 | 25ms |
| Quality-focused | DA3-Base @ 518x518 | 19 | 51ms |
| Offline processing | DA3-Large @ 518x518 | 7.5 | 132ms |

---

**Last Updated**: 2026-02-02
