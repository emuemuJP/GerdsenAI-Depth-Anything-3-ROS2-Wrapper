# Validation Checklist

Use this checklist to verify that the Depth Anything 3 ROS2 wrapper is properly installed and functional.

## Installation Validation

### Prerequisites

- [ ] Ubuntu 22.04 LTS installed
- [ ] ROS2 Humble installed and sourced
- [ ] Python 3.10+ available
- [ ] CUDA 12.x installed (optional, for GPU support)

### Dependency Check

```bash
# ROS2 packages
dpkg -l | grep ros-humble-cv-bridge
dpkg -l | grep ros-humble-sensor-msgs
dpkg -l | grep ros-humble-image-transport

# Python packages
python3 -c "import torch; print(f'PyTorch: {torch.__version__}')"
python3 -c "import torchvision; print(f'Torchvision: {torchvision.__version__}')"
python3 -c "import transformers; print(f'Transformers: {transformers.__version__}')"
python3 -c "import cv2; print(f'OpenCV: {cv2.__version__}')"
python3 -c "import numpy; print(f'NumPy: {numpy.__version__}')"

# Depth Anything 3
python3 -c "from depth_anything_3.api import DepthAnything3; print('DA3 installed')"
```

Expected output: All imports should succeed without errors.

### Build Validation

- [ ] Package builds without errors
```bash
cd ~/ros2_ws
colcon build --packages-select depth_anything_3_ros2
```

- [ ] No warnings during build
- [ ] Package is found after sourcing
```bash
source install/setup.bash
ros2 pkg list | grep depth_anything_3_ros2
```

### Test Validation

- [ ] Unit tests pass
```bash
colcon test --packages-select depth_anything_3_ros2
colcon test-result --verbose
```

- [ ] No test failures
- [ ] Test coverage is adequate

## Functionality Validation

### Basic Functionality

- [ ] Node starts without errors
```bash
ros2 run depth_anything_3_ros2 depth_anything_3_node
```

- [ ] Model loads successfully (check terminal output)
- [ ] Topics are advertised
```bash
ros2 topic list | grep depth_anything_3
```

Expected topics:
- `/depth_anything_3/depth`
- `/depth_anything_3/depth_colored`
- `/depth_anything_3/confidence`
- `/depth_anything_3/depth/camera_info`

### Parameter Validation

- [ ] Parameters are listed
```bash
ros2 param list /depth_anything_3
```

- [ ] Parameters can be read
```bash
ros2 param get /depth_anything_3 model_name
ros2 param get /depth_anything_3 device
```

### Camera Integration

- [ ] Works with USB camera (v4l2_camera)
```bash
# Terminal 1
ros2 run v4l2_camera v4l2_camera_node

# Terminal 2
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/image_raw
```

- [ ] Depth images are published
```bash
ros2 topic hz /depth_anything_3/depth
```

- [ ] Frame rate is reasonable (>1 Hz)

### Visualization

- [ ] RViz2 config loads
```bash
rviz2 -d $(ros2 pkg prefix depth_anything_3_ros2)/share/depth_anything_3_ros2/rviz/depth_view.rviz
```

- [ ] Depth visualization displays correctly
- [ ] Colored depth shows reasonable depth gradients
- [ ] No errors in RViz2 console

## Performance Validation

### GPU Mode (if CUDA available)

- [ ] CUDA device is detected
```bash
# Check node output for "Using CUDA device: ..."
ros2 run depth_anything_3_ros2 depth_anything_3_node --ros-args \
  -p device:=cuda -p log_inference_time:=true
```

- [ ] Inference runs on GPU
```bash
# In another terminal, monitor GPU usage
nvidia-smi -l 1
```

- [ ] GPU memory usage is reasonable:
  - DA3-Small: ~1.5 GB
  - DA3-Base: ~2.5 GB
  - DA3-Large: ~4.0 GB
  - DA3-Giant: ~6.5 GB

