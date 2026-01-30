# TensorRT Optimization Plan for Jetson Deployment

## Executive Summary

The TensorRT optimization plan is **approved and ready for implementation**. After reviewing the codebase, the plan aligns perfectly with existing infrastructure (`model_catalog.yaml`, `jetson_detector.py`) and addresses all critical gaps.

**Verdict: APPROVE with minor refinements**

---

## Problem Summary

The current TensorRT implementation has gaps that prevent seamless deployment:

1. **Missing Dependencies**: `pycuda` and `huggingface_hub` not installed in Dockerfile
2. **No Automatic Engine Building**: Users must manually run scripts after container deployment
3. **Inconsistent Settings**: Build script uses 518x518 FP16, docs recommend 384x384 INT8
4. **Poor User Experience**: TensorRT inference fails immediately due to missing deps
5. **Docker Compose Gaps**: Missing `NVIDIA_DRIVER_CAPABILITIES` for Jetson service

---

## Plan Validation

### ✅ Strengths

1. **Accurate Problem Identification**
   - Correctly identified missing `pycuda` and `huggingface_hub` dependencies
   - Spotted the missing `NVIDIA_DRIVER_CAPABILITIES` in docker-compose
   - Recognized inconsistency between build script (518x518 FP16) and docs (384x384 INT8)

