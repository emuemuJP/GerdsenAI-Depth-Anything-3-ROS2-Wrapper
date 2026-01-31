# Depth Anything V3 on Jetson Orin NX: TensorRT 8.6 won't work

**The definitive answer: DA3 + TensorRT 8.6 is not achievable without TensorRT upgrade.** The ika-rwth-aachen repository—the only working DA3+TRT implementation—requires TensorRT 10.9, not 8.6. Your "caskConvolutionV2Forward" error stems from TRT 8.6's fundamental inability to process DINOv2's Einsum-based attention patterns. The solution is upgrading to **JetPack 6.2** (TensorRT 10.3), which fully supports Jetson Orin NX and includes a 70% AI TOPS boost via "Super Mode."

---

## Why TensorRT 8.6 cannot build DA3 engines

The DINOv2 backbone at DA3's core uses `F.scaled_dot_product_attention()` which exports to ONNX as complex Einsum operations. TensorRT 8.6 has three critical limitations:

- **Einsum restrictions**: TRT 8.6 does not support more than 2 inputs, ellipsis notation, or diagonal operations in Einsum layers. DINOv2's attention patterns like `"nlhd,nhdv,nlh->nlhv"` fail completely.
- **Missing ViT optimizations**: TRT 8.6 lacks Multi-Head Attention (MHA) fusion for Vision Transformers—attention operations remain as unoptimized separate MatMul/Softmax chains.
- **Format incompatibility**: The error `"caskConvolutionV2Forward could not find any supported formats"` indicates TRT 8.6 cannot find compatible CUDA kernels for DINOv2's specific tensor format/precision combinations.

NVIDIA's TensorRT GitHub Issue #4537 confirms these DINOv2 compilation failures persist even into early TRT 10.x versions, with full fixes arriving in **TensorRT 10.8+**.

---

## How ika-rwth-aachen solves this (they use TRT 10.9)

The ika-rwth-aachen/ros2-depth-anything-v3-trt repository achieves DA3+TRT compatibility through one key requirement: **TensorRT 10.9**. They don't use custom plugins, graph surgery, or workarounds—they simply rely on TRT 10.x's improved transformer support.

Their tested configurations use Docker images `nvcr.io/nvidia/tensorrt:25.08-py3` and `nvcr.io/nvidia/tensorrt:25.03-py3`, both containing TensorRT 10.9 with CUDA 12.8+. The only preprocessing step is modifying DA3's source before ONNX export:

```python
# File: src/depth_anything_3/api.py
# Change bfloat16 to float16 (ONNX doesn't fully support bfloat16)
autocast_dtype = torch.float16  # NOT torch.bfloat16
```

Export uses fixed input shape `[1, 3, 280, 504]` and produces two outputs: metric depth and sky classification. Pre-built ONNX models are available at **huggingface.co/TillBeemelmanns/Depth-Anything-V3-ONNX**.

---

## The upgrade path: JetPack 6.2 with TensorRT 10.3

JetPack 6.2 is the production release for Jetson Orin NX with TensorRT 10.3—a massive upgrade from 8.6. This version includes critical ViT/transformer fixes and enables "Super Mode" which boosts your Orin NX 16GB to **up to 70% more AI TOPS**.

| Component | JetPack 6.0 (Current) | JetPack 6.2 (Target) |
|-----------|----------------------|---------------------|
| TensorRT | **8.6** | **10.3** |
| CUDA | 12.2 | 12.6 |
| cuDNN | 8.9 | 9.3 |
| ViT Support | Limited | Enhanced MHA fusion |

**Upgrade procedure:**
```bash
# On Jetson Orin NX, upgrade from JetPack 6.0/6.1 to 6.2
sudo apt-add-repository universe
sudo apt-add-repository multiverse
sudo apt-get update
sudo apt-get install nvidia-jetpack
sudo reboot
```

Note: Firmware update may be required. Verify post-upgrade with `dpkg -l | grep nvidia`. JetPack 7 is **not available** for Orin NX—it's exclusive to the new Jetson Thor platform.

---

## Alternative approaches if upgrade is impossible

### Option 1: ONNX Runtime hybrid execution (partial acceleration)

ONNX Runtime with TensorRT Execution Provider can accelerate TRT-compatible ops while falling back to CUDA EP for problematic layers:

```python
import onnxruntime as ort

sess = ort.InferenceSession('da3.onnx', providers=[
    ('TensorrtExecutionProvider', {
        'trt_op_types_to_exclude': 'Einsum,LayerNormalization',
        'trt_fp16_enable': True,
        'trt_engine_cache_enable': True
    }),
    'CUDAExecutionProvider'
])
```

This yields **20-40% slower performance** than full TRT but remains faster than pure CUDA inference.

### Option 2: Use Depth Anything V2 instead

The spacewalk01/depth-anything-tensorrt repository provides working TRT 8.6 implementations for **V1 and V2 only**. V2 uses a similar DINOv2 backbone but with different intermediate feature extraction that happens to work with older TRT versions. Quality is comparable to V3 for many use cases.

```bash
# spacewalk01 export for V2
python export_v2.py --encoder vitb --input-size 518
```

Known issue: INT64 weights require casting to INT32 on some Jetson configurations.

### Option 3: Modify DINOv2 attention implementation (complex)

Replace `scaled_dot_product_attention` with explicit operations before ONNX export:

```python
def explicit_attention(q, k, v, scale=None):
    scale = scale or (1.0 / math.sqrt(q.size(-1)))
    attn = (q @ k.transpose(-2, -1)) * scale
    attn = F.softmax(attn, dim=-1)
    return attn @ v
```

This requires forking DA3, modifying the DINOv2 backbone attention modules, and re-exporting to ONNX. Significant development effort with uncertain results on TRT 8.6.

---

## Pre-built resources and working implementations

| Resource | Description | URL |
|----------|-------------|-----|
| DA3 ONNX Models | Pre-exported ONNX (280×504 input) | huggingface.co/TillBeemelmanns/Depth-Anything-V3-ONNX |
| ROS2 DA3 TRT Node | Working TRT 10.9 implementation | github.com/ika-rwth-aachen/ros2-depth-anything-v3-trt |
| Jetson Orin Depth | V1/V2 for Jetson (small model only) | github.com/IRCVLab/Depth-Anything-for-Jetson-Orin |
| Seeed Studio Guide | DA3 deployment on Jetson AGX Orin | wiki.seeedstudio.com/deploy_depth_anything_v3_jetson_agx_orin |
| DA2 TensorRT | V1/V2 with TRT 8.6 support | github.com/spacewalk01/depth-anything-tensorrt |

The IRCVLab repository works on Jetson Orin but recommends the **small (vits14) model only** due to memory constraints—larger models may exceed 16GB on Orin NX.

---

## Conclusion

**Upgrade to JetPack 6.2 is the definitive solution.** TensorRT 10.3 includes the transformer/ViT improvements necessary for DA3's DINOv2 backbone. No custom plugins, graph surgery, or architectural modifications exist that make DA3 work reliably on TRT 8.6—the Einsum limitations are fundamental.

If upgrading is impossible, use ONNX Runtime's hybrid execution for partial TRT acceleration, or switch to Depth Anything V2 which has proven TRT 8.6 compatibility. The performance difference between V2 and V3 is marginal for most depth estimation tasks, making V2 a practical alternative when TRT version constraints cannot be changed.