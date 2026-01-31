# Jetson Deployment & TensorRT Validation Guide

**Platform:** NVIDIA Jetson Orin NX 16GB  
**Goal:** Achieve >20 FPS (target: >30 FPS) with TensorRT FP16  
**Execution Time:** ~30-60 minutes  
**Date:** 2026-01-30

---

## Quick Start (Copy-Paste Commands)

On your **Jetson Orin NX 16GB**, execute these commands in sequence:

### Step 1: Clone Repository (if not already on Jetson)

```bash
# Skip if already cloned
cd ~
git clone https://github.com/YourUsername/GerdsenAI-Depth-Anything-3-ROS2-Wrapper.git
cd GerdsenAI-Depth-Anything-3-ROS2-Wrapper
```

### Step 2: Build and Run with Automatic TensorRT

```bash
# This single command will:
# 1. Build the Docker image for Jetson
# 2. Auto-detect platform (Orin NX 16GB)
# 3. Download ONNX model from onnx-community
# 4. Build TensorRT FP16 engine at 518x518
# 5. Start the container

DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson
```

**Expected Output:**
```
[TensorRT] Validating TensorRT availability...
TensorRT 8.6.x available
[TensorRT] No engines found in /root/.cache/tensorrt
[TensorRT] Building TensorRT engine automatically...

Detected Platform: Jetson Orin NX 16GB

Recommended settings for ORIN_NX_16GB:
  Precision: fp16
  Resolution: 518x518
  Workspace: 2048 MB

Downloading ONNX model: Depth Anything 3 Small
  Repository: onnx-community/depth-anything-v3-small
  Downloaded: /root/.cache/onnx/onnx/model.onnx

Running trtexec...
Building TensorRT engine:
  ONNX model: /root/.cache/onnx/onnx/model.onnx
  Output: /root/.cache/tensorrt/da3-small_fp16_518x518_ORIN_NX_16GB.engine
  Precision: fp16
  Resolution: 518x518
  Workspace: 2048 MB

[...trtexec build logs...]

Engine built successfully: /root/.cache/tensorrt/da3-small_fp16_518x518_ORIN_NX_16GB.engine
  Size: 89.45 MB
```

**Build Time:** 5-10 minutes (one-time only, subsequent runs are instant)

---

## Phase 1: Environment Validation

### 1.1 Verify TensorRT Environment

Once the container is running, open a new terminal and exec into it:

```bash
# Terminal 2
docker exec -it da3_ros2_jetson bash
```

Inside the container, run these validation commands:

```bash
# Check TensorRT version
python3 -c "import tensorrt; print(f'TensorRT {tensorrt.__version__}')"
# Expected: TensorRT 8.6.x

# Check trtexec availability
which trtexec
# Expected: /usr/src/tensorrt/bin/trtexec

# Confirm JetPack version
cat /etc/nv_tegra_release
# Expected: R36 (JetPack 6.x)

# Verify engine was built
ls -lh /root/.cache/tensorrt/*.engine
# Expected: da3-small_fp16_518x518_ORIN_NX_16GB.engine (~90MB)
```

**Checkpoint 1:** All commands should succeed without errors.

### 1.2 Start the Depth Node

In the container terminal:

```bash
# Source ROS2 environment
source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash

# Launch the optimized node with TensorRT backend
ros2 launch depth_anything_3_ros2 depth_anything_3_optimized.launch.py \
  backend:=tensorrt_native \
  trt_model_path:=/root/.cache/tensorrt/da3-small_fp16_518x518_ORIN_NX_16GB.engine \
  log_inference_time:=true
```

**Expected Output:**
```
[depth_anything_3_optimized]: Node started
[depth_anything_3_optimized]: Backend: tensorrt_native
[depth_anything_3_optimized]: Model: /root/.cache/tensorrt/da3-small_fp16_518x518_ORIN_NX_16GB.engine
[depth_anything_3_optimized]: Input resolution: 518x518
[depth_anything_3_optimized]: Precision: FP16
[depth_anything_3_optimized]: Waiting for image messages...
```

**Checkpoint 2:** Node should start without TensorRT errors.

