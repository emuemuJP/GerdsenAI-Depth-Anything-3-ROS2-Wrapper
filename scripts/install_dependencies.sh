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
)

# Check if we're on Jetson (ARM64)
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
    log_info "Detected ARM64 (Jetson) architecture"
    log_info "Using PyTorch from NVIDIA repository..."
    
    # Check if PyTorch is installed
    if python3 -c "import torch; print(torch.__version__)" 2>/dev/null; then
        TORCH_VERSION=$(python3 -c "import torch; print(torch.__version__)")
        log_info "  [OK] PyTorch ${TORCH_VERSION} already installed"
    else
        log_warn "PyTorch not found. For Jetson, install from NVIDIA:"
        log_warn "  https://forums.developer.nvidia.com/t/pytorch-for-jetson/"
        log_warn "  Or: pip3 install --no-cache https://developer.download.nvidia.com/compute/redist/jp/v60/pytorch/torch-2.3.0a0+ebedce2.nv24.02-cp310-cp310-linux_aarch64.whl"
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
