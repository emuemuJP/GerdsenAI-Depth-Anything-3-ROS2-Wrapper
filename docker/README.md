# Docker Deployment Guide

This guide explains how to build and run the Depth Anything 3 ROS2 wrapper using Docker.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- For GPU support: NVIDIA Docker runtime (`nvidia-docker2`)

### Installing NVIDIA Docker Runtime

```bash
# Add NVIDIA Docker repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Install nvidia-docker2
sudo apt-get update
sudo apt-get install -y nvidia-docker2

# Restart Docker
sudo systemctl restart docker

# Test GPU access
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
```

## Quick Start

> **Important**: No pre-built Docker images are published to Docker Hub or any container registry. You must build the images locally using the commands below. Running `docker-compose pull` will fail.

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

### Option 1: Docker Compose (Recommended)

#### CPU-Only Mode
```bash
# Build and run
docker-compose up -d depth-anything-3-cpu

# Attach to container
docker exec -it da3_ros2_cpu bash

# Inside container, test the node
ros2 run depth_anything_3_ros2 depth_anything_3_node --ros-args -p device:=cpu
```

#### GPU Mode
```bash
# Build and run
docker-compose up -d depth-anything-3-gpu

# Attach to container
docker exec -it da3_ros2_gpu bash

# Inside container, test the node
ros2 run depth_anything_3_ros2 depth_anything_3_node --ros-args -p device:=cuda
```

#### Development Mode (Source Mounted)
```bash
# Start development container
docker-compose up -d depth-anything-3-dev

# Attach and rebuild after code changes
docker exec -it da3_ros2_dev bash
cd /ros2_ws
colcon build --packages-select depth_anything_3_ros2
source install/setup.bash
```

#### USB Camera Example (Standalone)
```bash
# Run with USB camera connected at /dev/video0
docker-compose up depth-anything-3-usb-camera
```

### Option 2: Manual Docker Build

#### Build CPU Image
```bash
docker build -t depth_anything_3_ros2:cpu \
    --build-arg BUILD_TYPE=base \
    .
```

#### Build GPU Image
```bash
docker build -t depth_anything_3_ros2:gpu \
    --build-arg BUILD_TYPE=cuda-base \
    --build-arg CUDA_VERSION=12.2.0 \
    .
```

#### Run Container
```bash
# CPU mode
docker run -it --rm \
    --network host \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v $(pwd)/models:/root/.cache/huggingface:rw \
    depth_anything_3_ros2:cpu

# GPU mode
docker run -it --rm \
    --runtime=nvidia \
    --gpus all \
    --network host \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v $(pwd)/models:/root/.cache/huggingface:rw \
    -v /dev:/dev:rw \
    --privileged \
    depth_anything_3_ros2:gpu
```

## Using the Container

### Basic Commands

Once inside the container:

```bash
# Source workspace (if not automatic)
source /ros2_ws/install/setup.bash

# Run the node
ros2 run depth_anything_3_ros2 depth_anything_3_node

# Launch with parameters
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
    image_topic:=/camera/image_raw \
    model_name:=depth-anything/DA3-BASE \
    device:=cuda

# List available topics
ros2 topic list

# Monitor depth output
ros2 topic hz /depth_anything_3/depth
```

### With USB Camera

```bash
# Terminal 1: Start camera
ros2 run v4l2_camera v4l2_camera_node --ros-args \
    -p image_size:="[640,480]" \
    -r __ns:=/camera

# Terminal 2: Start depth estimation
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
    image_topic:=/camera/image_raw
```

### Visualization with RViz2

```bash
# Allow X11 forwarding (run on host)
xhost +local:docker

# Inside container
rviz2 -d /ros2_ws/install/depth_anything_3_ros2/share/depth_anything_3_ros2/rviz/depth_view.rviz
```

## Volume Mounts Explained

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./models` | `/root/.cache/huggingface` | Model cache (avoid re-downloading) |
| `./examples` | `/examples` | Test images and scripts |
| `/tmp/.X11-unix` | `/tmp/.X11-unix` | X11 display for RViz2 |
| `/dev` | `/dev` | Camera device access |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ROS_DOMAIN_ID` | `0` | ROS2 domain ID for network isolation |
| `DISPLAY` | Host `$DISPLAY` | X11 display for GUI applications |
| `NVIDIA_VISIBLE_DEVICES` | `all` | GPU devices accessible to container |

## Multi-Container Setup

Run multiple instances for different cameras:

```bash
# Create custom docker-compose override
cat > docker-compose.override.yml <<EOF
version: '3.8'
services:
  camera1:
    extends: depth-anything-3-gpu
    container_name: da3_cam1
    environment:
      - ROS_NAMESPACE=/cam1
    command: >
      bash -c "
      source /ros2_ws/install/setup.bash &&
      ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py
      namespace:=/cam1 image_topic:=/cam1/image_raw
      "

  camera2:
    extends: depth-anything-3-gpu
    container_name: da3_cam2
    environment:
      - ROS_NAMESPACE=/cam2
    command: >
      bash -c "
      source /ros2_ws/install/setup.bash &&
      ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py
      namespace:=/cam2 image_topic:=/cam2/image_raw
      "
EOF

docker-compose up -d camera1 camera2
```