### 1.3 Measure Performance (No Camera Yet)

In another terminal on the Jetson:

```bash
# Terminal 3: Monitor topic publishing rate
ros2 topic hz /depth_anything_3/depth
```

If you have a camera already running, you should see:
```
average rate: 24.532
	min: 0.038s max: 0.043s std dev: 0.00189s window: 100
```

**If no camera is connected yet, proceed to Phase 1.4 below.**

### 1.4 Connect a Test Camera

```bash
# Terminal 4: Start USB camera
ros2 run v4l2_camera v4l2_camera_node --ros-args \
  -p video_device:="/dev/video0" \
  -p image_size:="[640,480]" \
  -p pixel_format:="MJPEG" \
  -r __ns:=/camera &

# Wait 2 seconds, then check FPS again in Terminal 3
```

**Expected FPS Range:**
- **518x518 Resolution:** 18-25 FPS (conservative), 25-30 FPS (optimistic)
- **If <18 FPS:** Proceed to Phase 2 (Resolution Tuning)
- **If >20 FPS:** SUCCESS! Proceed to Phase 3 (Thermal Validation)

---

## Phase 2: Performance Measurement and Optimization

### 2.1 Detailed Performance Metrics

Monitor all performance indicators simultaneously:

```bash
# Terminal 1: Node output (watch for inference time logs)
# Already running from Phase 1.2

# Terminal 2: Topic rate
ros2 topic hz /depth_anything_3/depth

# Terminal 3: GPU utilization
watch -n 1 nvidia-smi

# Terminal 4: Thermal monitoring
tegrastats --interval 1000
```

### 2.2 Expected Performance Breakdown

**TensorRT FP16 @ 518x518 on Orin NX 16GB:**
```
Preprocessing:     ~3ms  (GPU resize)
TensorRT Inference: ~20ms (FP16 on 518x518)
Postprocessing:    ~4ms  (GPU operations)
ROS2 Publishing:   ~2ms  (message conversion)
──────────────────────────
Total:            ~29ms = 34.5 FPS (theoretical)
Actual observed:  25-30 FPS (with overhead)
```

### 2.3 Decision Tree Based on FPS

**Scenario A: Achieved >25 FPS**
- **EXCELLENT!** Exceeded target
- Document actual FPS in TODO.md
- Proceed to Phase 3 (Thermal Validation)

**Scenario B: Achieved 20-25 FPS**
- **SUCCESS!** Met minimum target
- Proceed to Phase 3 (Thermal Validation)
- Consider Phase 2.4 for further optimization

**Scenario C: Achieved 15-20 FPS**
- **BORDERLINE** - Try resolution tuning
- Proceed to Phase 2.4 (Resolution Tuning)

**Scenario D: Achieved <15 FPS**
- **INVESTIGATE** - Unexpected, check for issues
- Verify TensorRT engine loaded correctly
- Check GPU throttling (tegrastats)
- Proceed to Phase 2.4 mandatory

### 2.4 Resolution Tuning (If FPS < 25)

Try intermediate resolutions to find the sweet spot:

```bash
# Stop the current node (Ctrl+C in Terminal 1)

# Build 400x400 engine (custom resolution)
python3 /app/scripts/build_tensorrt_engine.py \
  --model da3-small \
  --precision fp16 \
  --resolution 400 \
  --output-dir /root/.cache

# Launch with new engine
ros2 launch depth_anything_3_ros2 depth_anything_3_optimized.launch.py \
  backend:=tensorrt_native \
  trt_model_path:=/root/.cache/tensorrt/da3-small_fp16_400x400_ORIN_NX_16GB.engine \
  log_inference_time:=true
```

**Expected FPS @ 400x400:** 28-35 FPS

If still <25 FPS, drop to 308x308:

```bash
# Build 308x308 engine (minimum recommended)
python3 /app/scripts/build_tensorrt_engine.py \
  --model da3-small \
  --precision fp16 \
  --resolution 308 \
  --output-dir /root/.cache

# Launch
ros2 launch depth_anything_3_ros2 depth_anything_3_optimized.launch.py \
  backend:=tensorrt_native \
  trt_model_path:=/root/.cache/tensorrt/da3-small_fp16_308x308_ORIN_NX_16GB.engine \
  log_inference_time:=true
```

