# Configuration Reference

Complete reference for all parameters, topics, and configuration options.

---

## Launch File Parameters

All parameters can be configured via launch files or command line:

```bash
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  parameter_name:=value
```

### Core Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | string | `depth-anything/DA3-BASE` | Hugging Face model ID or local path |
| `device` | string | `cuda` | Inference device (`cuda` or `cpu`) |
| `cache_dir` | string | `""` | Model cache directory (empty for default) |

### Inference Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `inference_height` | int | `518` | Height for inference (model input) |
| `inference_width` | int | `518` | Width for inference (model input) |
| `input_encoding` | string | `bgr8` | Expected input encoding (`bgr8` or `rgb8`) |
| `normalize_depth` | bool | `true` | Normalize depth to [0, 1] range |

### Output Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `publish_colored` | bool | `true` | Publish colorized depth visualization |
| `publish_confidence` | bool | `true` | Publish confidence map |
| `colormap` | string | `turbo` | Colormap for visualization |

### Performance Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `queue_size` | int | `1` | Subscriber queue size (1 = latest frame only) |
| `log_inference_time` | bool | `false` | Log performance metrics |

---

## Available Models

| Model ID | Parameters | VRAM | Use Case |
|----------|------------|------|----------|
| `depth-anything/DA3-SMALL` | 0.08B | ~1.5GB | Fast inference, real-time robotics |
| `depth-anything/DA3-BASE` | 0.12B | ~2.5GB | Balanced performance (recommended) |
| `depth-anything/DA3-LARGE` | 0.35B | ~4GB | Higher accuracy |
| `depth-anything/DA3-GIANT` | 1.15B | ~6.5GB | Best accuracy, slower |
| `depth-anything/DA3NESTED-GIANT-LARGE` | Combined | ~8GB | Metric scale reconstruction |

### Model Licensing

| Model | License | Commercial Use |
|-------|---------|----------------|
| DA3-SMALL | Apache-2.0 | Yes |
| DA3-BASE | CC-BY-NC-4.0 | No (contact ByteDance) |
| DA3-LARGE | CC-BY-NC-4.0 | No (contact ByteDance) |
| DA3-GIANT | CC-BY-NC-4.0 | No (contact ByteDance) |

---

## Topics

### Subscribed Topics

| Topic | Type | Description |
|-------|------|-------------|
| `~/image_raw` | sensor_msgs/Image | Input RGB image from camera |
| `~/camera_info` | sensor_msgs/CameraInfo | Optional camera intrinsics |

### Published Topics

| Topic | Type | Description |
|-------|------|-------------|
| `~/depth` | sensor_msgs/Image | Depth map (32FC1 encoding, normalized 0-1) |
| `~/depth_colored` | sensor_msgs/Image | Colorized depth (BGR8, for visualization) |
| `~/confidence` | sensor_msgs/Image | Confidence map (32FC1) |
| `~/depth/camera_info` | sensor_msgs/CameraInfo | Camera info for depth image |

### Topic Remapping

Remap topics to match your camera setup:

```bash
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/my_camera/image_raw \
  camera_info_topic:=/my_camera/camera_info
```

---

## Resolution Guidelines

Resolution must be divisible by 14 (ViT patch size). Common presets:

| Preset | Resolution | Use Case |
|--------|------------|----------|
| Low | 308x308 | Fastest, obstacle avoidance, memory-constrained |
| Medium | 518x518 | Balanced speed and detail (default) |
| High | 728x728 | More detail, slower inference |
| Ultra | 1024x1024 | Maximum detail, requires high-end GPU |

### Platform-Specific Recommendations

| Platform | Recommended Resolution | Notes |
|----------|------------------------|-------|
| Orin Nano 4GB/8GB | 308x308 | Memory-constrained |
| Orin NX 8GB | 308x308 | Good balance |
| Orin NX 16GB | 518x518 | Recommended default |
| AGX Orin 32GB/64GB | 518x518 | Can go higher if needed |

---

## Colormap Options

Available colormaps for `colormap` parameter:

| Colormap | Description |
|----------|-------------|
| `turbo` | Rainbow-like, good contrast (default) |
| `viridis` | Perceptually uniform, colorblind-friendly |
| `plasma` | Warm colors, good for presentations |
| `inferno` | Dark to light, high contrast |
| `magma` | Similar to inferno, softer |
| `jet` | Classic rainbow (not recommended) |

---

## Environment Variables

### Docker Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DA3_MODEL` | `depth-anything/DA3-BASE` | HuggingFace model ID |
| `DA3_INFERENCE_HEIGHT` | `518` | Inference height |
| `DA3_INFERENCE_WIDTH` | `518` | Inference width |
| `DA3_VRAM_LIMIT_MB` | (auto) | Override detected VRAM |
| `DA3_DEVICE` | `cuda` | Inference device |
| `DA3_USE_SHARED_MEMORY` | `false` | Use shared memory IPC |

### Hugging Face Environment Variables

| Variable | Description |
|----------|-------------|
| `HF_HOME` | Custom cache directory for models |
| `TRANSFORMERS_CACHE` | Alternative cache directory |
| `HF_HUB_OFFLINE` | Set to `1` for offline mode |

---

## Configuration File Example

Create a YAML file for complex configurations:

```yaml
# my_config.yaml
depth_anything_3:
  ros__parameters:
    # Model
    model_name: "depth-anything/DA3-BASE"
    device: "cuda"

    # Inference
    inference_height: 518
    inference_width: 518
    input_encoding: "bgr8"
    normalize_depth: true

    # Output
    publish_colored: true
    publish_confidence: true
    colormap: "turbo"

    # Performance
    queue_size: 1
    log_inference_time: true
```

Launch with config file:

```bash
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  params_file:=/path/to/my_config.yaml
```

---

## QoS Settings

The node uses these QoS profiles:

### Image Subscriber
- Reliability: BEST_EFFORT (allows frame drops)
- Durability: VOLATILE
- History: KEEP_LAST (depth 1)

### Depth Publisher
- Reliability: RELIABLE
- Durability: VOLATILE
- History: KEEP_LAST (depth 10)

---

## Next Steps

- [Usage Examples](USAGE_EXAMPLES.md) - Practical examples
- [ROS2 Node Reference](ROS2_NODE_REFERENCE.md) - Node lifecycle, QoS, diagnostics
- [Optimization Guide](../OPTIMIZATION_GUIDE.md) - Performance tuning
- [Jetson Deployment](JETSON_DEPLOYMENT_GUIDE.md) - TensorRT setup
