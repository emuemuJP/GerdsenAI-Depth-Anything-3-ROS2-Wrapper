# Depth Anything 3 ROS2 Wrapper

Camera-agnostic ROS2 wrapper for [Depth Anything 3](https://github.com/ByteDance-Seed/Depth-Anything-3) monocular depth estimation.

<img width="1720" alt="Demo" src="https://github.com/user-attachments/assets/4d2c1cdf-0d8c-448c-a3f9-8e3557e37d81" />

## Performance (2026-02-05)

| Platform | Backend | Model | Resolution | FPS |
|----------|---------|-------|------------|-----|
| Orin AGX 64GB | PyTorch FP32 | DA3-Small | 518x518 | ~5 |
| **Orin NX 16GB** | **TensorRT FP16** | **DA3-Small** | **518x518** | **23+ / 43+** |

*23+ FPS real-world (camera-limited), 43+ FPS processing capacity*

> **Jetson Users**: Install `pycuda` on your Jetson host. TensorRT runs on the host, not in Docker.

---

## Key Features

- **TensorRT-Optimized**: 40+ FPS on Jetson via TensorRT 10.3
- **Camera-Agnostic**: Works with any camera publishing ROS2 image topics
- **One-Click Demo**: `./run.sh` handles everything automatically
- **Shared Memory IPC**: Low-latency host-container communication (~8ms)
- **Multiple Models**: DA3-Small, Base, Large with auto hardware detection
- **Docker Support**: Pre-configured for Jetson deployment

---

## Quick Start

### Option 1: Jetson TensorRT Demo (Recommended)

```bash
git clone https://github.com/GerdsenAI/Depth-Anything-3-ROS2-Wrapper.git ~/depth_anything_3_ros2
cd ~/depth_anything_3_ros2
./run.sh
```

First run takes ~15-20 minutes (Docker build + TensorRT engine). Subsequent runs start in ~10 seconds.

**Options:**
```bash
./run.sh --camera /dev/video0   # Specify camera
./run.sh --no-display           # Headless mode (SSH)
./run.sh --rebuild              # Force rebuild Docker
```

### Option 2: Native ROS2 Installation

```bash
# Clone and install
git clone https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper.git
cd GerdsenAI-Depth-Anything-3-ROS2-Wrapper
bash scripts/install_dependencies.sh
source install/setup.bash

# Run with USB camera
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw
```

See [Installation Guide](docs/INSTALLATION.md) for detailed steps.

### Option 3: Docker (Desktop GPU)

```bash
docker-compose up -d depth-anything-3-gpu
docker exec -it da3_ros2_gpu bash
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py image_topic:=/camera/image_raw
```

See [Docker Guide](docker/README.md) for more options.

---

## Architecture

This project uses a **host-container split** for optimal Jetson performance:

```
HOST (JetPack 6.x)
+--------------------------------------------------+
|  TRT Inference Service (trt_inference_shm.py)    |
|  - TensorRT 10.3, ~15ms inference                |
+--------------------------------------------------+
                    ^
                    | /dev/shm/da3 (shared memory)
                    v
+--------------------------------------------------+
|  Docker Container (ROS2 Humble)                  |
|  - Camera drivers, depth publisher               |
|  - SharedMemoryInferenceFast (~8ms IPC)          |
+--------------------------------------------------+
```

**Why**: Container TensorRT bindings are broken in current Jetson images. Host TensorRT 10.3 works perfectly.

---

## Platform Recommendations

| Platform | Model | Resolution | Expected FPS | Memory |
|----------|-------|------------|--------------|--------|
| Orin Nano 4GB/8GB | DA3-Small | 308x308 | 40-50 | ~1.2GB |
| Orin NX 8GB | DA3-Small | 308x308 | 50-55 | ~1.2GB |
| **Orin NX 16GB** | DA3-Small | 518x518 | **43+ (validated)** | ~1.8GB |
| AGX Orin 32GB/64GB | DA3-Base | 518x518 | 25-35 | ~2.5GB |

See [Optimization Guide](OPTIMIZATION_GUIDE.md) for detailed benchmarks and tuning.

---

## Topics

### Subscribed
| Topic | Type | Description |
|-------|------|-------------|
| `~/image_raw` | sensor_msgs/Image | Input RGB image |

### Published
| Topic | Type | Description |
|-------|------|-------------|
| `~/depth` | sensor_msgs/Image | Depth map (32FC1) |
| `~/depth_colored` | sensor_msgs/Image | Colorized visualization (BGR8) |
| `~/confidence` | sensor_msgs/Image | Confidence map (32FC1) |

---

## Common Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_name` | `depth-anything/DA3-BASE` | Model to use |
| `device` | `cuda` | `cuda` or `cpu` |
| `inference_height` | `518` | Input resolution height |
| `inference_width` | `518` | Input resolution width |
| `publish_colored` | `true` | Publish colorized depth |

See [Configuration Reference](docs/CONFIGURATION.md) for all parameters.

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Installation](docs/INSTALLATION.md) | Detailed installation steps, offline setup |
| [Usage Examples](docs/USAGE_EXAMPLES.md) | USB camera, ZED, RealSense, multi-camera |
| [Configuration](docs/CONFIGURATION.md) | All parameters, topics, models |
| [ROS2 Node Reference](docs/ROS2_NODE_REFERENCE.md) | Node lifecycle, QoS, Jetson performance tuning |
| [Optimization](OPTIMIZATION_GUIDE.md) | Platform benchmarks, performance tuning |
| [Jetson Deployment](docs/JETSON_DEPLOYMENT_GUIDE.md) | TensorRT setup, host-container split |
| [Docker](docker/README.md) | Container deployment options |
| [Troubleshooting](TROUBLESHOOTING.md) | Common issues and solutions |