**Expected FPS @ 308x308:** 40-50 FPS (guaranteed)

---

## Phase 3: Thermal and Stability Validation

### 3.1 Install Monitoring Tools (If Not Installed)

```bash
# Exit container temporarily
exit

# Install on Jetson host
sudo apt update
sudo apt install -y python3-pip
sudo pip3 install jetson-stats

# Restart jtop service
sudo systemctl restart jetson_stats.service
```

### 3.2 Sustained Load Test (10 Minutes)

```bash
# Terminal 1: Start jtop monitoring
sudo jtop

# Terminal 2: Re-enter container and run node
docker exec -it da3_ros2_jetson bash
ros2 launch depth_anything_3_ros2 depth_anything_3_optimized.launch.py \
  backend:=tensorrt_native \
  trt_model_path:=/root/.cache/tensorrt/da3-small_fp16_518x518_ORIN_NX_16GB.engine \
  log_inference_time:=true

# Terminal 3: Monitor FPS over time
ros2 topic hz /depth_anything_3/depth

# Let it run for 10 minutes and observe
```

### 3.3 Thermal Monitoring Checklist

**While running, monitor in jtop:**

- [ ] **GPU Temp:** Should stay <80°C (ideally 60-75°C)
- [ ] **CPU Temp:** Should stay <80°C
- [ ] **GPU Utilization:** Should be 80-95% (confirms GPU-bound, not CPU-bound)
- [ ] **Power Mode:** Should show "MAXN" (maximum performance)
- [ ] **No Throttling Flags:** "PTHERM" or thermal warnings

**FPS Stability Check:**
- [ ] FPS should remain stable over 10 minutes (±2 FPS variance acceptable)
- [ ] No gradual degradation (indicates thermal throttling)

### 3.4 If Throttling Occurs

**Symptoms:**
- GPU temp >85°C
- FPS drops over time (e.g., starts at 28 FPS, drops to 18 FPS)
- "PTHERM" warning in jtop

**Solutions:**

1. **Enable jetson_clocks (max performance):**
   ```bash
   sudo jetson_clocks
   ```

2. **Add active cooling (fan):**
   - Attach a fan to the heatsink
   - Or use official Jetson carrier board with fan

3. **Reduce resolution (if cooling not available):**
   - Drop to 400x400 or 308x308
   - This reduces GPU load and heat generation

4. **Check power supply:**
   - Orin NX requires 15-20W for sustained load
   - Verify power supply is adequate (5V/4A minimum)

---

## Success Criteria Validation

### Final Checklist

Mark each item as you validate:

- [ ] **TensorRT Environment:** Import successful, trtexec found
- [ ] **Engine Build:** Completed without errors, ~90MB file size
- [ ] **FPS Target:** Achieved >20 FPS (preferably >25 FPS)
- [ ] **Thermal Stability:** No throttling over 10 minutes
- [ ] **GPU Utilization:** 80-95% during inference
- [ ] **Memory Usage:** <4GB VRAM (check nvidia-smi)
- [ ] **ROS2 Topics:** Publishing depth + confidence at target FPS

### Performance Results Template

Update TODO.md with these results:

```markdown
## Phase 1 Results (2026-01-30)

**Platform:** Jetson Orin NX 16GB
**JetPack:** 6.x (L4T r36.2.0)
**TensorRT:** 8.6.x

**TensorRT Engine:**
- Model: da3-small
- Precision: FP16
- Resolution: 518x518
- Engine Size: 89.45 MB
- Build Time: 8m 34s

**Performance:**
- FPS: 27.3 FPS (avg over 10 min)
- Latency: 36.6ms (avg)
- GPU Temp: 72°C (sustained)
- GPU Util: 92%
- VRAM: 1.8GB / 16GB

**Status:** SUCCESS - Exceeded >20 FPS target
**Next Steps:** Proceed to Phase 3 thermal validation
```

---

## Troubleshooting Guide

### Issue 1: TensorRT Import Fails

**Error:**
```
ModuleNotFoundError: No module named 'tensorrt'
```

