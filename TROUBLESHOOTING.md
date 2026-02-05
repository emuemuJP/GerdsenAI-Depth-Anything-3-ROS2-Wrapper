# Troubleshooting Guide

Common issues and solutions for the Depth Anything 3 ROS2 Wrapper.

---

## Quick Diagnostics

```bash
# Check if package is installed
ros2 pkg list | grep depth_anything_3_ros2

# Check if topics are publishing
ros2 topic list | grep depth_anything_3

# Check topic frequency
ros2 topic hz /depth_anything_3/depth

# Check GPU status
nvidia-smi
```

---

## Model Issues

### 1. Model Download Failures

**Error**: `Failed to load model from Hugging Face Hub` or `Connection timeout`

**Solutions**:
- Check internet connection: `ping huggingface.co`
- Verify Hugging Face Hub is accessible (may be blocked by firewall/proxy)
- Pre-download models manually:
  ```bash
  python3 -c "from transformers import AutoImageProcessor, AutoModelForDepthEstimation; \
              AutoImageProcessor.from_pretrained('depth-anything/DA3-BASE'); \
              AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')"
  ```
- Use custom cache directory: Set `HF_HOME=/path/to/models` environment variable
- For offline robots: See [Offline Operation](docs/INSTALLATION.md#offline-operation)

### 2. Model Not Found on Offline Robot

**Error**: `Model depth-anything/DA3-BASE not found` on robot without internet

**Solution**: Pre-download models and copy cache directory:
```bash
# On development machine WITH internet:
python3 -c "from transformers import AutoModelForDepthEstimation; \
            AutoModelForDepthEstimation.from_pretrained('depth-anything/DA3-BASE')"
tar -czf da3_models.tar.gz -C ~/.cache/huggingface .

# Transfer to robot (USB, SCP, etc.) and extract:
mkdir -p ~/.cache/huggingface
tar -xzf da3_models.tar.gz -C ~/.cache/huggingface/
```

Verify models are available:
```bash
ls ~/.cache/huggingface/hub/models--depth-anything--*
```

---

## GPU/CUDA Issues

### 3. CUDA Out of Memory

**Error**: `RuntimeError: CUDA out of memory`

**Solutions**:
- Use a smaller model:
  ```bash
  ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py \
    model_name:=depth-anything/DA3-SMALL
  ```
- Reduce input resolution
- Close other GPU applications
- Switch to CPU mode temporarily:
  ```bash
  ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py device:=cpu
  ```

### 4. CUDA Device Not Found

**Error**: `CUDA not available` or `No CUDA GPUs are available`

**Solutions**:
- Verify CUDA installation: `nvidia-smi`
- Check PyTorch CUDA: `python3 -c "import torch; print(torch.cuda.is_available())"`
- Reinstall PyTorch with CUDA support
- For Docker: ensure `--runtime=nvidia` and `--gpus all` flags are set

---

## Image/Camera Issues

### 5. Image Encoding Mismatches

**Error**: `CV Bridge conversion failed`

**Solutions**:
- Check camera's output encoding
- Adjust `input_encoding` parameter:
  ```bash
  # For RGB cameras
  --param input_encoding:=rgb8

  # For BGR cameras (most common)
  --param input_encoding:=bgr8
  ```

### 6. No Image Received

**Solutions**:
- Verify camera is publishing: `ros2 topic echo /camera/image_raw`
- Check topic remapping is correct
- Verify QoS settings match camera

```bash
# List available topics
ros2 topic list | grep image

# Check topic info
ros2 topic info /camera/image_raw
```

---

## Performance Issues

### 7. Low Frame Rate

**Solutions**:
- Check GPU utilization: `nvidia-smi`
- Enable performance logging:
  ```bash
  --param log_inference_time:=true
  ```
- Use smaller model (DA3-Small)
- Reduce input resolution:
  ```bash
  --param inference_height:=308 inference_width:=308
  ```
- Disable unused outputs:
  ```bash
  --param publish_colored_depth:=false --param publish_confidence:=false
  ```

### 8. FPS Below 30 on Jetson

**Check 1: Verify TensorRT backend**
```bash
# Should see "Backend: tensorrt" in console output
# If seeing "Backend: pytorch", TensorRT model not loaded
```

**Check 2: Verify TRT service is running**
```bash
# Check shared memory directory
ls -la /dev/shm/da3/
cat /dev/shm/da3/status
```

**Check 3: Check GPU utilization**
```bash
watch -n 1 nvidia-smi
# GPU utilization should be 80-95%
```

---

## Jetson/Docker Issues

### 9. Jetson Docker Build Failures

**Error**: `dustynv/ros:humble-pytorch-l4t-r36.x.x` not found

**Solution**: The humble-pytorch variant doesn't exist for L4T r36.x. Use `humble-desktop` instead:
```dockerfile
# In docker-compose.yml, set:
L4T_VERSION: r36.4.0  # Uses humble-desktop variant
```

**Error**: `pip install` fails with connection errors to `jetson.webredirect.org`

**Solution**: The dustynv base images configure pip to use an unreliable custom index. The Dockerfile includes `--index-url https://pypi.org/simple/` to override this.

**Error**: `ImportError: libcudnn.so.8: cannot open shared object file`

**Solution**: L4T r36.4.0 ships with cuDNN 9.x, but some PyTorch wheels expect cuDNN 8. For the host-container TRT architecture, the container doesn't need CUDA-accelerated PyTorch since TensorRT inference runs on the host.

### 10. TensorRT Engine Build Fails

```bash
# Check TensorRT and pycuda installation
python3 -c "import tensorrt; print(f'TensorRT {tensorrt.__version__}')"
python3 -c "import pycuda.driver; print('pycuda OK')"

# Verify trtexec is available
which trtexec || ls /usr/src/tensorrt/bin/trtexec

# Verify TensorRT libraries
ls /usr/lib/aarch64-linux-gnu/libnvinfer*

# Try building with verbose output
python3 scripts/build_tensorrt_engine.py --auto --verbose
```

### 11. Container Can't Access Camera

**Solutions**:
- Ensure privileged mode: `--privileged`
- Mount /dev: `-v /dev:/dev:rw`
- Add video group: `--group-add video`
- Check camera device permissions: `ls -la /dev/video*`

---

## ROS2 Issues

### 12. Topics Not Publishing

**Solutions**:
- Check node is running: `ros2 node list`
- Check if subscribed to input: `ros2 topic info /camera/image_raw`
- Verify QoS compatibility between publisher and subscriber

### 13. RViz2 Not Showing Images

**Solutions**:
- Check topic is publishing: `ros2 topic hz /depth_anything_3/depth_colored`
- Verify image encoding is supported
- Check RViz2 display configuration
- Try `rqt_image_view` as alternative

---

## Getting Help

If your issue isn't listed here:

1. Check the logs:
   ```bash
   # Demo logs
   cat /tmp/da3_demo_logs/*.log

   # TRT service logs
   cat /tmp/trt_service.log
   ```

2. Open a GitHub issue with:
   - Error message
   - System info (OS, ROS2 version, GPU, JetPack version if Jetson)
   - Steps to reproduce

- **Issues**: [GitHub Issues](https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper/issues)
- **Discussions**: [GitHub Discussions](https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper/discussions)
