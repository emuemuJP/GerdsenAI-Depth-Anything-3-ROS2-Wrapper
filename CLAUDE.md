# CLAUDE.md

## Git Workflow (Non-Negotiable)

- **USER MAKES ALL COMMITS AND PRs** - Claude must NEVER commit or create PRs
- **Always branch off `main`** - Create feature branches from main for all work
- **Never commit directly to `main`** - All changes go through feature branches
- When starting work, create a new branch: `git checkout -b feature/description main`

## GitHub CLI Usage

Use `gh` CLI for all GitHub interactions:
```bash
# View issues
gh issue list
gh issue view <number>

# View PRs
gh pr list
gh pr view <number>

# Check repo status
gh repo view
```
Always offer to pull down and review issues before beginning work.

## Always see if there are specialized agents to help with tasks and troubleshooting, orchestrate agents to work together

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Build the package
colcon build --packages-select depth_anything_3_ros2

# Run tests
colcon test --packages-select depth_anything_3_ros2
colcon test-result --verbose

# Run a single test file
python3 -m pytest test/test_inference.py -v

# Lint and format
flake8 depth_anything_3_ros2/
black --check depth_anything_3_ros2/
black depth_anything_3_ros2/  # auto-format

# Launch with USB camera
ros2 launch depth_anything_3_ros2 depth_anything_3.launch.py image_topic:=/camera/image_raw

# Docker (GPU)
docker-compose up -d depth-anything-3-gpu

# Run live demo on Jetson
bash scripts/jetson_demo.sh

# Run demo (general)
bash scripts/run_demo.sh
```

## Jetson Deployment

Jetson Orin AGX is available at `10.69.7.112` with SSH keys configured (no password required).

```bash
# SSH to Jetson
ssh gerdsenai@10.69.7.112

# Deploy via SCP
scp -r . gerdsenai@10.69.7.112:~/depth_anything_3_ros2/

# Run commands remotely
ssh gerdsenai@10.69.7.112 "cd ~/depth_anything_3_ros2 && <command>"
```

## Host-Container TensorRT Architecture

Due to broken TensorRT Python bindings in containers, we use a split architecture:

- **Host**: Runs `scripts/trt_inference_service.py` (TensorRT inference)
- **Container**: Runs ROS2 nodes (camera driver, depth publisher)
- **Communication**: File-based IPC via `/tmp/da3_shared/`

| File | Direction | Format |
|------|-----------|--------|
| `input.npy` | Container -> Host | float32 [1,1,3,518,518] |
| `output.npy` | Host -> Container | float32 [1,518,518] |
| `request` | Container -> Host | Timestamp signal |
| `status` | Host -> Container | "ready", "complete:time", "error:msg" |

## Architecture

This is a ROS2 Humble wrapper for ByteDance's Depth Anything 3 monocular depth estimation, targeting >30 FPS on NVIDIA Jetson Orin AGX.

### 3-Layer Design
- **Node Layer** (`depth_anything_3_node.py`, `*_optimized.py`): ROS2 interface, parameter handling, topic management
- **Inference Layer** (`da3_inference.py`, `*_optimized.py`): Model loading via HuggingFace, CUDA/CPU inference
- **Utility Layer** (`utils.py`, `gpu_utils.py`): Depth processing, colorization, GPU acceleration

### Dual Implementation Pattern
- Standard nodes: Baseline functionality
- Optimized nodes (`*_optimized.py`): TensorRT, async processing, >30 FPS target
- Both expose identical ROS2 interfaces - changes to one should be reflected in the other

### Inference Wrapper Return Format
```python
{'depth': np.ndarray,  # (H, W) float32
 'confidence': np.ndarray,  # (H, W) float32, optional
 'camera_params': dict}  # optional
```

## Critical Design Principles

### Camera-Agnostic Design (Non-Negotiable)
- NEVER add camera-specific logic to core modules
- Camera integration ONLY via topic remapping and example launch files in `launch/examples/`
- All cameras work through standard `sensor_msgs/Image` interface

### ROS2 Patterns
- Use relative topic names with `~` prefix (e.g., `~/depth`, `~/image_raw`)
- BEST_EFFORT QoS for image subscribers (allows frame drops)
- Declare all parameters in node constructor

## Coding Standards

- **No emojis** - Forbidden in code, comments, docstrings, logs, and commits
- **Line length**: 88 characters (Black formatter)
- **Docstrings**: Google-style with type hints on all functions
- **Naming**: `PascalCase` classes, `snake_case` functions, `_private_methods`, `UPPER_SNAKE_CASE` constants

## Testing

Tests use mocked DA3 model (doesn't require GPU):
- `test/test_inference.py` - Unit tests for inference wrapper
- `test/test_node.py` - Integration tests for ROS2 node
- `test/test_generic_camera.py` - Camera-agnostic functionality

## Key Files

- `package.xml`, `setup.py` - ROS2 ament_python package config
- `launch/depth_anything_3.launch.py` - Main launch file with 13 configurable arguments
- `config/params.yaml` - Default parameters
- `.github/copilot-instructions.md` - Extended AI coding guidelines

## Specialized Agents

This repository includes specialized agents in `.claude/agents/`. Use them proactively for domain-specific tasks.

### Available Agents

| Agent | Domain | Use When |
|-------|--------|----------|
| `jetson-expert` | Hardware | Module selection, flashing, BSP, carrier boards, GPIO/CSI, thermal, boot issues |
| `nvidia-expert` | Software | CUDA, TensorRT, DeepStream, Isaac ROS, containers, profiling, PyTorch/TensorFlow |

### Agent Selection Guide

**Hardware questions** -> `jetson-expert`:
- "Which Jetson module should I use?"
- "How do I flash JetPack 6.x?"
- "Camera not detected on CSI port"
- "Thermal throttling issues"
- "Carrier board GPIO configuration"
- "Boot hangs after flashing"
- "Device tree or pinmux setup"

**Software questions** -> `nvidia-expert`:
- "How do I convert ONNX to TensorRT?"
- "Optimize inference performance"
- "DeepStream pipeline design"
- "Isaac ROS node optimization"
- "CUDA memory management"
- "Container can't access GPU"
- "INT8 calibration for TensorRT"

### Multi-Agent Scenarios

Some issues require both agents working together:

| Scenario | Primary Agent | Secondary Agent | Reason |
|----------|---------------|-----------------|--------|
| Slow inference on Orin NX | `nvidia-expert` | `jetson-expert` | Software first, then check thermal/power |
| Container can't access GPU | `nvidia-expert` | `jetson-expert` | Runtime config first, then driver/L4T check |
| CSI camera not detected | `jetson-expert` | - | Hardware/device tree issue |
| TensorRT build fails | `nvidia-expert` | - | Software/model issue |
| JetPack 6.x upgrade | `jetson-expert` | `nvidia-expert` | Flash first, then container compatibility |
| Performance varies wildly | `nvidia-expert` | `jetson-expert` | Profile first, then check thermal throttling |

### Proactive Agent Usage

ALWAYS consider using specialized agents when:
1. User mentions Jetson hardware or deployment -> Consider `jetson-expert`
2. User asks about AI/ML optimization -> Consider `nvidia-expert`
3. Troubleshooting involves both HW and SW -> Use both agents sequentially
4. Task is outside ROS2/Python expertise -> Use appropriate agent
5. Performance issues arise -> Start with `nvidia-expert`, escalate to `jetson-expert` if thermal
