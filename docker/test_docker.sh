#!/bin/bash
# Docker Image Test and Validation Script
# Tests both CPU and GPU Docker images for Depth Anything 3 ROS2 Wrapper

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Function to print test header
print_test() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
}

# Function to print failure
print_failure() {
    echo -e "${RED}✗ $1${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if NVIDIA GPU is available
has_nvidia_gpu() {
    if command_exists nvidia-smi; then
        nvidia-smi >/dev/null 2>&1
        return $?
    else
        return 1
    fi
}

# Test 1: Check Docker installation
test_docker_installed() {
    print_test "Test 1: Docker Installation"

    if command_exists docker; then
        DOCKER_VERSION=$(docker --version)
        print_success "Docker installed: $DOCKER_VERSION"
    else
        print_failure "Docker not installed"
        exit 1
    fi

    # Check docker group membership / permissions
    if ! docker info &> /dev/null; then
        print_failure "Cannot connect to Docker daemon (permission denied)"
        echo ""
        echo "Add your user to the docker group:"
        echo "  sudo usermod -aG docker \$USER"
        echo "Then log out and back in, or run: newgrp docker"
        exit 1
    fi
    print_success "Docker daemon accessible"
}

# Test 2: Check Docker Compose installation
test_docker_compose_installed() {
    print_test "Test 2: Docker Compose Installation"

    if command_exists docker-compose || docker compose version >/dev/null 2>&1; then
        if command_exists docker-compose; then
            COMPOSE_VERSION=$(docker-compose --version)
        else
            COMPOSE_VERSION=$(docker compose version)
        fi
        print_success "Docker Compose installed: $COMPOSE_VERSION"
    else
        print_failure "Docker Compose not installed"
        exit 1
    fi
}

# Test 3: Check NVIDIA Docker runtime
test_nvidia_docker() {
    print_test "Test 3: NVIDIA Docker Runtime"

    if has_nvidia_gpu; then
        GPU_INFO=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)
        print_success "NVIDIA GPU detected: $GPU_INFO"

        if docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
            print_success "NVIDIA Docker runtime working"
        else
            print_failure "NVIDIA Docker runtime not working"
        fi
    else
        print_warning "No NVIDIA GPU detected, skipping GPU tests"
    fi
}

# Test 4: Build CPU image
test_build_cpu() {
    print_test "Test 4: Build CPU Docker Image"

    echo "Building CPU image (this may take several minutes)..."
    if docker build \
        --build-arg BUILD_TYPE=base \
        -t depth_anything_3_ros2:cpu \
        -f Dockerfile . 2>&1 | tee /tmp/docker_build_cpu.log; then
        print_success "CPU image built successfully"
    else
        print_failure "CPU image build failed (see /tmp/docker_build_cpu.log)"
        return 1
    fi
}

# Test 5: Build GPU image
test_build_gpu() {
    print_test "Test 5: Build GPU Docker Image"

    if ! has_nvidia_gpu; then
        print_warning "Skipping GPU build (no NVIDIA GPU detected)"
        return 0
    fi

    echo "Building GPU image (this may take several minutes)..."
    if docker build \
        --build-arg BUILD_TYPE=cuda-base \
        -t depth_anything_3_ros2:gpu \
        -f Dockerfile . 2>&1 | tee /tmp/docker_build_gpu.log; then
        print_success "GPU image built successfully"
    else
        print_failure "GPU image build failed (see /tmp/docker_build_gpu.log)"
        return 1
    fi
}

# Test 6: Test CPU container startup
test_cpu_container_startup() {
    print_test "Test 6: CPU Container Startup"

    if docker run --rm \
        depth_anything_3_ros2:cpu \
        bash -c "echo 'Container started successfully'" >/dev/null 2>&1; then
        print_success "CPU container starts successfully"
    else
        print_failure "CPU container failed to start"
        return 1
    fi
}

# Test 7: Test GPU container startup
test_gpu_container_startup() {
    print_test "Test 7: GPU Container Startup"

    if ! has_nvidia_gpu; then
        print_warning "Skipping GPU container test (no NVIDIA GPU)"
        return 0
    fi

    if docker run --rm --gpus all \
        depth_anything_3_ros2:gpu \
        bash -c "echo 'Container started successfully'" >/dev/null 2>&1; then
        print_success "GPU container starts successfully"
    else
        print_failure "GPU container failed to start"
        return 1
    fi
}

# Test 8: Verify ROS2 installation in CPU container
test_cpu_ros2() {
    print_test "Test 8: ROS2 Installation (CPU)"

    if docker run --rm \
        depth_anything_3_ros2:cpu \
        bash -c "source /opt/ros/humble/setup.bash && ros2 --version" >/dev/null 2>&1; then
        ROS_VERSION=$(docker run --rm depth_anything_3_ros2:cpu bash -c "source /opt/ros/humble/setup.bash && ros2 --version")
        print_success "ROS2 installed: $ROS_VERSION"
    else
        print_failure "ROS2 not working in CPU container"
        return 1
    fi
}

# Test 9: Verify package build in CPU container
test_cpu_package_build() {
    print_test "Test 9: Package Build (CPU)"

    if docker run --rm \
        depth_anything_3_ros2:cpu \
        bash -c "source /ros2_ws/install/setup.bash && ros2 pkg list | grep depth_anything_3_ros2" >/dev/null 2>&1; then
        print_success "depth_anything_3_ros2 package found in CPU container"
    else
        print_failure "depth_anything_3_ros2 package not found in CPU container"
        return 1
    fi
}