## Troubleshooting

### GPU Not Detected
```bash
# Inside container, check CUDA
python3 -c "import torch; print(torch.cuda.is_available())"
nvidia-smi

# If false, ensure nvidia-docker2 is installed and container uses --gpus flag
```

### X11 Display Issues
```bash
# On host
xhost +local:docker

# Check DISPLAY variable inside container
echo $DISPLAY
```

### Permission Denied for Camera
```bash
# Ensure container runs with --privileged flag
# Or add user to video group on host:
sudo usermod -aG video $USER
```

### Model Download Issues
```bash
# Pre-download models on host
python3 -c "from huggingface_hub import snapshot_download; \
    snapshot_download('depth-anything/DA3-BASE', cache_dir='./models')"

# Then models will be available in container via volume mount
```

## Performance Optimization

### Reduce Build Time
```bash
# Use Docker BuildKit
export DOCKER_BUILDKIT=1
docker build --build-arg BUILD_TYPE=cuda-base -t depth_anything_3_ros2:gpu .
```

### Reduce Image Size
```bash
# Multi-stage build already optimized
# Check image size
docker images | grep depth_anything_3_ros2

# Clean up intermediate images
docker image prune -f
```

### Network Performance
```bash
# Use host network mode for best ROS2 performance
docker run --network host ...
```

## Jetson Deployment

For NVIDIA Jetson devices (Orin AGX, Orin NX, Orin Nano):

### Prerequisites

- JetPack 6.0+ (L4T r36.2.0+)
- Docker with NVIDIA container runtime
- ~15GB disk space for the built image

### Quick Start (Jetson)

```bash
# Clone and enter repository (on Jetson)
git clone https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper.git
cd GerdsenAI-Depth-Anything-3-ROS2-Wrapper

# Build the Jetson image (takes ~45 minutes)
docker compose build depth-anything-3-jetson

# Run the container
docker compose up -d depth-anything-3-jetson
docker exec -it da3_jetson bash

# Inside container: test inference
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw \
  model_name:=depth-anything/DA3-SMALL \
  log_inference_time:=true
```

### Windows to Jetson Workflow

If cloning on Windows and transferring to Jetson:

```bash
# On Windows: Fix line endings before transfer
# The Dockerfile handles this automatically with:
# RUN sed -i 's/\r$//' /ros_entrypoint.sh

# Transfer to Jetson (from Windows)
scp -r . user@jetson-ip:~/depth_anything_3_ros2/
```

### Known Jetson Build Requirements

| Component | Requirement | Notes |
|-----------|-------------|-------|
| **Base Image** | `dustynv/ros:humble-ros-base-l4t-r36.2.0` | No NGC auth required |
| **torchvision** | Build from source | NVIDIA wheel ABI mismatch |
| **cv_bridge** | Build from source | OpenCV version conflict |
| **pycolmap/evo** | Runtime patched | No ARM64 wheels |
| **Final Image Size** | ~14.9GB | Includes PyTorch, ROS2, models |

### Expected Performance

| Backend | Model | Resolution | FPS | Notes |
|---------|-------|------------|-----|-------|
| PyTorch FP32 | DA3-SMALL | 518x518 | ~5.2 | Baseline |
| TensorRT FP16 | DA3-SMALL | 518x518 | ~20-30 | Requires image rebuild |

**TensorRT Status**: Available with L4T r36.4.0 base image (TensorRT 10.3). Rebuild Docker image to enable.

### Manual Build (Alternative)

```bash
# Build Jetson image directly
docker build -t depth_anything_3_ros2:jetson \
    --build-arg BUILD_TYPE=jetson-base \
    --build-arg L4T_VERSION=r36.2.0 \
    .

# Run with GPU access
docker run -it --rm \
    --runtime=nvidia \
    --gpus all \
    --network host \
    -v /dev:/dev:rw \
    --privileged \
    depth_anything_3_ros2:jetson
```

## Cleanup

```bash
# Stop all containers
docker-compose down

# Remove images
docker rmi depth_anything_3_ros2:cpu depth_anything_3_ros2:gpu

# Clean up models cache (optional)
rm -rf models/*
```

## Advanced Usage

### Custom Model Path
```bash
docker run -it --rm \
    -v /path/to/custom/models:/models:ro \
    depth_anything_3_ros2:gpu \
    bash -c "ros2 run depth_anything_3_ros2 depth_anything_3_node \
        --ros-args -p model_name:=/models/my_custom_model"
```

### Resource Limits
```bash
# Limit GPU memory
docker run --gpus '"device=0,memory=4096"' ...

# Limit CPU and RAM
docker run --cpus=4 --memory=8g ...
```

## Support

For Docker-related issues:
- Check Docker logs: `docker logs <container_name>`
- Inspect container: `docker inspect <container_name>`
- Check resource usage: `docker stats`

For package issues, refer to the main README.md
