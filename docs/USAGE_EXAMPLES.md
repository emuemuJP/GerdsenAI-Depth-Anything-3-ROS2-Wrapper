# Usage Examples

Comprehensive examples for using the Depth Anything 3 ROS2 Wrapper with different cameras and configurations.

---

## Quick Reference

| Example | Use Case | Command |
|---------|----------|---------|
| USB Camera | Generic webcam | `ros2 launch depth_anything_3_ros2 usb_camera_example.launch.py` |
| Static Image | Testing without camera | `ros2 launch depth_anything_3_ros2 image_publisher_test.launch.py` |
| ZED Camera | Stereo camera | See [ZED Camera](#example-2-zed-stereo-camera) |
| RealSense | Intel depth camera | See [RealSense](#example-3-intel-realsense-camera) |
| Multi-Camera | Multiple cameras | See [Multi-Camera](#example-4-multi-camera-setup) |

---

## Example 1: Generic USB Camera (v4l2_camera)

Complete example with a standard USB webcam:

```bash
# Install v4l2_camera if not already installed
sudo apt install ros-humble-v4l2-camera

# Option A: Use the provided launch file
ros2 launch depth_anything_3_ros2 usb_camera_example.launch.py \
  video_device:=/dev/video0 \
  model_name:=depth-anything/DA3-BASE

# Option B: Launch components separately
# Terminal 1: Camera driver
ros2 run v4l2_camera v4l2_camera_node --ros-args \
  -p image_size:="[640,480]" \
  -r __ns:=/camera

# Terminal 2: Depth estimation
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw \
  model_name:=depth-anything/DA3-BASE \
  device:=cuda

# Terminal 3: Visualization
rviz2 -d $(ros2 pkg prefix depth_anything_3_ros2)/share/depth_anything_3_ros2/rviz/depth_view.rviz
```

---

## Example 2: ZED Stereo Camera

Connect to a ZED camera (requires separate ZED ROS2 wrapper installation):

```bash
# Launch ZED camera separately
ros2 launch zed_wrapper zed_camera.launch.py camera_model:=zedxm

# In another terminal, launch depth estimation with topic remapping
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/zed/zed_node/rgb/image_rect_color \
  camera_info_topic:=/zed/zed_node/rgb/camera_info

# Or use the provided example
ros2 launch depth_anything_3_ros2 zed_camera_example.launch.py \
  camera_model:=zedxm
```

---

## Example 3: Intel RealSense Camera

Connect to a RealSense camera (requires realsense-ros):

```bash
# Install RealSense ROS2 wrapper
sudo apt install ros-humble-realsense2-camera

# Launch RealSense camera
ros2 launch realsense2_camera rs_launch.py

# Launch depth estimation
ros2 launch depth_anything_3_ros2 realsense_example.launch.py
```

---

## Example 4: Multi-Camera Setup

Run depth estimation on multiple cameras simultaneously:

```bash
# Launch multi-camera setup (4 cameras)
ros2 launch depth_anything_3_ros2 multi_camera.launch.py \
  camera_namespaces:="cam1,cam2,cam3,cam4" \
  image_topics:="/cam1/image_raw,/cam2/image_raw,/cam3/image_raw,/cam4/image_raw" \
  model_name:=depth-anything/DA3-BASE
```

Each camera gets its own namespaced depth topics:
- `/cam1/depth_anything_3/depth`
- `/cam2/depth_anything_3/depth`
- etc.

---

## Example 5: Testing with Static Images

Test with a static image using image_publisher (no camera required):

```bash
# Install image_publisher
sudo apt install ros-humble-image-publisher

# Launch with test image
ros2 launch depth_anything_3_ros2 image_publisher_test.launch.py \
  image_path:=/path/to/test_image.jpg \
  model_name:=depth-anything/DA3-BASE
```

---

## Example 6: Different Models

Switch between models for different performance/accuracy tradeoffs:

```bash
# Fast inference (DA3-Small) - Best for real-time robotics
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  model_name:=depth-anything/DA3-SMALL \
  image_topic:=/camera/image_raw

# Balanced (DA3-Base) - Good accuracy and speed
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  model_name:=depth-anything/DA3-BASE \
  image_topic:=/camera/image_raw

# Best accuracy (DA3-Large) - Requires more GPU memory
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  model_name:=depth-anything/DA3-LARGE \
  image_topic:=/camera/image_raw
```

---

## Example 7: CPU-Only Mode

For development or testing on systems without CUDA. **Not recommended for production** - use TensorRT on Jetson for real-time performance:

```bash
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw \
  model_name:=depth-anything/DA3-BASE \
  device:=cpu
```

> **Note**: CPU mode runs at ~1-2 FPS. For production deployment, use the TensorRT host-container architecture via `./run.sh`.

---

## Example 8: Custom Configuration

Use a custom parameter file for complex setups:

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
    inference_height: 518
    inference_width: 518
EOF

# Launch with custom config
ros2 run depth_anything_3_ros2 depth_anything_3_node --ros-args \
  --params-file my_config.yaml \
  -r ~/image_raw:=/camera/image_raw
```

---

## Jetson TensorRT Demo

For Jetson users, the one-click demo handles everything:

```bash
cd ~/depth_anything_3_ros2
./run.sh                           # Auto-detect camera
./run.sh --camera /dev/video0      # Specify camera
./run.sh --no-display              # Headless mode (SSH)
```

See [Jetson Deployment Guide](JETSON_DEPLOYMENT_GUIDE.md) for details.

---

## Advanced: Batch Processing ROS2 Bags

Process recorded ROS2 bags through depth estimation:

```bash
./scripts/ros2_batch_process.sh \
  -i ./raw_bags \
  -o ./depth_bags \
  -m depth-anything/DA3-BASE \
  -d cuda
```

---

## Advanced: Performance Profiling

Profile ROS2 node performance:

```bash
python3 examples/scripts/profile_node.py \
  --model depth-anything/DA3-BASE \
  --device cuda \
  --duration 60
```

---

## Topic Reference

### Subscribed Topics

| Topic | Type | Description |
|-------|------|-------------|
| `~/image_raw` | sensor_msgs/Image | Input RGB image from camera |
| `~/camera_info` | sensor_msgs/CameraInfo | Optional camera intrinsics |

### Published Topics

| Topic | Type | Description |
|-------|------|-------------|
| `~/depth` | sensor_msgs/Image | Depth map (32FC1 encoding) |
| `~/depth_colored` | sensor_msgs/Image | Colorized depth visualization (BGR8) |
| `~/confidence` | sensor_msgs/Image | Confidence map (32FC1) |
| `~/depth/camera_info` | sensor_msgs/CameraInfo | Camera info for depth image |

---

## Next Steps

- [Configuration Reference](CONFIGURATION.md) - All parameters explained
- [ROS2 Node Reference](ROS2_NODE_REFERENCE.md) - Node lifecycle, Jetson tuning
- [Optimization Guide](../OPTIMIZATION_GUIDE.md) - Performance tuning
- [Troubleshooting](../TROUBLESHOOTING.md) - Common issues