# Test 10: Verify Python dependencies in CPU container
test_cpu_python_deps() {
    print_test "Test 10: Python Dependencies (CPU)"

    REQUIRED_PACKAGES="torch transformers opencv-python numpy"
    ALL_INSTALLED=true

    for pkg in $REQUIRED_PACKAGES; do
        if docker run --rm \
            depth_anything_3_ros2:cpu \
            python3 -c "import ${pkg//-/_}" 2>/dev/null; then
            print_success "Python package '$pkg' installed"
        else
            print_failure "Python package '$pkg' not installed"
            ALL_INSTALLED=false
        fi
    done

    if [ "$ALL_INSTALLED" = false ]; then
        return 1
    fi
}

# Test 11: Test node executable in CPU container
test_cpu_node_executable() {
    print_test "Test 11: Node Executable (CPU)"

    if docker run --rm \
        depth_anything_3_ros2:cpu \
        bash -c "source /ros2_ws/install/setup.bash && ros2 run depth_anything_3_ros2 depth_anything_3_node --help" 2>&1 | grep -q "ros2 run"; then
        print_success "Node executable found and runnable"
    else
        print_failure "Node executable not working"
        return 1
    fi
}

# Test 12: Test CUDA availability in GPU container
test_gpu_cuda() {
    print_test "Test 12: CUDA Availability (GPU)"

    if ! has_nvidia_gpu; then
        print_warning "Skipping CUDA test (no NVIDIA GPU)"
        return 0
    fi

    if docker run --rm --gpus all \
        depth_anything_3_ros2:gpu \
        python3 -c "import torch; print(torch.cuda.is_available())" 2>/dev/null | grep -q "True"; then
        GPU_NAME=$(docker run --rm --gpus all depth_anything_3_ros2:gpu python3 -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null)
        print_success "CUDA available in container: $GPU_NAME"
    else
        print_failure "CUDA not available in GPU container"
        return 1
    fi
}

# Test 13: Test model download capability
test_model_download() {
    print_test "Test 13: Model Download Capability"

    echo "Testing model download (this may take a while on first run)..."
    if timeout 300 docker run --rm \
        -e TRANSFORMERS_OFFLINE=0 \
        depth_anything_3_ros2:cpu \
        python3 -c "from transformers import AutoImageProcessor; AutoImageProcessor.from_pretrained('depth-anything/DA3-BASE')" 2>&1 | tee /tmp/model_download.log; then
        print_success "Model download successful"
    else
        print_failure "Model download failed or timed out (see /tmp/model_download.log)"
        return 1
    fi
}

# Test 14: Test Docker Compose
test_docker_compose() {
    print_test "Test 14: Docker Compose Configuration"

    if [ ! -f "docker-compose.yml" ]; then
        print_failure "docker-compose.yml not found"
        return 1
    fi

    # Validate compose file
    if docker compose config >/dev/null 2>&1 || docker-compose config >/dev/null 2>&1; then
        print_success "docker-compose.yml is valid"
    else
        print_failure "docker-compose.yml validation failed"
        return 1
    fi
}

# Test 15: Test volume mounts
test_volume_mounts() {
    print_test "Test 15: Volume Mounts"

    # Create test file
    TEST_DIR="/tmp/depth_test_$$"
    mkdir -p "$TEST_DIR"
    echo "test data" > "$TEST_DIR/test.txt"

    if docker run --rm \
        -v "$TEST_DIR:/test_mount:ro" \
        depth_anything_3_ros2:cpu \
        cat /test_mount/test.txt 2>&1 | grep -q "test data"; then
        print_success "Volume mounts working"
    else
        print_failure "Volume mounts not working"
        rm -rf "$TEST_DIR"
        return 1
    fi

    # Cleanup
    rm -rf "$TEST_DIR"
}

# Test 16: Image size check
test_image_size() {
    print_test "Test 16: Image Size Check"

    CPU_SIZE=$(docker images depth_anything_3_ros2:cpu --format "{{.Size}}")
    print_success "CPU image size: $CPU_SIZE"

    if has_nvidia_gpu; then
        GPU_SIZE=$(docker images depth_anything_3_ros2:gpu --format "{{.Size}}")
        print_success "GPU image size: $GPU_SIZE"
    fi
}

# Cleanup function
cleanup() {
    print_test "Cleanup"

    # Remove temporary files
    rm -f /tmp/docker_build_cpu.log
    rm -f /tmp/docker_build_gpu.log
    rm -f /tmp/model_download.log

    print_success "Cleanup completed"
}

# Main test execution
main() {
    echo ""
    echo "=========================================="
    echo "Depth Anything 3 ROS2 Docker Test Suite"
    echo "=========================================="
    echo ""

    # System checks
    test_docker_installed
    test_docker_compose_installed
    test_nvidia_docker

    # Build tests
    test_build_cpu || { print_warning "Skipping CPU container tests due to build failure"; }
    test_build_gpu || { print_warning "Skipping GPU container tests due to build failure"; }

    # CPU container tests
    if docker images | grep -q "depth_anything_3_ros2.*cpu"; then
        test_cpu_container_startup
        test_cpu_ros2
        test_cpu_package_build
        test_cpu_python_deps
        test_cpu_node_executable
        test_model_download
    fi

    # GPU container tests
    if has_nvidia_gpu && docker images | grep -q "depth_anything_3_ros2.*gpu"; then
        test_gpu_container_startup
        test_gpu_cuda
    fi

    # General tests
    test_docker_compose
    test_volume_mounts
    test_image_size

    # Cleanup
    cleanup

    # Print summary
    print_test "Test Summary"
    echo "Total tests: $TESTS_TOTAL"
    echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
    echo -e "${RED}Failed: $TESTS_FAILED${NC}"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "${RED}Some tests failed.${NC}"
        exit 1
    fi
}

# Run main function
main
