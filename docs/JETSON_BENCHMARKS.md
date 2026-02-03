# Depth Anything 3 - Jetson Orin NX Benchmarks

Performance benchmarks for Depth Anything 3 (DA3) models running on NVIDIA Jetson Orin NX 16GB with TensorRT 10.3 optimization.

**Test Date:** February 2, 2026
**Hardware:** Jetson Orin NX 16GB (JetPack 6.2)
**TensorRT Version:** 10.3
**Precision:** FP16

---

## Executive Summary

| Configuration | FPS | Latency | Use Case |
|--------------|-----|---------|----------|
| DA3-Small @ 256x256 | **110 FPS** | 9.1ms | High-speed robotics |
| DA3-Small @ 308x308 | **93 FPS** | 10.9ms | Real-time robotics (recommended) |
| DA3-Small @ 400x400 | **64 FPS** | 15.8ms | Balanced quality/speed |
| DA3-Small @ 518x518 | **40 FPS** | 25.0ms | Higher quality |
| DA3-Base @ 518x518 | **19 FPS** | 51.4ms | Quality-focused |
| DA3-Large @ 518x518 | **7.5 FPS** | 132ms | Offline processing |

**Recommendation:** For real-time robotics applications, use DA3-Small at 308x308 or 400x400 resolution for optimal speed/quality balance.

---

## Resolution Benchmarks (DA3-Small)

Testing DA3-Small model at different input resolutions to find the optimal speed/quality tradeoff.

| Resolution | Throughput (FPS) | Latency (mean) | Latency (p99) | Engine Size |
|------------|------------------|----------------|---------------|-------------|
| 518x518 | 40.09 | 25.0ms | 25.6ms | 64MB |
| 400x400 | 63.58 | 15.8ms | 16.4ms | 60MB |
| 308x308 | 92.58 | 10.9ms | 11.1ms | 60MB |
| 256x256 | 110.20 | 9.1ms | 9.3ms | 56MB |

### Resolution Scaling Analysis

- **2x speedup:** Reducing from 518 to 400 yields 1.6x faster inference
- **2.3x speedup:** 308x308 provides 2.3x improvement over native resolution
- **2.7x speedup:** 256x256 achieves maximum throughput at 110 FPS

### Quality Considerations

Lower resolutions reduce depth map detail but maintain relative depth accuracy. For navigation and obstacle avoidance, 308x308 provides sufficient spatial resolution while enabling real-time performance.

---

## Model Size Benchmarks (518x518)

Comparing DA3 model variants at native 518x518 resolution.

| Model | Parameters | Throughput (FPS) | Latency (mean) | Latency (p99) | Engine Size |
|-------|------------|------------------|----------------|---------------|-------------|
| DA3-Small | ~24M | 40.05 | 25.0ms | 25.6ms | 64MB |
| DA3-Base | ~97M | 19.24 | 51.4ms | 52.8ms | 211MB |
| DA3-Large | ~335M | 7.51 | 132.2ms | 134.2ms | 674MB |

### Model Scaling Analysis

- **Small to Base:** 4x more parameters, 2x slower (19 vs 40 FPS)
- **Base to Large:** 3.5x more parameters, 2.6x slower (7.5 vs 19 FPS)
- **Small to Large:** 14x more parameters, 5.3x slower (7.5 vs 40 FPS)

### Quality vs Speed Tradeoff

| Model | Relative Quality | Relative Speed | Best For |
|-------|-----------------|----------------|----------|
| Small | Good | Fastest | Real-time robotics, embedded |
| Base | Better | Moderate | Quality-sensitive applications |
| Large | Best | Slowest | Offline processing, benchmarking |

---

## Memory Usage

### GPU Memory (Estimated)

| Model | Resolution | GPU Memory |
|-------|------------|------------|
| DA3-Small | 518x518 | ~1.2GB |
| DA3-Small | 308x308 | ~0.8GB |
| DA3-Base | 518x518 | ~2.5GB |
| DA3-Large | 518x518 | ~6GB |

### Disk Space (TRT Engines)

| Configuration | Engine Size |
|---------------|-------------|
| DA3-Small (all resolutions) | ~240MB total |
| DA3-Base (518x518) | 211MB |
| DA3-Large (518x518) | 674MB |

---

## Deployment Recommendations

### Real-Time Robotics (30+ FPS required)

**Recommended:** DA3-Small @ 308x308 or 400x400
- 308x308: 93 FPS with 11ms latency
- 400x400: 64 FPS with 16ms latency
- Both leave headroom for other processing

### Quality-Focused Applications (15+ FPS acceptable)

**Recommended:** DA3-Small @ 518x518 or DA3-Base @ 518x518
- Small: 40 FPS, good quality
- Base: 19 FPS, better quality for detailed scenes

### Offline/Batch Processing

**Recommended:** DA3-Large @ 518x518
- 7.5 FPS suitable for non-real-time applications
- Best depth quality for dataset generation

---

## Test Methodology

### Hardware Configuration

- **Device:** NVIDIA Jetson Orin NX 16GB
- **JetPack:** 6.2
- **Power Mode:** MAXN (15W)
- **Cooling:** Active fan cooling

### Benchmark Parameters

- **Tool:** trtexec (TensorRT benchmark utility)
- **Iterations:** 100 inference passes
- **Warmup:** 2000ms
- **Precision:** FP16

### Engine Build Settings

```bash
trtexec \
    --onnx=model.onnx \
    --saveEngine=model.engine \
    --fp16 \
    --memPoolSize=workspace:2048MiB \
    --optShapes=pixel_values:1x1x3xHxW
```

---

## Reproducing Benchmarks

### Prerequisites

1. Jetson Orin NX with JetPack 6.2+
2. TensorRT 10.3
3. This repository deployed via `deploy_jetson.sh`

### Running Resolution Benchmarks

```bash
cd ~/depth_anything_3_ros2
bash scripts/benchmark_resolutions.sh
```

### Running Model Size Benchmarks

```bash
cd ~/depth_anything_3_ros2
bash scripts/benchmark_models.sh
```

---

## Version History

| Date | Changes |
|------|---------|
| 2026-02-02 | Initial benchmarks on Jetson Orin NX 16GB |
| 2026-02-02 | Added thermal/stability validation (10-min sustained load test) |

---

## Thermal/Stability Validation

### 10-Minute Sustained Load Test

Test performed with DA3-Small @ 518x518 under continuous inference load.

| Metric | Value |
|--------|-------|
| Duration | 600.06 seconds |
| Status | **PASSED** |
| Throughput | 40.79 FPS |
| Latency (mean) | 24.73ms |
| Latency (min) | 24.25ms |
| Latency (max) | 27.88ms |
| Latency (p99) | 25.19ms |

### Stability Analysis

- **FPS Stability:** Maintained consistent 40.79 FPS throughout 10-minute test
- **Latency Variance:** Only 3.63ms spread (min to max) indicating stable thermals
- **Thermal Throttling:** None detected (performance remained constant)
- **p99 Latency:** 25.19ms ensures predictable real-time behavior

### Conclusions

The Jetson Orin NX 16GB demonstrates excellent thermal stability for sustained DA3 inference workloads. No performance degradation was observed over the 10-minute test period, making it suitable for continuous robotics applications.

---

## References

- [Depth Anything V3 Paper](https://arxiv.org/abs/2401.10891)
- [ONNX Community Models](https://huggingface.co/onnx-community)
- [TensorRT Documentation](https://docs.nvidia.com/deeplearning/tensorrt/)
- [Jetson Orin NX Specs](https://developer.nvidia.com/embedded/jetson-orin-nx)