---

## Requirements

- **ROS2**: Humble Hawksbill (Ubuntu 22.04)
- **Python**: 3.10+
- **TensorRT**: 10.3+ (Jetson JetPack 6.x) for production
- **CUDA**: 12.x (optional for desktop GPU)

---

## Acknowledgments

- **[Depth Anything 3](https://github.com/ByteDance-Seed/Depth-Anything-3)** - ByteDance Seed Team ([paper](https://arxiv.org/abs/2511.10647))
- **[NVIDIA TensorRT](https://developer.nvidia.com/tensorrt)** - High-performance inference
- **[Jetson Containers](https://github.com/dusty-nv/jetson-containers)** - dusty-nv's L4T Docker images
- **[Hugging Face](https://huggingface.co/depth-anything)** - Model hosting

Inspired by [grupo-avispa/depth_anything_v2_ros2](https://github.com/grupo-avispa/depth_anything_v2_ros2) and [scepter914/DepthAnything-ROS](https://github.com/scepter914/DepthAnything-ROS).

---

## Citation

```bibtex
@article{depthanything3,
  title={Depth Anything 3: A New Foundation for Metric and Relative Depth Estimation},
  author={Yang, Lihe and Kang, Bingyi and Huang, Zilong and Zhao, Zhen and Xu, Xiaogang and Feng, Jiashi and Zhao, Hengshuang},
  journal={arXiv preprint arXiv:2511.10647},
  year={2024}
}
```

---

## License

**This ROS2 wrapper**: MIT License

**Depth Anything 3 models**:
- DA3-Small: Apache-2.0 (commercial use OK)
- DA3-Base/Large/Giant: CC-BY-NC-4.0 (non-commercial only)

---

## Contributing

Contributions welcome! We especially need help with **test coverage** for the SharedMemory/TensorRT production code paths. See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Current test coverage status
- Priority areas needing tests
- How to write and run tests

---

## Support

- [GitHub Issues](https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper/issues)
- [GitHub Discussions](https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper/discussions)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