**Solution:**
```bash
# Verify you're in the Jetson container
echo $BUILD_TYPE  # Should show "jetson-base"

# Check TensorRT installation
ls /usr/lib/aarch64-linux-gnu/libnvinfer*

# If missing, rebuild container
exit
docker compose build depth-anything-3-jetson
```

### Issue 2: trtexec Not Found

**Error:**
```
ERROR: trtexec not found
```

**Solution:**
```bash
# Check JetPack installation
dpkg -l | grep tensorrt

# trtexec is in JetPack, verify path
ls /usr/src/tensorrt/bin/trtexec

# Add to PATH if needed
export PATH=/usr/src/tensorrt/bin:$PATH
```

### Issue 3: FPS Much Lower Than Expected (<10 FPS)

**Possible Causes:**

1. **PyTorch backend instead of TensorRT:**
   ```bash
   # Check node logs - should see "Backend: tensorrt_native"
   # If seeing "Backend: pytorch", engine not loaded
   ```

2. **CPU fallback for unsupported operators:**
   ```bash
   # Check trtexec build logs for warnings:
   grep -i "fallback" /var/log/tensorrt_build.log
   ```

3. **GPU throttling:**
   ```bash
   # Check current power mode
   sudo nvpmodel -q
   # Should be mode 0 (MAXN)
   
   # Force MAXN mode
   sudo nvpmodel -m 0
   sudo jetson_clocks
   ```

4. **Memory bandwidth saturation:**
   ```bash
   # Check if using shared memory
   nvidia-smi  # Look for "Shared GPU Memory"
   
   # This is expected on Jetson (unified memory)
   # Try lower resolution if memory-bound
   ```

### Issue 4: ONNX Download Fails

**Error:**
```
ERROR: Failed to download ONNX model: HTTP 403
```

**Solution:**
```bash
# Manually download from HuggingFace
wget https://huggingface.co/onnx-community/depth-anything-v3-small/resolve/main/onnx/model.onnx \
  -O /root/.cache/onnx/onnx/model.onnx

# Then retry build with --skip-download
python3 /app/scripts/build_tensorrt_engine.py \
  --model da3-small \
  --precision fp16 \
  --resolution 518 \
  --skip-download \
  --output-dir /root/.cache
```

### Issue 5: ROS2 Topic Not Publishing

**Symptoms:**
- Node starts successfully
- No errors in logs
- `ros2 topic hz` shows no data

**Debug Steps:**

```bash
# 1. Check if camera is publishing
ros2 topic list
ros2 topic echo /camera/image_raw --no-arr

# 2. Check topic remapping
ros2 node info /depth_anything_3_optimized

# 3. Verify image encoding
ros2 topic echo /camera/image_raw | grep encoding
# Should be "bgr8" or "rgb8"

# 4. Check for subscription
ros2 topic info /camera/image_raw
# Should show 1 subscriber (the depth node)
```

---

## Next Steps After Validation

Once Phase 1-3 are complete:

1. **Update TODO.md** with actual results
2. **Document in CHANGELOG.md**
3. **Consider Phase 4:** INT8 Quantization (if >30 FPS needed)
4. **Consider DLA Support** (for power efficiency)
5. **Deploy to production environment**

---

## Quick Reference Commands

```bash
# Build and start container
DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson

# Exec into container
docker exec -it da3_ros2_jetson bash

# Check TensorRT
python3 -c "import tensorrt; print(tensorrt.__version__)"

# Launch node
ros2 launch depth_anything_3_ros2 depth_anything_3_optimized.launch.py \
  backend:=tensorrt_native \
  trt_model_path:=/root/.cache/tensorrt/da3-small_fp16_518x518_ORIN_NX_16GB.engine \
  log_inference_time:=true

# Measure FPS
ros2 topic hz /depth_anything_3/depth

# Monitor GPU
watch -n 1 nvidia-smi

# Monitor thermals
tegrastats --interval 1000
# or
sudo jtop
```

---

**Created:** 2026-01-30  
**For:** Jetson Orin NX 16GB TensorRT Optimization  
**Success Target:** >20 FPS (preferably >30 FPS)
