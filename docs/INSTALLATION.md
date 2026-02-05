# Installation Guide

Complete installation instructions for the Depth Anything 3 ROS2 Wrapper.

For quick installation, see the [Quick Install](#quick-install) section. For detailed manual steps, see [Manual Installation](#manual-installation).

---

## Quick Install

The fastest way to get started:

```bash
# Clone the repository
git clone https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper.git
cd GerdsenAI-Depth-Anything-3-ROS2-Wrapper

# Run the dependency installer (handles everything automatically)
bash scripts/install_dependencies.sh

# Source the workspace
source install/setup.bash
```

The installation script automatically:
- Detects your ROS2 distribution (Humble/Jazzy/Iron)
- Installs all ROS2 packages (cv-bridge, rviz2, image-publisher, etc.)
- Installs Python dependencies (PyTorch, OpenCV, transformers, etc.)
- Installs the Depth Anything 3 package from ByteDance
- Builds the ROS2 workspace
- Downloads sample images

---

## Prerequisites

### 1. ROS2 Humble on Ubuntu 22.04

```bash
# If not already installed
sudo apt update
sudo apt install ros-humble-desktop
```

### 2. CUDA 12.x (Optional, for GPU acceleration)

```bash
# For Jetson Orin, this comes with JetPack 6.x
# For desktop systems, install CUDA Toolkit from NVIDIA
nvidia-smi  # Verify CUDA installation
```

### 3. Internet Connection (for initial setup)

- Required for pip install of DA3 package
- Required for model weights download from Hugging Face Hub
- See [Offline Operation](#offline-operation) if deploying to robots without internet

---

## Manual Installation

If you prefer manual installation or the automated script fails:

### Step 1: Install ROS2 Dependencies

```bash
sudo apt install -y \
  ros-humble-cv-bridge \
  ros-humble-sensor-msgs \
  ros-humble-std-msgs \
  ros-humble-image-transport \
  ros-humble-image-publisher \
  ros-humble-rviz2 \
  ros-humble-rqt-image-view \
  ros-humble-rclpy
```

### Step 2: Install Python Dependencies

```bash
# Create and activate a virtual environment (recommended)
python3 -m venv ~/da3_venv
source ~/da3_venv/bin/activate

# Install PyTorch (required by DA3 library, NOT used for production inference)
# Production uses TensorRT on the Jetson host - see run.sh
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Install other dependencies
pip3 install transformers>=4.35.0 \
  huggingface-hub>=0.19.0 \
  opencv-python>=4.8.0 \
  pillow>=10.0.0 \
  numpy>=1.24.0 \
  timm>=0.9.0

# Install ByteDance DA3 Python API (pip handles cloning automatically)
pip3 install git+https://github.com/ByteDance-Seed/Depth-Anything-3.git
```

> **Note**: PyTorch is a library dependency but is NOT used for production inference. Production deployment uses TensorRT 10.3 on the Jetson host via shared memory IPC.

### Step 3: Clone and Build This ROS2 Wrapper

```bash
# Navigate to your ROS2 workspace
cd ~/ros2_ws/src  # Or create: mkdir -p ~/ros2_ws/src && cd ~/ros2_ws/src

# Clone THIS ROS2 wrapper repository
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

---

## Model Setup

### Interactive Setup (Recommended)

Use the interactive setup script to detect your hardware and download the optimal model:

```bash
# Interactive setup - detects hardware and recommends models
python scripts/setup_models.py

# Show detected hardware information only
python scripts/setup_models.py --detect

# List all available models with compatibility info
python scripts/setup_models.py --list-models

# Non-interactive installation of a specific model
python scripts/setup_models.py --model DA3-SMALL --no-download
```

### Manual Model Download

```bash
python3 -c "
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
print('Downloading DA3-BASE model...')
AutoImageProcessor.from_pretrained('depth-anything/DA3-BASE')
AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')
print('Model cached to ~/.cache/huggingface/hub/')
"
```

### Available Models

| Model | Parameters | Download Size | Use Case |
|-------|------------|---------------|----------|
| `depth-anything/DA3-SMALL` | 0.08B | ~1.5GB | Fast inference, lower accuracy |
| `depth-anything/DA3-BASE` | 0.12B | ~2.5GB | Balanced performance (recommended) |
| `depth-anything/DA3-LARGE` | 0.35B | ~4GB | Higher accuracy |
| `depth-anything/DA3-GIANT` | 1.15B | ~6.5GB | Best accuracy, slower |

---

## Offline Operation

For robots or systems without internet access, pre-download models on a connected machine:

```bash
# On a machine WITH internet connection:
python3 -c "
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
AutoImageProcessor.from_pretrained('depth-anything/DA3-BASE')
AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')
print('Model downloaded to ~/.cache/huggingface/hub/')
"

# Copy the cache directory to your offline robot:
tar -czf da3_models.tar.gz -C ~/.cache/huggingface .

# On target robot (via USB drive, SCP, etc.):
mkdir -p ~/.cache/huggingface
tar -xzf da3_models.tar.gz -C ~/.cache/huggingface/
```

### Custom Cache Directory

```bash
# Download to specific location
export HF_HOME=/path/to/models
python3 -c "from transformers import AutoModelForDepthEstimation; \
            AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')"

# On robot, point to the same location
export HF_HOME=/path/to/models
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py
```

---

## Docker Installation

For Docker-based deployment, see [Docker Deployment Guide](../docker/README.md).

Quick start with Docker:

```bash
# GPU mode (requires nvidia-docker)
docker-compose up -d depth-anything-3-gpu
docker exec -it da3_ros2_gpu bash

# Jetson deployment
docker-compose up -d depth-anything-3-jetson
```

---

## Next Steps

- [Quick Start Guide](../README.md#quick-start) - Run your first depth estimation
- [Configuration Reference](CONFIGURATION.md) - All parameters and topics
- [Jetson Deployment Guide](JETSON_DEPLOYMENT_GUIDE.md) - TensorRT optimization
- [Troubleshooting](../TROUBLESHOOTING.md) - Common issues and solutions
