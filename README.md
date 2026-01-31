# WORK IN PROGRESS LOOKING FOR CONTRIBUTERS

# Depth Anything 3 ROS2 Wrapper

<img width="3440" height="1440" alt="image" src="https://github.com/user-attachments/assets/4d2c1cdf-0d8c-448c-a3f9-8e3557e37d81" />


## Acknowledgments and Credits

This package would not be possible without the excellent work of the following projects and teams:

### Depth Anything 3
- **Team**: ByteDance Seed Team
- **Repository**: [ByteDance-Seed/Depth-Anything-3](https://github.com/ByteDance-Seed/Depth-Anything-3)
- **Paper**: [Depth Anything 3: A New Foundation for Metric and Relative Depth Estimation](https://arxiv.org/abs/2511.10647)
- **Project Page**: https://depth-anything-3.github.io/

This wrapper integrates the state-of-the-art Depth Anything 3 model for monocular depth estimation. All credit for the model architecture and training goes to the original authors.

### Inspiration from Prior ROS2 Wrappers
This package was inspired by the following excellent ROS2 wrapper implementations:

- **Depth Anything V2 ROS2**: [grupo-avispa/depth_anything_v2_ros2](https://github.com/grupo-avispa/depth_anything_v2_ros2)
- **Depth Anything ROS2**: [polatztrk/depth_anything_ros](https://github.com/polatztrk/depth_anything_ros)
- **TensorRT Optimized Wrapper**: [scepter914/DepthAnything-ROS](https://github.com/scepter914/DepthAnything-ROS)

Special thanks to these developers for demonstrating effective patterns for ROS2 integration.

---

## Overview

This aims to be a camera-agnostic ROS2 wrapper for Depth Anything 3 (DA3), providing real-time monocular depth estimation from standard RGB images. This package is designed to work seamlessly with any camera publishing standard `sensor_msgs/Image` messages.

### Key Features

- **Camera-Agnostic Design**: Works with ANY camera publishing standard ROS2 image topics
- **Multiple Model Support**: All DA3 variants (Small, Base, Large, Giant, Nested)
- **CUDA Acceleration**: Optimized for NVIDIA GPUs with automatic CPU fallback
- **Multi-Camera Support**: Run multiple instances for multi-camera setups
- **Real-Time Performance**: Optimized for low latency on Jetson Orin AGX
- **Production Ready**: Comprehensive error handling, logging, and testing
- **Docker Support**: Pre-configured Docker and Docker Compose files
- **Example Images**: Sample test images and benchmark scripts included
- **Performance Profiling**: Built-in benchmarking and profiling tools
- **TensorRT Support**: Optimization scripts for NVIDIA Jetson platforms (requires Docker image rebuild - see [TensorRT Status](#tensorrt-status))
- **Post-Processing**: Depth map filtering, hole filling, and enhancement
- **INT8 Quantization**: Model compression for faster inference
- **ONNX Export**: Deploy to various platforms and runtimes
- **Complete Documentation**: Sphinx-based API docs with comprehensive tutorials
- **CI/CD Ready**: GitHub Actions workflow for automated testing and validation
- **Docker Testing**: Automated Docker image validation suite
- **RViz2 Visualization**: Pre-configured visualization setup

### Supported Platforms

- **Primary**: NVIDIA Jetson (JetPack 6.x)
- **Compatible**: Any system with Ubuntu 22.04, ROS2 Humble, and CUDA 12.x
- **ROS2 Distribution**: Humble Hawksbill
- **Python**: 3.10+

---

## Important: Dependencies and Model Downloads

**You do NOT need to manually clone the ByteDance Depth Anything 3 repository.** The installation process handles everything automatically.

### What Gets Installed

**1. Python Package** (installed via pip in Step 2):
- ByteDance DA3 Python API and inference code
- Installed with: `pip install git+https://github.com/ByteDance-Seed/Depth-Anything-3.git`
- Pip handles cloning and installation automatically
- One-time setup, no manual git clone needed

**2. Pre-Trained Models** (downloaded automatically on first run):
- Model weights download from [Hugging Face Hub](https://huggingface.co/depth-anything) on first use
- Cached in `~/.cache/huggingface/hub/` for reuse
- **Internet connection required** for initial download
- Subsequent runs use cached models (no internet needed)

**Summary**: Install the package once with pip (Step 2), then models download automatically when you first run the node.

### Offline Operation (Robots Without Internet)

For robots or systems without internet access, pre-download models on a connected machine:

```bash
# On a machine WITH internet connection:
python3 -c "
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
# Download model (only needs to be done once)
AutoImageProcessor.from_pretrained('depth-anything/DA3-BASE')
AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')
print('Model downloaded to ~/.cache/huggingface/hub/')
"

# Copy the cache directory to your offline robot:
# On source machine:
tar -czf da3_models.tar.gz -C ~/.cache/huggingface .

# On target robot (via USB drive, SCP, etc.):
mkdir -p ~/.cache/huggingface
tar -xzf da3_models.tar.gz -C ~/.cache/huggingface/
```

Alternatively, set a custom cache directory:

```bash
# Download to specific location
export HF_HOME=/path/to/models
python3 -c "from transformers import AutoModelForDepthEstimation; \
            AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')"

# On robot, point to the same location
export HF_HOME=/path/to/models
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py
```

**Available Models:**
- `depth-anything/DA3-SMALL` - Fastest, ~1.5GB download
- `depth-anything/DA3-BASE` - Balanced, ~2.5GB download
- `depth-anything/DA3-LARGE` - Best quality, ~4GB download
- `depth-anything/DA3-GIANT` - Maximum quality, ~6.5GB download

---

## Table of Contents

- [Important: Dependencies and Model Downloads](#important-dependencies-and-model-downloads)
  - [What Gets Installed](#what-gets-installed)
  - [Offline Operation](#offline-operation-robots-without-internet)
- [Installation](#installation)
  - [Native Installation](#installation)
  - [Docker Installation](#docker-deployment)
- [Hardware Detection and Model Setup](#hardware-detection-and-model-setup)
  - [Interactive Setup Script](#interactive-setup-script)
  - [Platform Recommendations](#platform-recommendations)
  - [Model Licensing](#model-licensing)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Docker Deployment](#docker-deployment)
  - [Docker Environment Variables](#docker-environment-variables)
- [Example Images and Benchmarks](#example-images-and-benchmarks)
- [Performance](#performance)
- [Documentation](#documentation)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Citation](#citation)
- [License](#license)

---

## Installation

### Prerequisites

1. **ROS2 Humble** on Ubuntu 22.04:
```bash
# If not already installed
sudo apt update
sudo apt install ros-humble-desktop
```

2. **CUDA 12.x** (optional, for GPU acceleration):
```bash
# For Jetson Orin AGX, this comes with JetPack 6.x
# For desktop systems, install CUDA Toolkit from NVIDIA
nvidia-smi  # Verify CUDA installation
```

3. **Internet Connection** (for initial setup):
- Required for Step 2 (pip install of DA3 package)
- Required for Step 5 (model weights download from Hugging Face Hub)
- See [Offline Operation](#offline-operation-robots-without-internet) if deploying to robots without internet

### Step 1: Install ROS2 Dependencies

```bash
sudo apt install -y \
  ros-humble-cv-bridge \
  ros-humble-sensor-msgs \
  ros-humble-std-msgs \
  ros-humble-image-transport \
  ros-humble-rclpy
```

### Step 2: Install Python Dependencies

```bash
# Create and activate a virtual environment (recommended)
python3 -m venv ~/da3_venv
source ~/da3_venv/bin/activate

# Install PyTorch with CUDA support
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Install other dependencies
pip3 install transformers>=4.35.0 \
  huggingface-hub>=0.19.0 \
  opencv-python>=4.8.0 \
  pillow>=10.0.0 \
  numpy>=1.24.0 \
  timm>=0.9.0

# Install ByteDance DA3 Python API (pip handles cloning automatically)
# This provides the model inference code, NOT the pre-trained weights
# Model weights will download from Hugging Face Hub on first run
pip3 install git+https://github.com/ByteDance-Seed/Depth-Anything-3.git
```

**Note**: For CPU-only systems, install PyTorch without CUDA:
```bash
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### Step 3: Clone and Build This ROS2 Wrapper

```bash
# Navigate to your ROS2 workspace
cd ~/ros2_ws/src  # Or create: mkdir -p ~/ros2_ws/src && cd ~/ros2_ws/src

# Clone THIS ROS2 wrapper repository (not the ByteDance DA3 repo)
git clone https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper.git

# Build the package
cd ~/ros2_ws
colcon build --packages-select depth_anything_3_ros2

# Source the workspace
source install/setup.bash
```

### Step 4: Verify Installation

```bash
# Test that the package is found
ros2 pkg list | grep depth_anything_3_ros2

# Run tests (optional)
colcon test --packages-select depth_anything_3_ros2
colcon test-result --verbose
```

### Step 5: Model Setup (Recommended)

Use the interactive setup script to detect your hardware and download the optimal model:

```bash
# Interactive setup (recommended) - detects hardware and recommends models
python scripts/setup_models.py

# Show detected hardware information only
python scripts/setup_models.py --detect

# List all available models with compatibility info
python scripts/setup_models.py --list-models

# Non-interactive installation of a specific model
python scripts/setup_models.py --model DA3-SMALL --no-download

# Override detected VRAM (useful for shared GPU systems)
python scripts/setup_models.py --vram 8192
```

The setup script will:
1. Detect your hardware platform (Jetson module, GPU, RAM)
2. Show compatible models with recommendations
3. Download selected model(s) from Hugging Face
4. Generate an optimized configuration file

See [Hardware Detection and Model Setup](#hardware-detection-and-model-setup) for detailed platform recommendations.

**Manual Download (Alternative):**

If you prefer to download models manually without the setup script:

```bash
# Download a specific model (requires internet connection)
python3 -c "
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
print('Downloading DA3-BASE model...')
AutoImageProcessor.from_pretrained('depth-anything/DA3-BASE')
AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')
print('Model cached to ~/.cache/huggingface/hub/')
print('You can now run offline!')
"

# For offline robots, copy the cache:
# tar -czf da3_models.tar.gz -C ~/.cache/huggingface .
# Transfer da3_models.tar.gz to robot and extract:
# tar -xzf da3_models.tar.gz -C ~/.cache/huggingface/
```

See [Dependencies and Model Downloads](#important-dependencies-and-model-downloads) for complete offline deployment instructions.

---

## Hardware Detection and Model Setup

This package includes an interactive setup system that detects your hardware and recommends optimal model configurations.

### Interactive Setup Script

The `setup_models.py` script provides guided model selection based on your hardware:

```bash
cd ~/ros2_ws/src/GerdsenAI-Depth-Anything-3-ROS2-Wrapper

# Run interactive setup
python scripts/setup_models.py
```

Example output:
```
============================================================
     Depth Anything 3 - Model Setup
============================================================

Detected Hardware:
  Platform: Jetson Orin NX 16GB
  RAM: 16.0 GB
  GPU Memory: 16.0GB
  GPU: NVIDIA Tegra Orin (nvgpu)
  JetPack: 6.0
  L4T: 36.3.0
  CUDA Available: Yes

Available Models:
------------------------------------------------------------
  [*] DA3-SMALL           (30M, 1.0GB)
      License: Apache-2.0
      Status: Compatible
      Lightweight model for resource-constrained devices

  [*] DA3-BASE            (100M, 2.0GB)
      License: CC-BY-NC-4.0
      Status: RECOMMENDED for your hardware
      Balanced performance and accuracy
...
```

### CLI Options

| Option | Description |
|--------|-------------|
| `--detect` | Show hardware detection info only |
| `--list-models` | List all available models with compatibility |
| `--model MODEL` | Non-interactive install of specific model |
| `--vram MB` | Override detected VRAM (useful for shared GPU) |
| `--platform NAME` | Override detected platform |
| `--no-download` | Skip downloading models (config only) |
| `--no-config` | Skip generating config file |
| `--all` | Show all models including incompatible ones |

### Platform Recommendations

The following table shows recommended models for each Jetson platform:

| Platform | Recommended Model | Resolution | VRAM Usage |
|----------|-------------------|------------|------------|
| Orin Nano 4GB | DA3-SMALL | 308x308 | ~626MB |
| Orin Nano 8GB | DA3-SMALL | 308x308 | ~626MB |
| Orin NX 8GB | DA3-SMALL | 308x308 | ~626MB |
| Orin NX 16GB | DA3-BASE | 518x518 | ~1.8GB |
| AGX Orin 32GB | DA3-LARGE-1.1 | 518x518 | ~3.8GB |
| AGX Orin 64GB | DA3-LARGE-1.1 | 1024x1024 | ~4.5GB |
| Xavier NX | DA3-SMALL | 308x308 | ~626MB |
| x86 with GPU | DA3-BASE or larger | 518x518+ | Varies |
| CPU Only | DA3-SMALL | 308x308 | N/A |

**Note**: Resolution must be divisible by 14 (ViT patch size). Common presets:
- **Low**: 308x308 - Fastest, suitable for obstacle avoidance
- **Medium**: 518x518 - Balanced speed and detail
- **High**: 728x728 - More detail, slower inference
- **Ultra**: 1024x1024 - Maximum detail, requires high-end GPU

### Model Licensing

Depth Anything 3 models have different licenses that affect commercial use:

| Model | License | Commercial Use |
|-------|---------|----------------|
| DA3-SMALL | Apache-2.0 | Yes |
| DA3-BASE | CC-BY-NC-4.0 | No (contact ByteDance) |
| DA3-LARGE-1.1 | CC-BY-NC-4.0 | No (contact ByteDance) |
| DA3-GIANT-1.1 | CC-BY-NC-4.0 | No (contact ByteDance) |
| DA3METRIC-LARGE | CC-BY-NC-4.0 | No (contact ByteDance) |
| DA3MONO-LARGE | CC-BY-NC-4.0 | No (contact ByteDance) |

**Important**: Only `DA3-SMALL` is licensed for commercial use under Apache-2.0. All other models use CC-BY-NC-4.0 (non-commercial). For commercial applications with larger models, contact ByteDance for licensing.

---

## Quick Start

### Single Camera (Generic USB Camera)

The fastest way to get started is with a standard USB camera:

```bash
# Terminal 1: Launch USB camera driver
ros2 run v4l2_camera v4l2_camera_node --ros-args \
  -p image_size:="[640,480]" \
  -r __ns:=/camera

# Terminal 2: Launch Depth Anything 3
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw \
  model_name:=depth-anything/DA3-BASE \
  device:=cuda

# Terminal 3: Visualize with RViz2
rviz2 -d $(ros2 pkg prefix depth_anything_3_ros2)/share/depth_anything_3_ros2/rviz/depth_view.rviz
```

### Using Pre-Built Example Launch Files

```bash
# USB camera example (requires v4l2_camera)
ros2 launch depth_anything_3_ros2 usb_camera_example.launch.py

# Static image test (requires image_publisher)
ros2 launch depth_anything_3_ros2 image_publisher_test.launch.py \
  image_path:=/path/to/your/test_image.jpg
```

---

## Configuration

### Parameters

All parameters can be configured via launch files or command line:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | string | `depth-anything/DA3-BASE` | Hugging Face model ID or local path |
| `device` | string | `cuda` | Inference device (`cuda` or `cpu`) |
| `cache_dir` | string | `""` | Model cache directory (empty for default) |
| `inference_height` | int | `518` | Height for inference (model input) |
| `inference_width` | int | `518` | Width for inference (model input) |
| `input_encoding` | string | `bgr8` | Expected input encoding (`bgr8` or `rgb8`) |
| `normalize_depth` | bool | `true` | Normalize depth to [0, 1] range |
| `publish_colored` | bool | `true` | Publish colorized depth visualization |
| `publish_confidence` | bool | `true` | Publish confidence map |
| `colormap` | string | `turbo` | Colormap for visualization |
| `queue_size` | int | `1` | Subscriber queue size |
| `log_inference_time` | bool | `false` | Log performance metrics |

### Available Models

| Model | Parameters | Use Case |
|-------|------------|----------|
| `depth-anything/DA3-SMALL` | 0.08B | Fast inference, lower accuracy |
| `depth-anything/DA3-BASE` | 0.12B | Balanced performance (recommended) |
| `depth-anything/DA3-LARGE` | 0.35B | Higher accuracy |
| `depth-anything/DA3-GIANT` | 1.15B | Best accuracy, slower |
| `depth-anything/DA3NESTED-GIANT-LARGE` | Combined | Metric scale reconstruction |

### Topics

#### Subscribed Topics
- `~/image_raw` (sensor_msgs/Image): Input RGB image from camera
- `~/camera_info` (sensor_msgs/CameraInfo): Optional camera intrinsics

#### Published Topics
- `~/depth` (sensor_msgs/Image): Depth map (32FC1 encoding)
- `~/depth_colored` (sensor_msgs/Image): Colorized depth visualization (BGR8)
- `~/confidence` (sensor_msgs/Image): Confidence map (32FC1)
- `~/depth/camera_info` (sensor_msgs/CameraInfo): Camera info for depth image

---

## Usage Examples

### Example 1: Generic USB Camera (v4l2_camera)

Complete example with a standard USB webcam:

```bash
# Install v4l2_camera if not already installed
sudo apt install ros-humble-v4l2-camera

# Launch everything together
ros2 launch depth_anything_3_ros2 usb_camera_example.launch.py \
  video_device:=/dev/video0 \
  model_name:=depth-anything/DA3-BASE
```

### Example 2: ZED Stereo Camera

Connect to a ZED camera (requires separate ZED ROS2 wrapper installation):

```bash
# Launch ZED camera separately
ros2 launch zed_wrapper zed_camera.launch.py camera_model:=zedxm

# In another terminal, launch depth estimation with topic remapping
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/zed/zed_node/rgb/image_rect_color \
  camera_info_topic:=/zed/zed_node/rgb/camera_info
```

Or use the provided example:
```bash
ros2 launch depth_anything_3_ros2 zed_camera_example.launch.py \
  camera_model:=zedxm
```

### Example 3: Intel RealSense Camera

Connect to a RealSense camera (requires realsense-ros):

```bash
# Launch RealSense camera
ros2 launch realsense2_camera rs_launch.py

# Launch depth estimation
ros2 launch depth_anything_3_ros2 realsense_example.launch.py
```

### Example 4: Multi-Camera Setup

Run depth estimation on 4 cameras simultaneously:

```bash
# Launch multi-camera setup
ros2 launch depth_anything_3_ros2 multi_camera.launch.py \
  camera_namespaces:="cam1,cam2,cam3,cam4" \
  image_topics:="/cam1/image_raw,/cam2/image_raw,/cam3/image_raw,/cam4/image_raw" \
  model_name:=depth-anything/DA3-BASE
```

### Example 5: Testing with Static Images

Test with a static image using image_publisher:

```bash
sudo apt install ros-humble-image-publisher

ros2 launch depth_anything_3_ros2 image_publisher_test.launch.py \
  image_path:=/path/to/test_image.jpg \
  model_name:=depth-anything/DA3-BASE
```

### Example 6: Using Different Models

Switch between models for different performance/accuracy tradeoffs:

```bash
# Fast inference (DA3-Small)
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  model_name:=depth-anything/DA3-SMALL \
  image_topic:=/camera/image_raw

# Best accuracy (DA3-Giant) - requires more GPU memory
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  model_name:=depth-anything/DA3-GIANT \
  image_topic:=/camera/image_raw
```

### Example 7: CPU-Only Mode

Run on systems without CUDA:

```bash
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw \
  model_name:=depth-anything/DA3-BASE \
  device:=cpu
```

### Example 8: Custom Configuration

Use a custom parameter file:

```bash
# Create custom config file
cat > my_config.yaml <<EOF
depth_anything_3:
  ros__parameters:
    model_name: "depth-anything/DA3-LARGE"
    device: "cuda"
    normalize_depth: true
    publish_colored: true
    colormap: "viridis"
    log_inference_time: true
EOF

# Launch with custom config
ros2 run depth_anything_3_ros2 depth_anything_3_node --ros-args \
  --params-file my_config.yaml \
  -r ~/image_raw:=/camera/image_raw
```

---

## Docker Deployment

Docker configuration files are provided for building and deploying on both CPU and GPU systems.

> **Important**: No pre-built Docker images are published to Docker Hub or any container registry. You must build the images locally using `docker-compose build` or `docker-compose up` (which auto-builds).

### Complete Docker Installation (3 Steps)

```bash
# Step 1: Clone the repository
git clone https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper.git
cd GerdsenAI-Depth-Anything-3-ROS2-Wrapper

# Step 2: Build and run (choose GPU or CPU)
docker-compose up -d depth-anything-3-gpu    # For GPU (requires nvidia-docker)
# OR
docker-compose up -d depth-anything-3-cpu    # For CPU-only

# Step 3: Enter container and run the node
docker exec -it da3_ros2_gpu bash            # For GPU container
# OR
docker exec -it da3_ros2_cpu bash            # For CPU container

# Inside the container:
ros2 run depth_anything_3_ros2 depth_anything_3_node --ros-args -p device:=cuda
```

### Quick Start with Docker Compose

```bash
# CPU-only mode
docker-compose up -d depth-anything-3-cpu
docker exec -it da3_ros2_cpu bash

# GPU mode (requires nvidia-docker)
docker-compose up -d depth-anything-3-gpu
docker exec -it da3_ros2_gpu bash

# Development mode (source mounted)
docker-compose up -d depth-anything-3-dev
```

### Manual Docker Build

```bash
# Build GPU image
docker build -t depth_anything_3_ros2:gpu \
    --build-arg BUILD_TYPE=cuda-base \
    .

# Run with USB camera
docker run -it --rm \
    --runtime=nvidia \
    --gpus all \
    --network host \
    --privileged \
    -v /dev:/dev:rw \
    depth_anything_3_ros2:gpu
```

### Pre-configured Services

The docker-compose.yml includes:
- `depth-anything-3-cpu`: CPU-only deployment
- `depth-anything-3-gpu`: GPU-accelerated deployment
- `depth-anything-3-dev`: Development environment
- `depth-anything-3-usb-camera`: Standalone USB camera service

### Docker Environment Variables

Configure the container behavior using environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DA3_MODEL` | `depth-anything/DA3-BASE` | HuggingFace model ID to use |
| `DA3_INFERENCE_HEIGHT` | `518` | Inference height (must be divisible by 14) |
| `DA3_INFERENCE_WIDTH` | `518` | Inference width (must be divisible by 14) |
| `DA3_VRAM_LIMIT_MB` | (auto) | Override detected VRAM for model selection |
| `DA3_DEVICE` | `cuda` | Inference device (`cuda` or `cpu`) |

Example usage:

```bash
# Run with specific model and resolution
docker run -it --rm \
    --runtime=nvidia \
    --gpus all \
    -e DA3_MODEL=depth-anything/DA3-SMALL \
    -e DA3_INFERENCE_HEIGHT=308 \
    -e DA3_INFERENCE_WIDTH=308 \
    depth_anything_3_ros2:gpu

# Override VRAM detection for shared GPU systems
docker run -it --rm \
    --runtime=nvidia \
    --gpus all \
    -e DA3_VRAM_LIMIT_MB=4096 \
    depth_anything_3_ros2:gpu
```

In docker-compose.yml:

```yaml
services:
  depth-anything-3-gpu:
    environment:
      - DA3_MODEL=depth-anything/DA3-SMALL
      - DA3_INFERENCE_HEIGHT=308
      - DA3_INFERENCE_WIDTH=308
```

### Docker Testing and Validation

Automated test suite for validating Docker images:

```bash
cd docker
chmod +x test_docker.sh
./test_docker.sh
```

This comprehensive test suite validates:
- Docker and Docker Compose installation
- CPU and GPU image builds
- ROS2 installation and package builds
- Python dependencies
- CUDA availability (GPU images)
- Volume mounts and networking
- Model download capability

For detailed Docker documentation, see [docker/README.md](docker/README.md).

---

## Example Images and Benchmarks

### Sample Test Images

Download sample images for quick testing:

```bash
cd examples
./scripts/download_samples.sh
```

This downloads sample indoor, outdoor, and object images from public datasets.

### Testing with Static Images

```bash
# Test single image
python3 examples/scripts/test_with_images.py \
    --image examples/images/outdoor/street_01.jpg \
    --model depth-anything/DA3-BASE \
    --device cuda \
    --output-dir results/

# Batch process directory
python3 examples/scripts/test_with_images.py \
    --input-dir examples/images/outdoor/ \
    --output-dir results/ \
    --model depth-anything/DA3-BASE
```

### Performance Benchmarking

Run comprehensive benchmarks across multiple models and image sizes:

```bash
# Benchmark multiple models
python3 examples/scripts/benchmark.py \
    --images examples/images/ \
    --models depth-anything/DA3-SMALL,depth-anything/DA3-BASE,depth-anything/DA3-LARGE \
    --sizes 640x480,1280x720 \
    --device cuda \
    --output benchmark_results.json
```

Example output:
```
================================================================================
BENCHMARK SUMMARY
================================================================================
Model                          Device   Size         FPS      Time (ms)    GPU Mem (MB)
--------------------------------------------------------------------------------
depth-anything/DA3-SMALL       cuda     640x480      25.3     39.5         1512
depth-anything/DA3-BASE        cuda     640x480      19.8     50.5         2489
depth-anything/DA3-LARGE       cuda     640x480      11.7     85.4         3952
================================================================================
```

### Advanced Example Scripts

#### Depth Post-Processing

Apply filtering, hole filling, and enhancement to depth maps:

```bash
cd examples/scripts

# Process single depth map
python3 depth_postprocess.py \
    --input depth.npy \
    --output processed.npy \
    --visualize

# Batch process directory
python3 depth_postprocess.py \
    --input depth_dir/ \
    --output processed_dir/ \
    --batch
```

#### Multi-Camera Synchronization

Synchronize depth estimation from multiple cameras:

```bash
# Terminal 1: Launch multi-camera setup
ros2 launch depth_anything_3_ros2 multi_camera.launch.py \
    camera_namespaces:=cam_left,cam_right \
    image_topics:=/cam_left/image_raw,/cam_right/image_raw

# Terminal 2: Run synchronizer
python3 multi_camera_sync.py \
    --cameras cam_left cam_right \
    --sync-threshold 0.05 \
    --output synchronized_depth/
```

#### TensorRT Optimization (Jetson)

Optimize models for maximum performance on Jetson platforms:

```bash
# Optimize model
python3 optimize_tensorrt.py \
    --model depth-anything/DA3-BASE \
    --output da3_base_trt.pth \
    --precision fp16 \
    --benchmark

# Expected speedup: 2-3x faster inference
```

#### Performance Tuning

Quantization, ONNX export, and profiling:

```bash
# INT8 quantization
python3 performance_tuning.py quantize \
    --model depth-anything/DA3-BASE \
    --output da3_base_int8.pth

# Export to ONNX
python3 performance_tuning.py export-onnx \
    --model depth-anything/DA3-BASE \
    --output da3_base.onnx \
    --benchmark

# Profile layers
python3 performance_tuning.py profile \
    --model depth-anything/DA3-BASE \
    --layers \
    --memory
```

#### ROS2 Batch Processing

Process ROS2 bags through depth estimation:

```bash
./ros2_batch_process.sh \
    -i ./raw_bags \
    -o ./depth_bags \
    -m depth-anything/DA3-BASE \
    -d cuda
```

#### Node Profiling

Profile ROS2 node performance:

```bash
python3 profile_node.py \
    --model depth-anything/DA3-BASE \
    --device cuda \
    --duration 60
```

For more examples, see [examples/README.md](examples/README.md).

---

## Documentation

Complete documentation is available in multiple formats:

### Sphinx Documentation

Build and view the complete API documentation:

```bash
cd docs
pip install -r requirements.txt
make html
open build/html/index.html  # or xdg-open on Linux
```

### Documentation Contents

- **API Reference**: Complete API documentation with examples
  - [DA3 Inference Module](docs/source/api/da3_inference.rst)
  - [ROS2 Node Module](docs/source/api/depth_anything_3_node.rst)
  - [Utilities Module](docs/source/api/utils.rst)

- **User Guides**:
  - Installation and setup
  - Camera integration guide
  - Multi-camera configuration
  - Performance optimization
  - Troubleshooting

- **Tutorials**:
  - [Quick Start Tutorial](docs/source/tutorials/quick_start.rst) - Get up and running in minutes
  - [USB Camera Setup](docs/source/tutorials/usb_camera.rst) - Complete USB camera guide
  - [Multi-Camera Setup](docs/source/tutorials/multi_camera.rst) - Synchronized multi-camera depth
  - [Performance Tuning](docs/source/tutorials/performance_tuning.rst) - Optimization guide for all platforms

### Additional Documentation

- [Docker Deployment Guide](docker/README.md)
- [Example Images Guide](examples/README.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Validation Checklist](VALIDATION_CHECKLIST.md)

---

## Performance

### Current Status (PyTorch Baseline)

Measured on Jetson Orin NX 16GB (JetPack 6.0, L4T r36.2.0):

| Model | Backend | Resolution | FPS | Inference Time |
|-------|---------|------------|-----|----------------|
| DA3-SMALL | PyTorch FP32 | 518x518 | ~5.2 | ~193ms |

**Note**: TensorRT acceleration is not yet available due to ONNX opset incompatibility. See [TensorRT Status](#tensorrt-status) below.

### TensorRT Status

TensorRT acceleration has been validated on Jetson Orin NX 16GB:

- **Previous Issue**: TensorRT 8.6.2 (L4T r36.2.0) incompatible with DINOv2/Einsum ops
- **Solution**: Docker image updated to L4T r36.4.0 (TensorRT 10.3)
- **Status**: Validated - performance verified

**Validated Performance (2026-01-31):**
- Platform: Jetson Orin NX 16GB
- TensorRT Version: 10.3
- Model: DA3-SMALL at 518x518 FP16
- Throughput: 35.3 FPS
- GPU Latency: 26.4ms median (25.5ms min)
- Engine Size: 58MB
- Speedup: 6.8x over PyTorch baseline (~5.2 FPS)

**To enable TensorRT:**
```bash
# Rebuild with new base image
docker compose build depth-anything-3-jetson

# Run with auto TensorRT engine build
DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson
```

See [OPTIMIZATION_GUIDE.md](OPTIMIZATION_GUIDE.md) for detailed performance data.

### Validated TensorRT Performance

Measured on Jetson Orin NX 16GB with TensorRT 10.3 (2026-01-31):

| Model | Backend | Resolution | FPS | GPU Latency | Speedup vs PyTorch |
|-------|---------|------------|-----|-------------|-------------------|
| DA3-SMALL | TensorRT FP16 | 518x518 | 35.3 | 26.4ms (median) | 6.8x |
| DA3-SMALL | PyTorch FP32 | 518x518 | 5.2 | ~193ms | Baseline |

### Optimization Tips (Current)

1. **Use Smaller Models**: DA3-SMALL offers best speed with acceptable accuracy

2. **Reduce Input Resolution**: Lower resolution images process faster
```bash
--param inference_height:=308 inference_width:=308
```

3. **Queue Size**: Set to 1 to always process latest frame
```bash
--param queue_size:=1
```

4. **Disable Unused Outputs**: Save processing time
```bash
--param publish_colored_depth:=false
--param publish_confidence:=false
```

5. **Performance Profiling**: Profile to identify bottlenecks
```bash
python3 examples/scripts/profile_node.py --model depth-anything/DA3-BASE
```

For comprehensive optimization guide, see [OPTIMIZATION_GUIDE.md](OPTIMIZATION_GUIDE.md).

---

## Troubleshooting

### Common Issues

#### 1. Model Download Failures

**Error**: `Failed to load model from Hugging Face Hub` or `Connection timeout`

**Solutions**:
- **Check internet connection**: `ping huggingface.co`
- **Verify Hugging Face Hub is accessible**: May be blocked by firewall/proxy
- **Pre-download models manually**:
  ```bash
  python3 -c "from transformers import AutoImageProcessor, AutoModelForDepthEstimation; \
              AutoImageProcessor.from_pretrained('depth-anything/DA3-BASE'); \
              AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')"
  ```
- **Use custom cache directory**: Set `HF_HOME=/path/to/models` environment variable
- **For offline robots**: See [Offline Operation](#offline-operation-robots-without-internet) section

#### 2. Model Not Found on Offline Robot

**Error**: `Model depth-anything/DA3-BASE not found` on robot without internet

**Solution**: Pre-download models and copy cache directory:
```bash
# On development machine WITH internet:
python3 -c "from transformers import AutoModelForDepthEstimation; \
            AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')"
tar -czf da3_models.tar.gz -C ~/.cache/huggingface .

# Transfer to robot (USB, SCP, etc.) and extract:
ssh robot@robot-ip
mkdir -p ~/.cache/huggingface
tar -xzf da3_models.tar.gz -C ~/.cache/huggingface/
```

Verify models are available:
```bash
ls ~/.cache/huggingface/hub/models--depth-anything--*
```

#### 3. CUDA Out of Memory

**Error**: `RuntimeError: CUDA out of memory`

**Solutions**:
- Use a smaller model (DA3-Small or DA3-Base)
- Reduce input resolution
- Close other GPU applications
- Switch to CPU mode temporarily

```bash
# Use smaller model
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  model_name:=depth-anything/DA3-SMALL

# Or use CPU
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  device:=cpu
```

#### 2. Model Download Failures

**Error**: `Failed to load model from Hugging Face Hub`

**Solutions**:
- Check internet connection
- Verify Hugging Face Hub is accessible
- Download model manually and use local path

```bash
# Download manually
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('depth-anything/DA3-BASE')"

# Use local path
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  model_name:=/path/to/local/model
```

#### 3. Image Encoding Mismatches

**Error**: `CV Bridge conversion failed`

**Solutions**:
- Check camera's output encoding
- Adjust `input_encoding` parameter

```bash
# For RGB cameras
--param input_encoding:=rgb8

# For BGR cameras (most common)
--param input_encoding:=bgr8
```

#### 4. No Image Received

**Solutions**:
- Verify camera is publishing: `ros2 topic echo /camera/image_raw`
- Check topic remapping is correct
- Verify QoS settings match camera

```bash
# List available topics
ros2 topic list | grep image

# Check topic info
ros2 topic info /camera/image_raw
```

#### 5. Low Frame Rate

**Solutions**:
- Check GPU utilization: `nvidia-smi`
- Enable performance logging
- Reduce image resolution
- Use smaller model

```bash
# Enable performance logging
--param log_inference_time:=true
```

---

## Development

### Running Tests

```bash
# Run all tests
cd ~/ros2_ws
colcon test --packages-select depth_anything_3_ros2

# View test results
colcon test-result --verbose

# Run specific test
python3 -m pytest src/depth_anything_3_ros2/test/test_inference.py -v
```

### Code Style

This package follows:
- PEP 8 for Python code
- Google-style docstrings
- Type hints for all functions
- No emojis in code or documentation

### Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Follow code style guidelines
4. Add tests for new functionality
5. Submit a pull request

---

## Citation

If you use Depth Anything 3 in your research, please cite the original paper:

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

This ROS2 wrapper is released under the MIT License.

The Depth Anything 3 model has its own license. Please refer to the [official repository](https://github.com/ByteDance-Seed/Depth-Anything-3) for model license information.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper/issues)
- **Discussions**: [GitHub Discussions](https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper/discussions)
- **ROS2 Documentation**: [ROS2 Humble Docs](https://docs.ros.org/en/humble/)
- **Depth Anything 3**: [Official Repository](https://github.com/ByteDance-Seed/Depth-Anything-3)

---

**Note**: This is an unofficial ROS2 wrapper. For the official Depth Anything 3 implementation, please visit the [ByteDance-Seed repository](https://github.com/ByteDance-Seed/Depth-Anything-3).
