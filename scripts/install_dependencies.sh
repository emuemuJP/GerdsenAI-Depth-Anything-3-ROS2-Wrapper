#!/bin/bash
# GerdsenAI Depth Anything 3 ROS2 Wrapper - Dependency Installation Script
# Run this script after cloning the repository to install all required dependencies
#
# Usage:
#   cd ~/depth_anything_3_ros2
#   bash scripts/install_dependencies.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "============================================"
echo " GerdsenAI Depth Anything 3 ROS2 Wrapper"
echo " Dependency Installation Script"
echo "============================================"
echo ""

# Detect ROS2 distribution
if [ -z "$ROS_DISTRO" ]; then
    log_info "Detecting ROS2 distribution..."
    for distro in humble jazzy iron; do
        if [ -f "/opt/ros/${distro}/setup.bash" ]; then
            export ROS_DISTRO="$distro"
            source "/opt/ros/${distro}/setup.bash"
            log_info "Found and sourced ROS2 ${distro}"
            break
        fi
    done
fi

if [ -z "$ROS_DISTRO" ]; then
    log_error "No ROS2 installation found in /opt/ros/"
    log_error "Please install ROS2 Humble first:"
    log_error "  https://docs.ros.org/en/humble/Installation.html"
    exit 1
fi

log_info "Using ROS2 distribution: $ROS_DISTRO"

# Update package lists
log_info "Updating package lists..."
sudo apt update

# Install ROS2 dependencies
log_info "Installing ROS2 dependencies..."
ROS_PACKAGES=(
    "ros-${ROS_DISTRO}-cv-bridge"
    "ros-${ROS_DISTRO}-sensor-msgs"
    "ros-${ROS_DISTRO}-std-msgs"
    "ros-${ROS_DISTRO}-image-transport"
    "ros-${ROS_DISTRO}-image-publisher"
    "ros-${ROS_DISTRO}-rviz2"
    "ros-${ROS_DISTRO}-rqt-image-view"
    "ros-${ROS_DISTRO}-rqt-graph"
)

for pkg in "${ROS_PACKAGES[@]}"; do
    if dpkg -l | grep -q "^ii  ${pkg} "; then
        log_info "  [OK] ${pkg} already installed"
    else
        log_info "  Installing ${pkg}..."
        sudo apt install -y "$pkg" || log_warn "  Failed to install ${pkg}"
    fi
done

# Install Python dependencies
log_info "Installing Python dependencies..."
PYTHON_PACKAGES=(
    "numpy>=1.24.0"
    "opencv-python>=4.8.0"
    "pillow>=10.0.0"
    "transformers>=4.35.0"
    "huggingface-hub>=0.19.0"
    "timm>=0.9.0"
    "safetensors>=0.4.0"
)

# Check if we're on Jetson (ARM64)
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
    log_info "Detected ARM64 (Jetson) architecture"

    # =========================================
    # CUDA/cuDNN Setup for Jetson
    # =========================================
    # On Jetson, CUDA and cuDNN come with JetPack (system libraries)
    # We just need to ensure paths are set correctly

    log_info "Checking CUDA/cuDNN installation..."

    # Find CUDA installation
    CUDA_PATH=""
    for cuda_dir in /usr/local/cuda /usr/local/cuda-12 /usr/local/cuda-12.6 /usr/local/cuda-12.2; do
        if [ -d "$cuda_dir" ]; then
            CUDA_PATH="$cuda_dir"
            break
        fi
    done

    if [ -n "$CUDA_PATH" ]; then
        log_info "  [OK] CUDA found: $CUDA_PATH"

        # Check nvcc
        if [ -f "$CUDA_PATH/bin/nvcc" ]; then
            NVCC_VERSION=$("$CUDA_PATH/bin/nvcc" --version | grep "release" | awk '{print $6}' | cut -d',' -f1)
            log_info "  [OK] nvcc version: $NVCC_VERSION"
        else
            log_warn "  nvcc not found in $CUDA_PATH/bin"
        fi

        # Set CUDA environment if not already set
        if [[ ":$PATH:" != *":$CUDA_PATH/bin:"* ]]; then
            export PATH="$CUDA_PATH/bin:$PATH"
            log_info "  Added $CUDA_PATH/bin to PATH"
        fi

        if [[ ":$LD_LIBRARY_PATH:" != *":$CUDA_PATH/lib64:"* ]]; then
            export LD_LIBRARY_PATH="$CUDA_PATH/lib64:$LD_LIBRARY_PATH"
            log_info "  Added $CUDA_PATH/lib64 to LD_LIBRARY_PATH"
        fi

        # Check if CUDA env is in bashrc
        if ! grep -q "CUDA_HOME" ~/.bashrc 2>/dev/null; then
            log_info "  Adding CUDA environment to ~/.bashrc..."
            cat >> ~/.bashrc << EOF

