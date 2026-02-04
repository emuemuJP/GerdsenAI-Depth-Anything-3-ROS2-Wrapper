# CLAUDE.md

## Always Follow These Guidelines

## Environment Detection (Do This First)

Before attempting Jetson access or system commands, determine your environment:

### Check Available Tools

1. **MCP Tools**: Check if OSA Tools, Windows MCP, or SSH MCP tools are available
2. **Local Environment**: Test if `~/.ssh/jetson_j4012` exists and `10.69.7.112` is reachable

### Environment-Specific Behavior

| Environment | SSH Key Exists | Network Reachable | Action |
|-------------|----------------|-------------------|--------|
| Claude Code (local) | Yes | Yes | Use SSH commands directly |
| Claude Cowork (cloud) | No | No | Use MCP tools or guide user |
| Docker container | No | Maybe | Exit container, run on host |

### If Running in Cowork (Cloud)

When SSH key or network is unavailable:

1. **Check for MCP tools** that provide remote access (SSH MCP, terminal MCP)
2. **Guide the user** to run commands locally via Claude Code
3. **Provide commands** for user to copy/paste into their local terminal
4. **Do NOT repeatedly attempt** SSH commands that will fail

## Jetson SSH Quick Reference (Local Claude Code Only)

These commands work from the user's local machine with Claude Code:

- **Host**: `10.69.7.112` (Jetson device on local network)
- **User**: `gerdsenai`
- **Identity file**: `~/.ssh/jetson_j4012`

```bash
# Quick connectivity test (run this first)
ping -c 1 10.69.7.112 && ls ~/.ssh/jetson_j4012

# SSH to Jetson
ssh -i ~/.ssh/jetson_j4012 gerdsenai@10.69.7.112
```

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

This file provides guidance to Claude Code and Claude Cowork when working with this repository.

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

# Run live demo (one-click from repo root)
./run.sh
```

## Jetson Deployment

Jetson Orin AGX is available at `10.69.7.112`. SSH requires identity file.

```bash
# SSH to Jetson (identity file required)
ssh -i ~/.ssh/jetson_j4012 gerdsenai@10.69.7.112

# Deploy via git clone (preferred - maintains git history)
ssh -i ~/.ssh/jetson_j4012 gerdsenai@10.69.7.112 \
  "git clone https://github.com/GerdsenAI/Depth-Anything-3-ROS2-Wrapper.git ~/depth_anything_3_ros2"

# Or deploy via SCP (no git history)
scp -i ~/.ssh/jetson_j4012 -r . gerdsenai@10.69.7.112:~/depth_anything_3_ros2/

# Run commands remotely
ssh -i ~/.ssh/jetson_j4012 gerdsenai@10.69.7.112 "cd ~/depth_anything_3_ros2 && <command>"
```

### One-Click Demo (Recommended)

Use the `run.sh` script at repo root which handles everything:

```bash
# On Jetson, after cloning:
cd ~/depth_anything_3_ros2
./run.sh                      # Auto-detect camera, build if needed
./run.sh --camera /dev/video0 # Specify camera
./run.sh --no-display         # Headless mode (SSH)
./run.sh --rebuild            # Force rebuild Docker
```

### JetPack / L4T Version Notes

| L4T Version | OpenCV | cuDNN | Base Image                              |
|-------------|--------|-------|-----------------------------------------|
| r36.2.0     | 4.8.1  | 8.x   | dustynv/ros:humble-desktop-l4t-r36.2.0  |
| r36.4.0     | 4.10.0 | 9.x   | dustynv/ros:humble-desktop-l4t-r36.4.0  |

**Important**: The `humble-pytorch` variant does NOT exist for r36.x. Use `humble-desktop` instead.

## Docker Build Known Issues (Jetson)

### 1. pip.conf Points to Unreliable Server

dustynv base images configure pip to use `jetson.webredirect.org` which may be unreliable.
**Fix**: Use `--index-url https://pypi.org/simple/` explicitly for pip installs.

### 2. OpenCV Version Check

The Dockerfile validates OpenCV version. Supported versions:

- 4.5.x (apt packages)
- 4.8.x (L4T r36.2)
- 4.10.x (L4T r36.4)

### 3. cuDNN Version Mismatch

L4T r36.4.0 ships with cuDNN 9.x, but some PyTorch wheels expect cuDNN 8.
**Fix**: For host-container TRT architecture, container doesn't need CUDA-accelerated PyTorch.
Use CPU-only torchvision in container since TRT inference runs on host.

### 4. Base Image Selection

```dockerfile
# WRONG - doesn't exist for r36.x
FROM dustynv/ros:humble-pytorch-l4t-r36.4.0

# CORRECT
FROM dustynv/ros:humble-desktop-l4t-r36.4.0
```

## Host-Container TensorRT Architecture

Due to broken TensorRT Python bindings in containers, we use a split architecture:

- **Host**: Runs `scripts/trt_inference_service.py` (TensorRT inference)
- **Container**: Runs ROS2 nodes (camera driver, depth publisher)
- **Communication**: File-based IPC via `/tmp/da3_shared/`

| File         | Direction          | Format                                   |
|--------------|--------------------|------------------------------------------|
| `input.npy`  | Container -> Host  | float32 [1,1,3,518,518]                  |
| `output.npy` | Host -> Container  | float32 [1,518,518]                      |
| `request`    | Container -> Host  | Timestamp signal                         |
| `status`     | Host -> Container  | "ready", "complete:time", "error:msg"    |

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

| Agent           | Domain   | Use When                                                                         |
|-----------------|----------|----------------------------------------------------------------------------------|
| `jetson-expert` | Hardware | Module selection, flashing, BSP, carrier boards, GPIO/CSI, thermal, boot issues  |
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

| Scenario                   | Primary Agent   | Secondary Agent  | Reason                                         |
|----------------------------|-----------------|------------------|------------------------------------------------|
| Slow inference on Orin NX  | `nvidia-expert` | `jetson-expert`  | Software first, then check thermal/power       |
| Container can't access GPU | `nvidia-expert` | `jetson-expert`  | Runtime config first, then driver/L4T check    |
| CSI camera not detected    | `jetson-expert` | -                | Hardware/device tree issue                     |
| TensorRT build fails       | `nvidia-expert` | -                | Software/model issue                           |
| JetPack 6.x upgrade        | `jetson-expert` | `nvidia-expert`  | Flash first, then container compatibility      |
| Performance varies wildly  | `nvidia-expert` | `jetson-expert`  | Profile first, then check thermal throttling   |

### Proactive Agent Usage

ALWAYS consider using specialized agents when:

1. User mentions Jetson hardware or deployment -> Consider `jetson-expert`
2. User asks about AI/ML optimization -> Consider `nvidia-expert`
3. Troubleshooting involves both HW and SW -> Use both agents sequentially
4. Task is outside ROS2/Python expertise -> Use appropriate agent
5. Performance issues arise -> Start with `nvidia-expert`, escalate to `jetson-expert` if thermal