2. **Well-Researched Recommendations**
   - FP16 over INT8 is correct (INT8 needs calibration dataset which isn't implemented)
   - Platform-specific settings align with `model_catalog.yaml` (lines 381-451)
   - Resolution recommendations match existing `jetson_detector.py` logic

3. **Practical Implementation Approach**
   - Phased rollout minimizes risk
   - Optional build-time vs runtime engine building provides flexibility
   - Proper volume mounts for engine caching

### ⚠️ Minor Gaps Identified

1. **Missing Flag in build_tensorrt_engine.py**
   - Original plan references `--auto-resolution` flag but this doesn't exist
   - The script already has `--auto` which handles resolution selection via `PLATFORM_CONFIGS`
   - **Fix**: Use existing `--auto` flag instead

2. **TensorRT Python Bindings**
   - JetPack includes TensorRT C++ libraries, but Python bindings may need explicit verification
   - **Add**: `python3 -c "import tensorrt"` verification step

---

## Research Findings

### Best Practices from Existing Implementations

| Source | Approach | Performance |
|--------|----------|-------------|
| [ika-rwth-aachen/ros2-depth-anything-v3-trt](https://github.com/ika-rwth-aachen/ros2-depth-anything-v3-trt) | Pre-exported ONNX + TensorRT | ~50 FPS (RTX 6000) |
| [spacewalk01/depth-anything-tensorrt](https://github.com/spacewalk01/depth-anything-tensorrt) | trtexec conversion | 3-12ms (RTX 4090) |

### Key Insights

- **FP16 is optimal precision** for Jetson (best speed/accuracy tradeoff)
- Input dimensions must be **divisible by 14** (ViT patch size)
- **Pre-build and cache engines** to avoid runtime overhead
- Measure **end-to-end latency** including preprocessing

### Platform-Specific Recommendations

| Platform | Model | Resolution | Precision | Expected FPS |
|----------|-------|------------|-----------|--------------| 
| Orin Nano 4GB | da3-small | 308 | FP16 | 30 |
| Orin Nano 8GB | da3-small | 308 | FP16 | 35 |
| Orin NX 8GB | da3-small | 308 | FP16 | 40 |
| Orin NX 16GB | da3-small | 518 | FP16 | 45 |
| AGX Orin 32GB | da3-base | 518 | FP16 | 50 |
| AGX Orin 64GB | da3-large | 518 | FP16 | 50+ |

---

## Implementation Plan

### Phase 1: Fix Dependencies in Dockerfile

**File:** `Dockerfile`

**Changes:**

```dockerfile
# Line ~113-119: Add python3-dev to Jetson system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    git \
    wget \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Line ~260: Add TensorRT dependencies after PyTorch installation
RUN if [ "$BUILD_TYPE" = "jetson-base" ]; then \
        pip3 install --no-cache-dir pycuda huggingface_hub; \
    fi

# Line ~262: Verify TensorRT is accessible (Jetson only)
RUN if [ "$BUILD_TYPE" = "jetson-base" ]; then \
        python3 -c "import tensorrt; print(f'TensorRT {tensorrt.__version__}')" && \
        python3 -c "import pycuda.driver as cuda; print('pycuda OK')" && \
        python3 -c "import huggingface_hub; print('huggingface_hub OK')"; \
    fi
```

**Complexity:** 3/10 - Straightforward dependency additions

---

### Phase 2: Add TensorRT Build Arguments

**File:** `Dockerfile`

**Changes:**

```dockerfile
# Line ~14: Add TensorRT configuration arguments
ARG BUILD_TENSORRT=false
ARG TENSORRT_MODEL=da3-small
ARG TENSORRT_PRECISION=fp16
```

**Note:** Removed `TENSORRT_RESOLUTION` - the `--auto` flag handles this via platform detection

**Complexity:** 2/10 - Simple build args

---

### Phase 3: Implement Optional Engine Building

**File:** `Dockerfile`

**Changes:**

```dockerfile
# Line ~320, before ENTRYPOINT: Add optional TensorRT engine build
ARG BUILD_TENSORRT
ARG TENSORRT_MODEL
ARG TENSORRT_PRECISION

RUN if [ "$BUILD_TYPE" = "jetson-base" ] && [ "$BUILD_TENSORRT" = "true" ]; then \
        echo "Building TensorRT engine: $TENSORRT_MODEL ($TENSORRT_PRECISION)"; \
        python3 /ros2_ws/src/depth_anything_3_ros2/scripts/build_tensorrt_engine.py \
            --model "$TENSORRT_MODEL" \
            --precision "$TENSORRT_PRECISION" \
            --auto \
            --output-dir /root/.cache; \
    fi
```

**Key Change:** Use `--auto` instead of `--auto-resolution` (which doesn't exist)

**Complexity:** 4/10 - Conditional build logic

---

### Phase 4: Enhance Entrypoint Script

**File:** `docker/ros_entrypoint.sh`

**Changes:**

```bash
#!/bin/bash
set -e

# Source ROS2 environment
source /opt/ros/humble/setup.bash

# Source workspace if it exists
if [ -f /ros2_ws/install/setup.bash ]; then
    source /ros2_ws/install/setup.bash
fi

# TensorRT engine detection and optional on-demand building
if [ "${DA3_TENSORRT_AUTO:-false}" = "true" ]; then
    ENGINE_DIR="/root/.cache/tensorrt"
    if [ ! -d "$ENGINE_DIR" ] || [ -z "$(ls -A $ENGINE_DIR/*.engine 2>/dev/null)" ]; then
        echo "[TensorRT] No engines found, building automatically..."
        python3 /ros2_ws/src/depth_anything_3_ros2/scripts/build_tensorrt_engine.py --auto --output-dir /root/.cache
    else
        echo "[TensorRT] Found existing engines in $ENGINE_DIR"
        ls -lh $ENGINE_DIR/*.engine
    fi
fi

# Execute the command
exec "$@"
```

**Complexity:** 5/10 - Adds runtime engine building logic

---

### Phase 5: Fix docker-compose.yml

**File:** `docker-compose.yml`

**Changes:**

```yaml
# Line ~76: Update Jetson service environment and volumes
depth-anything-3-jetson:
  # ... existing config ...
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
    - NVIDIA_DRIVER_CAPABILITIES=all  # ADD THIS
    - ROS_DOMAIN_ID=0
    - DISPLAY=${DISPLAY}
    - DA3_TENSORRT_AUTO=${DA3_TENSORRT_AUTO:-false}  # ADD THIS
    # Model configuration
    - DA3_MODEL=${DA3_MODEL:-}
    - DA3_INFERENCE_HEIGHT=${DA3_INFERENCE_HEIGHT:-}
    - DA3_INFERENCE_WIDTH=${DA3_INFERENCE_WIDTH:-}
    - DA3_VRAM_LIMIT_MB=${DA3_VRAM_LIMIT_MB:-}
  volumes:
    - /tmp/.X11-unix:/tmp/.X11-unix:rw
    - ./models:/root/.cache/huggingface:rw
    - ./models/tensorrt:/root/.cache/tensorrt:rw  # ADD: TensorRT engine cache
    - ./models/onnx:/root/.cache/onnx:rw          # ADD: ONNX model cache
    - ./examples:/examples:ro
    - ./config:/app/config:ro
    - /dev:/dev:rw
```

**Complexity:** 3/10 - Environment and volume additions

---

### Phase 6: Update OPTIMIZATION_GUIDE.md

**File:** `OPTIMIZATION_GUIDE.md`

**Changes:**

1. **Line 34-55:** Update TensorRT INT8 recommendation to FP16
2. **Line 62-68:** Update precision recommendation
3. **Line 214-218:** Update backend table

**Complexity:** 4/10 - Documentation alignment

---

## Build Strategy Options

The plan offers three engine-building strategies:

### Option A: Build-Time (Baked into Image)
- **Pros:** Fastest startup, engine ready immediately
- **Cons:** Longer build time, platform-specific images
- **Use Case:** Production deployments on known hardware

### Option B: Runtime Auto-Build (On First Run) ⭐ RECOMMENDED
- **Pros:** Flexible, works on any platform, one-time delay
- **Cons:** 5-10 minute delay on first container start
- **Use Case:** Development, multi-platform deployments

### Option C: Manual (User Runs Script)
- **Pros:** Maximum control, explicit workflow
- **Cons:** Requires user intervention, more steps
- **Use Case:** Advanced users, custom configurations

**Recommendation:** Implement **Option B** as default with **Option A** as optional.

**Usage Examples:**

```bash
# Option B: Quick start with runtime auto-build
DA3_TENSORRT_AUTO=true docker compose up depth-anything-3-jetson

# Option A: Pre-built engine at build time
docker compose build depth-anything-3-jetson \
    --build-arg BUILD_TENSORRT=true \
    --build-arg TENSORRT_MODEL=da3-small \
    --build-arg TENSORRT_PRECISION=fp16

# Option C: Manual build
docker run --rm --runtime=nvidia \
    -v ./models/tensorrt:/root/.cache/tensorrt:rw \
    depth_anything_3_ros2:jetson \
    python3 /ros2_ws/src/depth_anything_3_ros2/scripts/build_tensorrt_engine.py --auto
```

---

## Verification Plan

### 1. Dependency Verification

```bash
# Build Jetson image
docker compose build depth-anything-3-jetson

# Verify dependencies
docker run --rm --runtime=nvidia depth_anything_3_ros2:jetson \
    python3 -c "
import tensorrt
import pycuda.driver
import huggingface_hub
print('✓ All TensorRT dependencies OK')
print(f'  TensorRT: {tensorrt.__version__}')
"
```

**Expected:** All imports succeed, TensorRT version printed

---

### 2. Engine Building Test

```bash
# Create models directory
mkdir -p models/tensorrt models/onnx

# Run engine build
docker run --rm --runtime=nvidia \
    -v ./models/tensorrt:/root/.cache/tensorrt:rw \
    -v ./models/onnx:/root/.cache/onnx:rw \
    depth_anything_3_ros2:jetson \
    python3 /ros2_ws/src/depth_anything_3_ros2/scripts/build_tensorrt_engine.py --auto

# Verify engine was created
ls -lh models/tensorrt/*.engine
```

**Expected:** 
- ONNX model downloaded to `models/onnx/`
- TensorRT engine created in `models/tensorrt/`
- Engine filename includes platform (e.g., `da3-small_fp16_308x308_ORIN_NX_16GB.engine`)

---

### 3. Build-Time Engine Generation Test

```bash
# Build with TensorRT engine
docker compose build depth-anything-3-jetson \
    --build-arg BUILD_TENSORRT=true \
    --build-arg TENSORRT_MODEL=da3-small \
    --build-arg TENSORRT_PRECISION=fp16

# Verify engine exists in image
docker run --rm --runtime=nvidia depth_anything_3_ros2:jetson \
    ls -lh /root/.cache/tensorrt/
```

**Expected:** Engine file present in image

---

### 4. Runtime Auto-Build Test

```bash
# Start container with auto-build enabled
docker run --rm --runtime=nvidia \
    -e DA3_TENSORRT_AUTO=true \
    -v ./models/tensorrt:/root/.cache/tensorrt:rw \
    depth_anything_3_ros2:jetson \
    bash -c "echo 'Container started, engine should build automatically'"
```

**Expected:** "[TensorRT] No engines found, building automatically..." in logs

---

### 5. ROS2 Inference Test (Requires Jetson Hardware)

```bash
# Terminal 1: Start container
docker compose up depth-anything-3-jetson

# Terminal 2: Inside container, run optimized node
docker exec -it da3_ros2_jetson bash
source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash

# Find engine file
ENGINE=$(ls /root/.cache/tensorrt/*.engine | head -n 1)

# Launch with TensorRT backend
ros2 launch depth_anything_3_ros2 depth_anything_3_optimized.launch.py \
    backend:=tensorrt_native \
    trt_model_path:=$ENGINE \
    log_inference_time:=true

# Terminal 3: Check output
ros2 topic echo /depth_anything_3/depth --once
```

**Expected:**
- Node starts without errors
- TensorRT engine loads successfully
- Inference runs at expected FPS
- Depth map published to `/depth_anything_3/depth`

---

### 6. Docker Compose Environment Test

```bash
# Create .env file
cat > .env << EOF
DA3_TENSORRT_AUTO=true
DA3_MODEL=DA3-SMALL
EOF

# Start with environment
docker compose --env-file .env up depth-anything-3-jetson

# Verify environment inside container
docker exec da3_ros2_jetson env | grep DA3
```

**Expected:** Environment variables set correctly

---

## Files to Modify

| File | Changes | Priority |
|------|---------|----------|
| `Dockerfile` | Add pycuda, huggingface_hub, python3-dev, TensorRT build args | CRITICAL |
| `docker-compose.yml` | Add NVIDIA_DRIVER_CAPABILITIES, volume mounts | HIGH |
| `docker/ros_entrypoint.sh` | Add TensorRT detection and auto-build | MEDIUM |
| `OPTIMIZATION_GUIDE.md` | Align with implementation (FP16, platform-aware) | LOW |

---

## Implementation Order

1. **Phase 1** (Dependencies) - **CRITICAL** - Blocks all other phases
2. **Phase 5** (docker-compose) - **HIGH** - Enables GPU access
3. **Phase 2** (Build args) - **MEDIUM** - Enables optional features
4. **Phase 3** (Build-time engines) - **MEDIUM** - Optional optimization
5. **Phase 4** (Entrypoint) - **MEDIUM** - Runtime convenience
6. **Phase 6** (Documentation) - **LOW** - User-facing clarity

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| pycuda compilation fails | Low | High | Pre-built wheels available for JetPack 6.x |
| TensorRT version mismatch | Very Low | High | JetPack bundles matching versions |
| Engine build timeout | Medium | Medium | Make build-time optional, use runtime fallback |
| Memory exhaustion | Low | Medium | Platform detection limits model/resolution |
| ONNX download fails | Low | Low | Retry logic + manual download instructions |

---

## Additional Recommendations

### 1. Add Engine Validation

Add validation after engine building:

```python
# In build_tensorrt_engine.py, after engine build:
def validate_engine(engine_path: Path) -> bool:
    """Quick validation that engine loads."""
    try:
        from depth_anything_3_ros2.da3_inference_optimized import TensorRTNativeInference
        trt = TensorRTNativeInference(str(engine_path))
        print(f"✓ Engine validation passed: {engine_path.name}")
        trt.cleanup()
        return True
    except Exception as e:
        print(f"✗ Engine validation failed: {e}")
        return False
```

### 2. Add Progress Indicators

Engine building takes 5-10 minutes:

```bash
# In entrypoint script:
echo "[TensorRT] Building engine (this may take 5-10 minutes)..."
python3 /ros2_ws/.../build_tensorrt_engine.py --auto --verbose
```

### 3. Document Engine Caching

Add to README.md:

```markdown
## TensorRT Engine Caching

Engines are cached in `./models/tensorrt/` and reused across container restarts.
To rebuild engines (e.g., after platform change):

```bash
rm -rf models/tensorrt/*
docker compose up depth-anything-3-jetson
```
```

---

## Immediate Priority (Docker Permission Fix)

Before any code changes, run on Jetson:

```bash
sudo usermod -aG docker $USER
newgrp docker  # or logout/login
docker compose build depth-anything-3-jetson
```

This will unblock Docker builds while the TensorRT improvements are implemented.

---

## Related Files

- `scripts/build_tensorrt_engine.py` - TensorRT engine builder (uses pre-exported ONNX)
- `depth_anything_3_ros2/da3_inference_optimized.py` - Native TensorRT inference class
- `config/model_catalog.yaml` - Model specifications and platform configurations
- `depth_anything_3_ros2/jetson_detector.py` - Jetson platform detection

---

## Conclusion

The proposed plan is **excellent and ready for implementation** with only minor refinements:

1. ✅ All technical approaches are sound
2. ✅ Aligns with existing codebase architecture
3. ✅ Addresses all identified gaps
4. ⚠️ Minor fix: Use `--auto` instead of `--auto-resolution`
5. ✅ Verification strategy is comprehensive

**Recommendation:** **APPROVE** and proceed with implementation in the order specified above.
