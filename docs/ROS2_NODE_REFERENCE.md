# ROS2 Node Reference

Complete reference for the Depth Anything 3 ROS2 node behavior, diagnostics, and performance tuning.

---

## Node Overview

**Node Name**: `depth_anything_3`
**Package**: `depth_anything_3_ros2`
**Executable**: `depth_anything_3_node`

```bash
# Basic launch
ros2 run depth_anything_3_ros2 depth_anything_3_node

# With parameters
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  image_topic:=/camera/image_raw
```

---

## Node Lifecycle

### Initialization Sequence

1. **Parameter Declaration** - All ROS2 parameters declared with defaults
2. **Backend Selection** (in order of preference):
   - `SharedMemoryInferenceFast` - If `/dev/shm/da3/status` exists (production)
   - `SharedMemoryInference` - If `/tmp/da3_shared/status` exists (fallback)
   - `DA3InferenceWrapper` - PyTorch fallback (development only)
3. **Publisher Creation** - Depth, colored depth, confidence, camera_info
4. **Subscriber Creation** - Image and optional camera_info
5. **Ready State** - Node begins processing frames

### Backend Selection Logic

```
use_shared_memory=true?
    |
    +-- YES --> /dev/shm/da3/status exists?
    |               |
    |               +-- YES --> SharedMemoryInferenceFast (43+ FPS)
    |               |
    |               +-- NO --> /tmp/da3_shared/status exists?
    |                              |
    |                              +-- YES --> SharedMemoryInference (~11 FPS)
    |                              |
    |                              +-- NO --> DA3InferenceWrapper (PyTorch, ~5 FPS)
    |
    +-- NO --> DA3InferenceWrapper (PyTorch, ~5 FPS)
```

### Graceful Shutdown

The node handles `SIGINT` (Ctrl+C) gracefully:
- Stops accepting new frames
- Completes current inference (if any)
- Releases GPU memory
- Closes publishers/subscribers

---

## Topics

### Subscribed Topics

| Topic | Type | QoS | Description |
|-------|------|-----|-------------|
| `~/image_raw` | sensor_msgs/Image | BEST_EFFORT | Input RGB/BGR image |
| `~/camera_info` | sensor_msgs/CameraInfo | BEST_EFFORT | Optional camera intrinsics |

### Published Topics

| Topic | Type | QoS | Description |
|-------|------|-----|-------------|
| `~/depth` | sensor_msgs/Image | RELIABLE | Depth map (32FC1, normalized 0-1) |
| `~/depth_colored` | sensor_msgs/Image | RELIABLE | Colorized visualization (BGR8) |
| `~/confidence` | sensor_msgs/Image | RELIABLE | Confidence map (32FC1, 0-1) |
| `~/depth/camera_info` | sensor_msgs/CameraInfo | RELIABLE | Depth image camera info |

### Message Format Details

**Depth Map (`~/depth`)**:
- Encoding: `32FC1` (32-bit float, single channel)
- Range: 0.0 to 1.0 (normalized relative depth)
- 0.0 = closest, 1.0 = farthest
- Frame ID: Inherited from input image

**Colored Depth (`~/depth_colored`)**:
- Encoding: `bgr8`
- Colormap: Configurable (default: `turbo`)
- For visualization only, not metric depth

**Confidence Map (`~/confidence`)**:
- Encoding: `32FC1`
- Range: 0.0 to 1.0
- Higher values = more confident depth estimate

---

## QoS Configuration

### Why These Settings?

**Image Subscriber (BEST_EFFORT)**:
- Cameras often publish at high rates (30-60 FPS)
- Missing occasional frames is acceptable
- Avoids subscriber queue backup
- Matches common camera driver QoS

**Depth Publisher (RELIABLE)**:
- Downstream nodes expect every depth frame
- Important for mapping/navigation pipelines
- Queue depth of 10 allows brief subscriber delays

### Overriding QoS

If your camera uses different QoS, remap or use a bridge:

```bash
# Example: Force RELIABLE subscription for recorded bags
ros2 run depth_anything_3_ros2 depth_anything_3_node \
  --ros-args -p qos_overrides./image_raw.reliability:=reliable
```

### QoS Compatibility Matrix

| Camera Driver | Default QoS | Compatible? |
|---------------|-------------|-------------|
| v4l2_camera | BEST_EFFORT | Yes |
| realsense2_camera | BEST_EFFORT | Yes |
| zed_wrapper | BEST_EFFORT | Yes |
| image_publisher | RELIABLE | Yes (auto-matched) |
| rosbag2 play | RELIABLE | Yes (auto-matched) |

---