- [ ] FPS is within expected range (see README benchmarks)

### CPU Fallback

- [ ] CPU mode works
```bash
ros2 run depth_anything_3_ros2 depth_anything_3_node --ros-args \
  -p device:=cpu
```

- [ ] Graceful fallback if CUDA unavailable
- [ ] Inference completes (slower than GPU)

## Code Quality Validation

### Static Analysis

- [ ] No PEP 8 violations
```bash
flake8 depth_anything_3_ros2/ --max-line-length=88
```

- [ ] Type hints are present
```bash
# Check random sample of functions
grep "def.*->" depth_anything_3_ros2/depth_anything_3_ros2/*.py
```

- [ ] No emojis in code
```bash
# This should return nothing
grep -r "[\x{1F600}-\x{1F64F}]" depth_anything_3_ros2/ || echo "No emojis found"
```

### Documentation

- [ ] README is complete
- [ ] All sections filled in
- [ ] Examples are working
- [ ] Credits section present at top
- [ ] Docstrings present in all modules
```bash
python3 -c "import depth_anything_3_ros2.da3_inference; help(depth_anything_3_ros2.da3_inference.DA3InferenceWrapper)"
```

## Multi-Camera Validation

- [ ] Multi-camera launch works
```bash
ros2 launch depth_anything_3_ros2 multi_camera.launch.py
```

- [ ] Multiple nodes start
```bash
ros2 node list | grep depth_anything_3
```

- [ ] Topics are namespaced correctly
```bash
ros2 topic list | grep depth
```

## Error Handling Validation

### Invalid Input Handling

- [ ] Handles missing camera gracefully
```bash
# Start node without camera - should not crash
ros2 run depth_anything_3_ros2 depth_anything_3_node
```

- [ ] Logs appropriate error messages
- [ ] Node stays alive waiting for images

### Resource Limits

- [ ] Handles CUDA OOM gracefully
```bash
# Try to load model too large for GPU
ros2 run depth_anything_3_ros2 depth_anything_3_node --ros-args \
  -p model_name:=depth-anything/DA3-GIANT -p device:=cuda
```

- [ ] Error message is clear
- [ ] Suggests fallback options

### Invalid Parameters

- [ ] Rejects invalid device
```bash
ros2 run depth_anything_3_ros2 depth_anything_3_node --ros-args \
  -p device:=invalid_device
```

- [ ] Rejects invalid model name
- [ ] Provides helpful error messages

## Integration Validation

### Different Cameras

Test with at least 2 different camera types:

- [ ] USB camera (v4l2_camera)
- [ ] Test with image_publisher
- [ ] Optionally: ZED, RealSense, or other cameras

### Different Image Sizes

- [ ] 640x480 (VGA)
- [ ] 1280x720 (HD)
- [ ] 1920x1080 (Full HD)

### Different Encodings

- [ ] BGR8
- [ ] RGB8
- [ ] Conversion between encodings works

## Production Readiness Checklist

- [ ] No crashes during normal operation
- [ ] Graceful shutdown on Ctrl+C
- [ ] No memory leaks in long-running test (>30 minutes)
- [ ] Error messages are informative
- [ ] Performance is acceptable for target application
- [ ] All documentation is complete
- [ ] Tests cover critical paths
- [ ] Code follows style guidelines
- [ ] Camera-agnostic design maintained

## Deployment Checklist

Before deploying to production:

- [ ] Test with actual target camera
- [ ] Measure performance on target hardware
- [ ] Verify GPU memory fits within limits
- [ ] Test failure scenarios
- [ ] Document any hardware-specific settings
- [ ] Create deployment-specific launch files
- [ ] Test recovery from errors
- [ ] Verify logging is appropriate for production

## Sign-off

Validation completed by: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Date: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

System configuration:
- OS: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
- ROS2 Distribution: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
- GPU: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
- CUDA Version: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Notes:
\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
