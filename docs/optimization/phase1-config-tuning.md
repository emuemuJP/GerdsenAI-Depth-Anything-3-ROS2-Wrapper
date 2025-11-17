# Phase 1: Configuration Tuning

**Branch**: `opt/phase1-config-tuning`
**Date**: 2025-11-17
**Goal**: Measure impact of DA3-SMALL model vs DA3-BASE at same resolution (518x518)

## Baseline Performance

**Hardware**:
- Platform: NVIDIA Jetson AGX Orin 64GB (Syslogic A4AGX64)
- CPU: 12-core ARM Cortex-A78AE @ 2.2 GHz
- GPU: NVIDIA Ampere (2048 CUDA cores, 64 Tensor cores)
- RAM: 64 GB LPDDR5 (unified memory)

**Software**:
- OS: Ubuntu 22.04 LTS + JetPack 6.2.1
- CUDA: 12.6
- ROS2: Humble Hawksbill
- PyTorch: 2.8.0 (Jetson-optimized)

**Baseline Configuration**:
- Model: DA3-BASE
- Input Resolution: 518x518
- Confidence Publishing: Enabled
- Colored Depth: Enabled

**Baseline Metrics**:
- FPS: 6.35
- Inference Time: 153ms per frame
- GPU Utilization: 35-69%
- RAM Usage: ~6 GB (out of 64 GB)

## Changes Made

### 1. Model Change: DA3-BASE → DA3-SMALL
**File**: `config/params.yaml`
**Line**: 9

**Change**:
```yaml
# Before
model_name: "depth-anything/DA3-BASE"

# After
model_name: "depth-anything/DA3-SMALL"
```

**Rationale**:
- DA3-SMALL has 25M parameters vs DA3-BASE's larger model
- Faster inference with acceptable quality tradeoff
- Expected speedup: 20-30%

### 2. Disable Confidence Computation
**File**: `config/params.yaml`
**Line**: 21

**Change**:
```yaml
# Before
publish_confidence: true

# After
publish_confidence: false
```

**Rationale**:
- Confidence map not currently used in pipeline
- Eliminates expensive confidence computation
- Reduces memory bandwidth usage
- Expected speedup: 10-15%

### 3. Enable Inference Time Logging
**File**: `config/params.yaml`
**Line**: 29

**Change**:
```yaml
# Before
log_inference_time: false

# After
log_inference_time: true
```

**Rationale**:
- Monitor per-frame inference time
- Verify performance improvements
- Identify performance regressions

## Expected Performance

**Expected Impact**:
- DA3-SMALL vs DA3-BASE: +20-30% FPS (smaller model, fewer parameters)
- Confidence disabled: +10-15% FPS (eliminate extra computation)
- **Combined**: ~1.35-1.5x speedup → 8.5-9.5 FPS

**Target**:
- **Target FPS**: 8-10 FPS
- **Target Inference Time**: 105-125ms per frame

**Note**: Resolution kept at 518x518 to maintain apples-to-apples comparison with baseline

## Testing Instructions

### 1. Update Package on Jetson

```bash
# Copy updated config to Jetson
scp /home/gerdsenai/Documents/GerdsenAI-Depth-Anything-3-ROS2-Wrapper/config/params.yaml \
    nvidia@10.69.1.168:~/ros2_ws/src/depth_anything_3_ros2/config/

# Rebuild package (if needed)
ssh nvidia@10.69.1.168 "cd ~/ros2_ws && colcon build --packages-select depth_anything_3_ros2 && source install/setup.bash"
```

### 2. Run Benchmark

```bash
# Stop existing pipeline
ssh nvidia@10.69.1.168 "pkill -f 'v4l2_camera_node|depth_anything_3_node|image_view'"

# Launch optimized pipeline
ssh nvidia@10.69.1.168 "cd ~/ros2_ws && source install/setup.bash && \
  ros2 launch depth_anything_3_ros2 usb_camera_example.launch.py \
    video_device:=/dev/video0 \
    image_width:=640 \
    image_height:=480"
```

### 3. Monitor Performance

```bash
# Watch inference time logs
ssh nvidia@10.69.1.168 "ros2 topic echo /depth_anything_3/inference_time"

# Monitor GPU utilization
ssh nvidia@10.69.1.168 "tegrastats --interval 1000"

# Check topic frequency
ssh nvidia@10.69.1.168 "ros2 topic hz /depth_anything_3/depth"
```

## Quality Verification

### Visual Inspection
1. Check depth map quality in visualization window
2. Verify smooth gradients and accurate boundaries
3. Compare with baseline screenshots

### Quantitative Metrics (if available)
- Depth accuracy on test dataset
- Edge preservation quality
- Temporal stability (if recording video)

## Benchmark Template

```
Date: 2025-11-17
Branch: opt/phase1-config-tuning
Hardware: Jetson AGX Orin 64GB
Configuration:
  Model: DA3-SMALL
  Resolution: 518x518 (same as baseline)
  Confidence: Disabled
  Colored: Enabled

Results:
  FPS: [TO BE MEASURED]
  Inference Time: [TO BE MEASURED] ms
  GPU Utilization: [TO BE MEASURED] %
  RAM Usage: [TO BE MEASURED] GB

Quality Assessment:
  Visual Quality: [Excellent/Good/Acceptable/Poor]
  Compared to Baseline: [Better/Same/Worse]

Notes:
  - [Any observations]
  - [Issues encountered]
  - [Recommendations]
```

## Rollback Instructions

If performance degrades or quality is unacceptable:

```bash
# Checkout main branch config
cd /home/gerdsenai/Documents/GerdsenAI-Depth-Anything-3-ROS2-Wrapper
git checkout main -- config/params.yaml

# Copy to Jetson
scp config/params.yaml nvidia@10.69.1.168:~/ros2_ws/src/depth_anything_3_ros2/config/

# Rebuild
ssh nvidia@10.69.1.168 "cd ~/ros2_ws && colcon build --packages-select depth_anything_3_ros2"
```

## Next Steps

### If Successful (8-10 FPS achieved):
- Proceed to Phase 2: Direct Tensor Conversion
- Target: 12-15 FPS

### If Partial Success (7-8 FPS):
- Fine-tune resolution (try 320x320, 448x448)
- Test different model variants
- Consider additional config optimizations

### If Unsuccessful (<7 FPS):
- Investigate bottlenecks with profiling
- Check for configuration issues
- Verify correct model loading

## Files Modified

- `config/params.yaml` - Optimized configuration parameters
- `docs/optimization/phase1-config-tuning.md` - This documentation
- `docs/claude.md` - Development guidelines
- `.gitignore` - Added optimization artifacts

## References

- Depth Anything V3 Paper: https://arxiv.org/abs/2408.02532
- Model Repository: https://github.com/ByteDance-Seed/Depth-Anything-3
- Jetson AGX Orin Specs: https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/