## Parameters

### Core Parameters

| Parameter | Type | Default | Dynamic | Description |
|-----------|------|---------|---------|-------------|
| `model_name` | string | `depth-anything/DA3-BASE` | No | HuggingFace model ID |
| `device` | string | `cuda` | No | `cuda` or `cpu` |
| `use_shared_memory` | bool | `false` | No | Enable TensorRT IPC |

### Inference Parameters

| Parameter | Type | Default | Dynamic | Description |
|-----------|------|---------|---------|-------------|
| `inference_height` | int | `518` | No | Model input height |
| `inference_width` | int | `518` | No | Model input width |
| `input_encoding` | string | `bgr8` | No | Expected input format |
| `normalize_depth` | bool | `true` | Yes | Normalize output to 0-1 |

### Output Parameters

| Parameter | Type | Default | Dynamic | Description |
|-----------|------|---------|---------|-------------|
| `publish_colored` | bool | `true` | Yes | Publish colorized depth |
| `publish_confidence` | bool | `true` | Yes | Publish confidence map |
| `colormap` | string | `turbo` | Yes | Visualization colormap |

### Performance Parameters

| Parameter | Type | Default | Dynamic | Description |
|-----------|------|---------|---------|-------------|
| `queue_size` | int | `1` | No | Subscriber queue (1=latest only) |
| `log_inference_time` | bool | `false` | Yes | Enable performance logging |

**Dynamic Parameters**: Can be changed at runtime via `ros2 param set`

---

## Performance Logging

Enable with `log_inference_time:=true`:

```
[depth_anything_3]: Performance - FPS: 23.4, Inference: 15.2ms, IPC: 8.1ms, Total: 23.3ms
[depth_anything_3]: Backend: SharedMemoryInferenceFast, Frames: 1024
```

### Metrics Explained

| Metric | Description | Target (Orin NX 16GB) |
|--------|-------------|----------------------|
| FPS | Frames processed per second | 23+ (camera limited) |
| Inference | TensorRT engine time | ~15ms |
| IPC | Shared memory overhead | ~8ms |
| Total | End-to-end frame time | ~23ms |

---

## Jetson Performance Tuning

### Power Modes

Jetson devices have multiple power modes. Use MAXN for best inference performance:

```bash
# Check current mode
sudo nvpmodel -q

# Set to MAXN (maximum performance)
sudo nvpmodel -m 0

# Common modes:
# Mode 0: MAXN (all cores, max clocks) - RECOMMENDED
# Mode 1: 15W (power limited)
# Mode 2: 10W (power limited)
```

### Clock Frequencies

Lock clocks to maximum for consistent performance:

```bash
# Enable max clocks (jetson_clocks)
sudo jetson_clocks

# Check current clocks
sudo jetson_clocks --show

# Store current settings (to restore later)
sudo jetson_clocks --store

# Restore original settings
sudo jetson_clocks --restore
```

**Clock targets for Orin NX 16GB:**
- GPU: 918 MHz (max)
- EMC (memory): 3199 MHz
- CPU: 2035 MHz per core

### Thermal Monitoring

Monitor temperatures to detect throttling:

```bash
# Real-time thermal monitoring
watch -n 1 cat /sys/devices/virtual/thermal/thermal_zone*/temp

# Or use tegrastats
tegrastats --interval 1000

# Output example:
# RAM 4321/15830MB | CPU [45%@2035,42%@2035,...] | GPU 38%@918 | Temp CPU@42C GPU@40.5C
```

**Thermal thresholds (Orin NX):**
- Normal: < 50C
- Warm: 50-70C (OK for sustained load)
- Throttling: > 70C (clocks may reduce)
- Critical: > 85C (automatic shutdown)

### Performance Monitoring Script

Use the included monitor:

```bash
# From repo root
bash scripts/performance_monitor.sh
```

Output:
```
========================================
  Depth Anything V3 - Performance
========================================

TensorRT Inference Service
----------------------------------------
  Status:     Running
  FPS:        43.1
  Latency:    23.2 ms
  Frames:     1024

GPU Resources
----------------------------------------
  GPU Usage:  45%
  GPU Memory: 1843 / 15360 MB
  GPU Temp:   42C

Power Mode
----------------------------------------
  NV Model:   MAXN
  Clocks:     Locked (jetson_clocks active)
```

### Thermal Management Tips

1. **Ensure adequate cooling**:
   - Use heatsink with fan
   - Ensure airflow is not blocked
   - Consider active cooling for sustained loads

2. **Monitor during benchmarks**:
   ```bash
   # Run tegrastats alongside your workload
   tegrastats --interval 1000 --logfile thermal.log &
   ./run.sh
   ```

