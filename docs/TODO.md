# Optimization Plan: Feature/Performance-Optimization

## Objective
Achieve >30 FPS on NVIDIA Jetson Orin AGX with 1080p output (Depth + Confidence) and ensure compatibility across the Jetson family (Nano, NX, AGX, Thor).

## Current Status
- **Baseline**: ~6 FPS (PyTorch path, CPU bottlenecks).
- **Bottlenecks**: 
  - Excessive CPU-GPU data transfers (PIL conversions).
  - Missing confidence output in TensorRT path.
  - Lack of platform-specific tuning.

## Roadmap

### 1. Fix Critical CPU Bottlenecks (PyTorch Backend)
- [ ] **Refactor `da3_inference.py`**:
    - Remove `PIL` dependency in the hot path.
    - Implement direct `torch.Tensor` preprocessing on GPU.
    - Ensure input stays on GPU from `cv_bridge` (if possible) or minimize upload cost.
- [ ] **Optimize `depth_anything_3_node_optimized.py`**:
    - Verify `cv_bridge` usage is optimal.
    - Ensure `inference` method accepts and returns tensors/arrays without unnecessary copies.

### 2. Enable TensorRT with Confidence Output
- [ ] **Update `examples/scripts/optimize_tensorrt.py`**:
    - Modify the export logic to include the confidence head.
    - Verify ONNX export includes both `depth` and `confidence` outputs.
- [ ] **Update `da3_inference_optimized.py`**:
    - Handle multi-output TensorRT bindings (Depth + Confidence).
    - Remove the "dummy confidence" placeholder.

### 3. Platform-Adaptive Launch System
- [ ] **Create `launch/performance.launch.py`**:
    - Add `platform` argument (e.g., `orin_agx`, `orin_nano`, `xavier_nx`).
    - Automatically configure:
        - `model_input_size` (384x384 vs 518x518).
        - `model_name` (Small vs Base).
        - `precision` (INT8 vs FP16).
- [ ] **Create Platform Configs**:
    - `config/platforms/orin_agx.yaml`
    - `config/platforms/orin_nano.yaml`

### 4. Verification & Benchmarking
- [ ] **Benchmark Script**:
    - Create a script to measure FPS, Latency, and GPU/CPU usage.
- [ ] **Validation**:
    - Verify 1080p output quality.
    - Verify >30 FPS on Orin AGX.

## Notes
- **Branch**: `feature/performance-optimization`
- **Target Hardware**: NVIDIA Jetson Orin AGX 64GB