# CUDA environment (added by install_dependencies.sh)
export CUDA_HOME=$CUDA_PATH
export PATH=\$CUDA_HOME/bin:\$PATH
export LD_LIBRARY_PATH=\$CUDA_HOME/lib64:\$LD_LIBRARY_PATH
EOF
            log_info "  [OK] CUDA environment added to ~/.bashrc"
        fi
    else
        log_error "  CUDA not found in /usr/local/cuda*"
        log_error "  JetPack may not be properly installed"
        log_error "  Install JetPack via SDK Manager or flash the device"
        exit 1
    fi

    # Check cuDNN
    CUDNN_VERSION=$(python3 -c "
import ctypes
try:
    cudnn = ctypes.CDLL('libcudnn.so')
    print('installed')
except:
    print('not found')
" 2>/dev/null)

    if [ "$CUDNN_VERSION" = "installed" ]; then
        # Try to get version from header or dpkg
        CUDNN_VER=$(dpkg -l 2>/dev/null | grep cudnn | head -1 | awk '{print $3}' | cut -d'-' -f1 || echo "unknown")
        log_info "  [OK] cuDNN: $CUDNN_VER"
    else
        log_warn "  cuDNN library not found"
        log_warn "  Installing cuDNN (if available via apt)..."
        sudo apt-get update && sudo apt-get install -y libcudnn8 libcudnn8-dev 2>/dev/null || {
            log_warn "  cuDNN not available via apt. It should come with JetPack."
            log_warn "  If you're on JetPack 6.x, cuDNN 9.x should already be installed."
        }
    fi

    # Verify nvidia-smi
    if command -v nvidia-smi &> /dev/null; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        DRIVER_VER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
        log_info "  [OK] GPU: $GPU_NAME (Driver: $DRIVER_VER)"
    else
        log_warn "  nvidia-smi not found"
    fi

    log_info "Checking PyTorch CUDA support..."

    # Check if PyTorch has CUDA support (not just installed)
    TORCH_CUDA=$(python3 -c "import torch; print(torch.version.cuda or 'None')" 2>/dev/null || echo "None")
    TORCH_VERSION=$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null || echo "None")

    if [ "$TORCH_CUDA" != "None" ] && [ "$TORCH_CUDA" != "" ]; then
        log_info "  [OK] PyTorch ${TORCH_VERSION} with CUDA ${TORCH_CUDA}"
    else
        if [ "$TORCH_VERSION" != "None" ]; then
            log_warn "  PyTorch ${TORCH_VERSION} found but NO CUDA support (CPU-only)"
            log_warn "  Uninstalling CPU-only PyTorch..."
            pip3 uninstall -y torch torchvision 2>/dev/null || true
        fi

        log_info "Installing NVIDIA PyTorch for Jetson (JetPack 6.x)..."
        log_info "  This may take a few minutes..."

        # PyTorch 2.3.0 wheel for JetPack 6.x (L4T R36.x, CUDA 12.x)
        # Source: https://forums.developer.nvidia.com/t/pytorch-for-jetson/
        TORCH_WHEEL_URL="https://nvidia.box.com/shared/static/mp164asf3sceb570wvjsrezk1p4ftj8t.whl"
        TORCH_WHEEL="/tmp/torch-2.3.0-cp310-cp310-linux_aarch64.whl"

        log_info "  Downloading PyTorch wheel..."
        wget -q --show-progress -O "$TORCH_WHEEL" "$TORCH_WHEEL_URL" || {
            log_error "Failed to download PyTorch wheel"
            log_error "Manual install: pip3 install --no-cache $TORCH_WHEEL_URL"
            exit 1
        }

        log_info "  Installing PyTorch..."
        pip3 install --no-cache-dir "$TORCH_WHEEL" || {
            log_error "Failed to install PyTorch"
            exit 1
        }
        rm -f "$TORCH_WHEEL"

        # Verify CUDA is now available
        TORCH_CUDA_CHECK=$(python3 -c "import torch; print(torch.version.cuda or 'None')" 2>/dev/null || echo "None")
        if [ "$TORCH_CUDA_CHECK" != "None" ]; then
            log_info "  [OK] PyTorch installed with CUDA ${TORCH_CUDA_CHECK}"
        else
            log_error "  PyTorch installed but CUDA still not available"
            log_error "  This may indicate a JetPack/CUDA version mismatch"
        fi

        # Build torchvision from source (required for NVIDIA PyTorch ABI compatibility)
        log_info "Building torchvision from source (required for Jetson)..."
        sudo apt-get update && sudo apt-get install -y --no-install-recommends \
            libjpeg-dev zlib1g-dev libpython3-dev libopenblas-dev \
            libavcodec-dev libavformat-dev libswscale-dev || true

        TORCHVISION_DIR="/tmp/torchvision_build"
        rm -rf "$TORCHVISION_DIR"
        git clone --depth 1 --branch v0.18.0 https://github.com/pytorch/vision.git "$TORCHVISION_DIR"
        cd "$TORCHVISION_DIR"

        log_info "  Compiling torchvision (this takes a while)..."
        TORCH_CUDA_ARCH_LIST="8.7" FORCE_CUDA=1 python3 setup.py bdist_wheel 2>&1 | tail -5
        pip3 install --no-cache-dir dist/*.whl || {
            log_warn "  torchvision build failed, trying pip install..."
            pip3 install torchvision
        }
        cd - > /dev/null
        rm -rf "$TORCHVISION_DIR"

        log_info "  [OK] torchvision installed"
    fi
else
    log_info "Detected x86_64 architecture"
    log_info "Installing PyTorch with CUDA support..."
    pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu121 || {
        log_warn "CUDA PyTorch installation failed, trying CPU version..."
        pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    }
fi

# Install other Python packages
log_info "Installing Python packages..."
for pkg in "${PYTHON_PACKAGES[@]}"; do
    pip3 install "$pkg" || log_warn "Failed to install $pkg"
done

# Install Depth Anything 3 from ByteDance
log_info "Installing Depth Anything 3 package from ByteDance..."
if python3 -c "from depth_anything_3.api import DepthAnything3" 2>/dev/null; then
    log_info "  [OK] Depth Anything 3 already installed"
else
    pip3 install git+https://github.com/ByteDance-Seed/Depth-Anything-3.git || {
        log_error "Failed to install Depth Anything 3 package"
        log_error "Try manually: pip3 install git+https://github.com/ByteDance-Seed/Depth-Anything-3.git"
    }
fi

# Get the script directory (repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Build the ROS2 package
log_info "Building ROS2 workspace..."
cd "$REPO_ROOT"
source "/opt/ros/${ROS_DISTRO}/setup.bash"
colcon build --packages-select depth_anything_3_ros2 --symlink-install

if [ $? -eq 0 ]; then
    log_info "Build successful"
else
    log_error "Build failed"
    exit 1
fi

# Source the workspace
source "${REPO_ROOT}/install/setup.bash"

# Verify installation
log_info "Verifying installation..."
if ros2 pkg list | grep -q "depth_anything_3_ros2"; then
    log_info "  [OK] Package depth_anything_3_ros2 found"
else
    log_error "  Package depth_anything_3_ros2 not found"
    exit 1
fi

# Download sample images
if [ -f "${REPO_ROOT}/examples/scripts/download_samples.sh" ]; then
    log_info "Downloading sample images..."
    cd "${REPO_ROOT}/examples" && bash scripts/download_samples.sh
    cd "$REPO_ROOT"
fi

# Check CUDA availability
log_info "Checking CUDA availability..."
if python3 -c "import torch; print('CUDA available:', torch.cuda.is_available())" 2>/dev/null; then
    CUDA_AVAIL=$(python3 -c "import torch; print(torch.cuda.is_available())")
    if [ "$CUDA_AVAIL" = "True" ]; then
        log_info "  [OK] CUDA is available"
        python3 -c "import torch; print('  GPU:', torch.cuda.get_device_name(0))"
    else
        log_warn "  CUDA not available. Will use CPU (slower performance)"
    fi
else
    log_warn "  Could not check CUDA availability"
fi

echo ""
echo "============================================"
echo " Installation Complete"
echo "============================================"
echo ""
log_info "To use the package, source the workspace:"
echo ""
echo "  source /opt/ros/${ROS_DISTRO}/setup.bash"
echo "  source ${REPO_ROOT}/install/setup.bash"
echo ""
log_info "To run the demo:"
echo ""
echo "  ./GerdsenAI-DA3-ROS2-Wrapper-demo_rviz_full.sh"
echo ""
log_info "Or add to your ~/.bashrc:"
echo ""
echo "  echo 'source /opt/ros/${ROS_DISTRO}/setup.bash' >> ~/.bashrc"
echo "  echo 'source ${REPO_ROOT}/install/setup.bash' >> ~/.bashrc"
echo ""
