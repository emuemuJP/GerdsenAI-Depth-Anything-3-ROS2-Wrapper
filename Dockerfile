# Depth Anything 3 ROS2 Wrapper - Docker Image
# Multi-stage build for optimized image size
# Supports CPU, CUDA (x86), and Jetson ARM64 builds

# Build arguments
ARG ROS_DISTRO=humble
ARG CUDA_VERSION=12.2.0
ARG UBUNTU_VERSION=22.04
ARG L4T_VERSION=r36.2.0
ARG BUILD_TYPE=base

# Model selection arguments (used by setup_models.py)
ARG INSTALL_MODELS=""
ARG DOWNLOAD_MODELS_AT_BUILD=false

# ==============================================================================
# Stage 1: Base image with ROS2 Humble
# ==============================================================================
FROM osrf/ros:${ROS_DISTRO}-desktop AS base

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-opencv \
    git \
    wget \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install ROS2 dependencies
RUN apt-get update && apt-get install -y \
    ros-${ROS_DISTRO}-cv-bridge \
    ros-${ROS_DISTRO}-image-transport \
    ros-${ROS_DISTRO}-vision-opencv \
    ros-${ROS_DISTRO}-v4l2-camera \
    && rm -rf /var/lib/apt/lists/*

# ==============================================================================
# Stage 2: CUDA-enabled image (for GPU support)
# ==============================================================================
FROM nvidia/cuda:${CUDA_VERSION}-cudnn8-runtime-ubuntu${UBUNTU_VERSION} AS cuda-base

# Copy ROS2 from base stage
COPY --from=base /opt/ros /opt/ros
COPY --from=base /usr/bin/python3 /usr/bin/python3
COPY --from=base /usr/lib/python3 /usr/lib/python3

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-opencv \
    git \
    wget \
    curl \
    vim \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install ROS2 dependencies
RUN apt-get update && apt-get install -y \
    ros-humble-cv-bridge \
    ros-humble-image-transport \
    ros-humble-vision-opencv \
    ros-humble-v4l2-camera \
    && rm -rf /var/lib/apt/lists/*

# ==============================================================================
# Stage 2b: Jetson ARM64 image (for NVIDIA Jetson devices)
# Uses dusty-nv's jetson-containers (public, no NGC auth required)
# https://github.com/dusty-nv/jetson-containers
#
# IMPORTANT: OpenCV Conflict Resolution
# --------------------------------------
# The dustynv base image includes OpenCV 4.8.1 with CUDA support (opencv-dev, opencv-libs).
# ROS Humble apt packages (ros-humble-cv-bridge, ros-humble-vision-opencv) depend on
# Ubuntu's OpenCV 4.5.4, which conflicts with the pre-installed version.
#
# Solution: Build cv_bridge and image_geometry from source against OpenCV 4.8.1.
# This preserves CUDA acceleration while providing ROS2 compatibility.
# ==============================================================================
FROM dustynv/ros:humble-ros-base-l4t-${L4T_VERSION} AS jetson-base

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Refresh ROS GPG key (may be expired in base image)
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /tmp/ros.key \
    && gpg --batch --yes --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg /tmp/ros.key \
    && rm /tmp/ros.key

# Verify OpenCV 4.8.x is present (critical check - build will fail if missing)
RUN echo "=== Checking pre-installed OpenCV ===" && \
    pkg-config --modversion opencv4 && \
    OPENCV_VERSION=$(pkg-config --modversion opencv4) && \
    echo "Found OpenCV version: $OPENCV_VERSION" && \
    case "$OPENCV_VERSION" in \
        4.8.*) echo "OpenCV 4.8.x detected - proceeding with source build of cv_bridge" ;; \
        4.5.*) echo "WARNING: OpenCV 4.5.x detected - apt packages should work, but we'll build from source anyway" ;; \
        *) echo "ERROR: Unexpected OpenCV version: $OPENCV_VERSION" && exit 1 ;; \
    esac

# Install system dependencies
# NOTE: Do NOT install python3-opencv - use pre-installed CUDA-enabled version
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    git \
    wget \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install ROS2 build dependencies
# NOTE: Do NOT install ros-humble-cv-bridge or ros-humble-vision-opencv via apt
#       These packages have hard dependencies on libopencv-*-dev 4.5.4 which
#       conflicts with the pre-installed opencv-dev 4.8.1 package.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-humble-sensor-msgs \
    ros-humble-std-msgs \
    ros-humble-geometry-msgs \
    ros-humble-ament-cmake \
    ros-humble-ament-cmake-auto \
    ros-humble-rclcpp \
    ros-humble-rclpy \
    ros-humble-pluginlib \
    ros-humble-message-filters \
    python3-colcon-common-extensions \
    libboost-python-dev \
    && rm -rf /var/lib/apt/lists/*

# Build cv_bridge and image_geometry from source against existing OpenCV 4.8.1
WORKDIR /tmp/ros_build
RUN echo "=== Building cv_bridge from source ===" && \
    git clone --depth 1 -b humble https://github.com/ros-perception/vision_opencv.git && \
    cd vision_opencv && \
    echo "Cloned vision_opencv repository" && \
    ls -la

RUN /bin/bash -c '\
    set -e; \
    source /opt/ros/humble/setup.bash; \
    echo "=== Starting colcon build ==="; \
    cd /tmp/ros_build; \
    colcon build \
        --packages-select cv_bridge image_geometry \
        --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
        --event-handlers console_direct+; \
    echo "=== Build completed successfully ==="; \
    ls -la install/; \
    '

# Install built packages to /opt/ros/humble
# Structure: install/<pkg>/lib, install/<pkg>/share, install/<pkg>/local/lib/python3.10/...
RUN echo "=== Installing cv_bridge to /opt/ros/humble ===" && \
    # Copy shared libraries
    cp -r /tmp/ros_build/install/cv_bridge/lib/*.so* /opt/ros/humble/lib/ 2>/dev/null || true && \
    cp -r /tmp/ros_build/install/image_geometry/lib/*.so* /opt/ros/humble/lib/ 2>/dev/null || true && \
    # Copy Python packages to site-packages
    cp -r /tmp/ros_build/install/cv_bridge/local/lib/python3.10/dist-packages/* \
        /opt/ros/humble/lib/python3.10/site-packages/ 2>/dev/null || true && \
    cp -r /tmp/ros_build/install/image_geometry/local/lib/python3.10/dist-packages/* \
        /opt/ros/humble/lib/python3.10/site-packages/ 2>/dev/null || true && \
    # Copy CMake/share files
    cp -r /tmp/ros_build/install/cv_bridge/share/* /opt/ros/humble/share/ 2>/dev/null || true && \
    cp -r /tmp/ros_build/install/image_geometry/share/* /opt/ros/humble/share/ 2>/dev/null || true && \
    # Copy include files
    cp -r /tmp/ros_build/install/cv_bridge/include/* /opt/ros/humble/include/ 2>/dev/null || true && \
    cp -r /tmp/ros_build/install/image_geometry/include/* /opt/ros/humble/include/ 2>/dev/null || true && \
    echo "=== Installation complete ===" && \
    rm -rf /tmp/ros_build

# Install image_transport AFTER cv_bridge is available
# This should now work since cv_bridge is built and available
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-humble-image-transport \
    && rm -rf /var/lib/apt/lists/* \
    || echo "WARNING: ros-humble-image-transport install had issues, may need source build"

# Verify cv_bridge is importable
RUN /bin/bash -c '\
    source /opt/ros/humble/setup.bash; \
    python3 -c "import cv_bridge; print(\"cv_bridge import successful\")" || \
    echo "WARNING: cv_bridge Python import failed - check PYTHONPATH"; \
    '

WORKDIR /

# ==============================================================================
# Stage 3: Build stage (installs Python dependencies)
# ==============================================================================
FROM ${BUILD_TYPE} AS builder

ARG BUILD_TYPE

# Set working directory
WORKDIR /tmp/build

# Copy requirements
COPY requirements.txt .

# Upgrade pip
RUN pip3 install --upgrade pip setuptools wheel

# Install PyTorch based on build type
RUN if [ "$BUILD_TYPE" = "cuda-base" ]; then \
        pip3 install torch torchvision \
            --index-url https://download.pytorch.org/whl/cu121; \
    elif [ "$BUILD_TYPE" = "jetson-base" ]; then \
        # Jetson uses PyTorch wheels from NVIDIA's Jetson AI Lab or pre-installed from JetPack
        pip3 install --no-cache-dir \
            --index-url https://pypi.jetson-ai-lab.dev/jp6/cu126 \
            torch torchvision || \
        pip3 install torch torchvision; \
    else \
        pip3 install torch torchvision \
            --index-url https://download.pytorch.org/whl/cpu \
            --ignore-installed sympy; \
    fi

# Install other Python dependencies
RUN pip3 install --no-cache-dir \
    "transformers>=4.35.0" \
    "huggingface-hub>=0.19.0" \
    "opencv-python>=4.8.0" \
    "pillow>=10.0.0" \
    "numpy>=1.24.0,<2.0" \
    "timm>=0.9.0"

# Install Depth Anything 3
# NOTE: Installing with --no-deps because pycolmap/open3d don't have ARM64 wheels.
# We manually install only the inference-required dependencies above.
RUN pip3 install --no-cache-dir --no-deps \
    git+https://github.com/ByteDance-Seed/Depth-Anything-3.git && \
    pip3 install --no-cache-dir einops

# ==============================================================================
# Stage 4: Final runtime image
# ==============================================================================
FROM ${BUILD_TYPE} AS runtime

ARG BUILD_TYPE

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.10/dist-packages \
    /usr/local/lib/python3.10/dist-packages

# Create workspace
RUN mkdir -p /ros2_ws/src
WORKDIR /ros2_ws

# Copy package source
COPY . /ros2_ws/src/depth_anything_3_ros2

# Source ROS2 and build package
RUN /bin/bash -c "source /opt/ros/humble/setup.bash && \
    colcon build --packages-select depth_anything_3_ros2 && \
    rm -rf build log"

# Setup entrypoint (fix Windows line endings if present)
COPY docker/ros_entrypoint.sh /ros_entrypoint.sh
RUN sed -i 's/\r$//' /ros_entrypoint.sh && chmod +x /ros_entrypoint.sh

# Environment setup
ENV ROS_DISTRO=humble
ENV AMENT_PREFIX_PATH=/ros2_ws/install/depth_anything_3_ros2
ENV PYTHONPATH=/ros2_ws/install/depth_anything_3_ros2/lib/python3.10/site-packages:${PYTHONPATH}

# Source ROS2 workspace in bashrc
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc && \
    echo "source /ros2_ws/install/setup.bash" >> ~/.bashrc

# Install PyYAML for setup_models.py
RUN pip3 install --no-cache-dir pyyaml

# Copy setup script and model catalog
COPY scripts/setup_models.py /app/scripts/setup_models.py
COPY config/model_catalog.yaml /app/config/model_catalog.yaml
RUN chmod +x /app/scripts/setup_models.py

# Optionally download models at build time
ARG INSTALL_MODELS
ARG DOWNLOAD_MODELS_AT_BUILD
RUN if [ "$DOWNLOAD_MODELS_AT_BUILD" = "true" ] && [ -n "$INSTALL_MODELS" ]; then \
        echo "Downloading models: $INSTALL_MODELS"; \
        for model in $(echo $INSTALL_MODELS | tr ',' ' '); do \
            python3 /app/scripts/setup_models.py --model "$model" --no-config; \
        done; \
    fi

# Environment variables for runtime configuration
ENV DA3_MODEL=""
ENV DA3_INFERENCE_HEIGHT=""
ENV DA3_INFERENCE_WIDTH=""
ENV DA3_VRAM_LIMIT_MB=""

ENTRYPOINT ["/ros_entrypoint.sh"]
CMD ["bash"]

# Metadata
LABEL maintainer="your@email.com"
LABEL description="Depth Anything 3 ROS2 Wrapper with CUDA support"
LABEL version="1.0.0"