3. **Reduce power if overheating**:
   ```bash
   # Switch to 15W mode if thermal throttling
   sudo nvpmodel -m 1
   ```

---

## Shared Memory IPC Details

### File Locations

**Fast IPC (Production)**:
```
/dev/shm/da3/
  input.bin    # Input tensor (numpy memmap)
  output.bin   # Output depth (numpy memmap)
  request      # Timestamp signal
  status       # "ready", "complete:<time>", "error:<msg>"
```

**File-based IPC (Fallback)**:
```
/tmp/da3_shared/
  input.npy    # Input tensor (numpy file)
  output.npy   # Output depth (numpy file)
  request      # Timestamp signal
  status       # Status string
```

### Status File Protocol

The node polls the status file to coordinate with the host TRT service:

| Status | Meaning | Node Action |
|--------|---------|-------------|
| `ready` | Service idle, waiting for input | Write input, set request |
| `complete:<time>` | Inference done | Read output, publish depth |
| `error:<msg>` | Service error | Log error, skip frame |

### Debugging IPC Issues

```bash
# Check if TRT service is running
cat /dev/shm/da3/status

# Monitor IPC activity
watch -n 0.5 'ls -la /dev/shm/da3/'

# Check TRT service logs
cat /tmp/trt_service.log

# Verify shared memory permissions
ls -la /dev/shm/da3/
# Should show read/write for all users
```

---

## Error Handling

### Common Log Messages

| Message | Cause | Solution |
|---------|-------|----------|
| `Waiting for TRT service...` | Status file not found | Start TRT service with `./run.sh` |
| `IPC timeout after Xms` | TRT service too slow | Check GPU load, thermal throttling |
| `Failed to load model` | Model not cached | Check internet, run model download |
| `CUDA out of memory` | Model too large | Use smaller model or resolution |
| `No image received` | Topic not publishing | Check camera, topic remapping |

### Recovery Behavior

- **IPC Timeout**: Node continues, skips frame, retries next frame
- **Service Crash**: Node detects missing status, waits for restart
- **GPU OOM**: Node fails to initialize, logs error, exits

---

## Multi-Node Deployment

### Namespacing

```bash
# Launch multiple instances with namespaces
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  namespace:=cam_front image_topic:=/cam_front/image_raw &

ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
  namespace:=cam_rear image_topic:=/cam_rear/image_raw &
```

### Resource Considerations

| Cameras | Recommended Backend | Notes |
|---------|---------------------|-------|
| 1 | SharedMemoryInferenceFast | Full 43+ FPS capacity |
| 2 | SharedMemoryInferenceFast | ~20 FPS each (shared GPU) |
| 3+ | Consider queue or load balance | GPU may bottleneck |

---

## Integration with ROS2 Tools

### Visualization

```bash
# RViz2 with preset config
rviz2 -d $(ros2 pkg prefix depth_anything_3_ros2)/share/depth_anything_3_ros2/rviz/depth_view.rviz

# rqt_image_view for quick check
ros2 run rqt_image_view rqt_image_view /depth_anything_3/depth_colored
```

### Recording

```bash
# Record depth output
ros2 bag record /depth_anything_3/depth /depth_anything_3/depth_colored

# Record with compression
ros2 bag record -o depth_bag --compression-mode file \
  /depth_anything_3/depth /camera/image_raw
```

### Diagnostics

```bash
# Check node status
ros2 node info /depth_anything_3

# List parameters
ros2 param list /depth_anything_3

# Get specific parameter
ros2 param get /depth_anything_3 model_name

# Monitor topic rates
ros2 topic hz /depth_anything_3/depth
```

---

## Quick Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| 0 FPS | `ros2 topic hz ~/image_raw` | Verify camera publishing |
| ~5 FPS | Backend type in logs | Enable shared memory, start TRT |
| ~11 FPS | IPC path in logs | Use `/dev/shm` not `/tmp` |
| Inconsistent FPS | `tegrastats` | Check thermal throttling |
| High latency | Power mode | Set MAXN, run jetson_clocks |

See [Troubleshooting Guide](../TROUBLESHOOTING.md) for detailed solutions.

---

## Next Steps

- [Configuration Reference](CONFIGURATION.md) - All parameters and topics
- [Jetson Deployment Guide](JETSON_DEPLOYMENT_GUIDE.md) - TensorRT setup
- [Optimization Guide](../OPTIMIZATION_GUIDE.md) - Platform benchmarks
- [Troubleshooting](../TROUBLESHOOTING.md) - Common issues and fixes
