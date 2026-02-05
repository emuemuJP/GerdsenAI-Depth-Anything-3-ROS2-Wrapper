# Contributing to Depth Anything 3 ROS2 Wrapper

Thank you for your interest in contributing to this project! This document provides guidelines and best practices for contributions.

## Code of Conduct

Please be respectful and professional in all interactions. We welcome contributions from developers of all skill levels.

## How to Contribute

### Reporting Bugs

When reporting bugs, please include:

1. Your system configuration:
   - OS version (Ubuntu 22.04, etc.)
   - ROS2 distribution (Humble)
   - CUDA version (if applicable)
   - GPU model (if applicable)

2. Steps to reproduce the issue

3. Expected vs. actual behavior

4. Relevant log output or error messages

5. Minimal code example if possible

### Suggesting Features

Feature requests are welcome! Please:

1. Check existing issues first to avoid duplicates
2. Clearly describe the use case
3. Explain why this feature would benefit the project
4. Consider camera-agnostic design principles

### Submitting Pull Requests

1. **Fork the repository**
2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes** following the code style guidelines below

4. **Add tests** for new functionality

5. **Update documentation** as needed

6. **Run tests** before submitting:
   ```bash
   colcon test --packages-select depth_anything_3_ros2
   colcon test-result --verbose
   ```

7. **Submit pull request** with clear description of changes

## Code Style Guidelines

### Python Code

This project follows **PEP 8** with these specifics:

- Line length: 88 characters (Black formatter default)
- Indentation: 4 spaces
- Use type hints for all function signatures
- Google-style docstrings for all public functions/classes

Example:
```python
def process_image(self, image: np.ndarray, normalize: bool = True) -> Dict[str, np.ndarray]:
    """
    Process input image and return depth estimation.

    Args:
        image: Input RGB image as numpy array (H, W, 3)
        normalize: Whether to normalize depth output

    Returns:
        Dictionary containing depth map and confidence

    Raises:
        ValueError: If image format is invalid
    """
    pass
```

### No Emojis

**IMPORTANT**: Do not use emojis anywhere in:
- Code comments
- Docstrings
- Log messages
- Documentation
- Variable/function names
- Git commit messages

Use clear, professional technical language instead.

### Naming Conventions

- **Classes**: `PascalCase` (e.g., `DepthAnything3Node`)
- **Functions/Methods**: `snake_case` (e.g., `process_image`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_MODEL_NAME`)
- **Private methods**: Prefix with `_` (e.g., `_load_model`)

### ROS2 Conventions

Follow standard ROS2 best practices:

- Use relative topic names with `~` prefix for namespacing
- Declare all parameters with types and defaults
- Use appropriate QoS profiles
- Follow REP-144 naming conventions
- Clean up resources in destructors

### Camera-Agnostic Design

**Critical**: All contributions must maintain camera-agnostic design:

- No camera-specific dependencies in core code
- No hardcoded camera brand logic
- Configuration via standard ROS2 parameters only
- Topic remapping for camera integration

Camera-specific code belongs ONLY in example launch files.

## Testing Guidelines

### Current Test Coverage - Help Wanted!

We need community help improving test coverage. The project migrated to a TensorRT/SharedMemory architecture, but tests haven't caught up yet.

**Current State:**

| Component | Tests | Coverage | Status |
|-----------|-------|----------|--------|
| `DA3InferenceWrapper` (PyTorch fallback) | 6 | ~90% | Good |
| `SharedMemoryInferenceFast` (production) | 0 | 0% | **Help wanted** |
| `SharedMemoryInference` (IPC fallback) | 0 | 0% | **Help wanted** |
| `DepthAnything3Node` (basic init) | 5 | ~40% | Needs work |
| `DepthAnything3Node` (SharedMemory) | 0 | 0% | **Help wanted** |
| `jetson_detector.py` | 22 | ~90% | Good |
| `utils.py` | 0 | 0% | **Help wanted** |

### Priority Contributions Needed

**High Priority - Production Code Paths:**

1. **SharedMemory Backend Tests** - The production inference path has no tests!
   - Create `test/test_shared_memory_fast.py`
   - Test `/dev/shm/da3` memmap initialization
   - Test status file polling and timeout handling
   - Mock `numpy.memmap` and `pathlib.Path`

2. **Node SharedMemory Integration**
   - Test `use_shared_memory=True` parameter handling
   - Test backend selection logic (Fast -> Standard -> PyTorch fallback)
   - Test behavior when TRT service is unavailable

**Medium Priority:**

3. **Utility Function Tests**
   - Create `test/test_utils.py`
   - Test `normalize_depth()`, `colorize_depth()`, `PerformanceMetrics`

4. **Error Handling Tests**
   - Test timeout conditions
   - Test malformed status files
   - Test missing shared memory directories

### Writing Tests

Example unit test structure:

```python
# test/test_shared_memory_fast.py
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

class TestSharedMemoryInferenceFast(unittest.TestCase):
    @patch('numpy.memmap')
    @patch.object(Path, 'exists', return_value=True)
    def test_initialization_with_existing_shm(self, mock_exists, mock_memmap):
        # Test that SharedMemoryInferenceFast initializes correctly
        pass

    def test_timeout_when_service_unavailable(self):
        # Test graceful timeout handling
        pass
```

### Running Tests

```bash
# Run all tests
colcon test --packages-select depth_anything_3_ros2
colcon test-result --verbose

# Run specific test file
python3 -m pytest test/test_inference.py -v

# Run with coverage (if pytest-cov installed)
python3 -m pytest test/ --cov=depth_anything_3_ros2 --cov-report=term-missing
```

### Test Coverage Goals

Realistic targets we're working toward:
- Production code paths (SharedMemory): >60%
- PyTorch fallback: >80% (currently met)
- Utility functions: >70%
- Error handling: Include failure cases for all backends

## Documentation

### Code Documentation

- All public classes and functions must have docstrings
- Include type hints
- Document exceptions that can be raised
- Explain non-obvious logic with inline comments

### README Updates

Update README.md when:
- Adding new features
- Changing parameters
- Adding new examples
- Modifying installation steps

### Changelog

Add entry to CHANGELOG.md (if exists) describing your changes.

## Commit Message Guidelines

Use clear, descriptive commit messages:

```
Add support for dynamic parameter reconfiguration

- Implement callback for parameter changes
- Add tests for parameter updates
- Update documentation with new feature

Fixes #123
```

Format:
1. Brief summary (50 chars or less)
2. Blank line
3. Detailed description
4. Reference related issues

## Development Setup

### Local Development Environment

```bash
# Clone repository
git clone https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper.git
cd GerdsenAI-Depth-Anything-3-ROS2-Wrapper

# Install dependencies
pip3 install -r requirements.txt

# Build package
cd ~/ros2_ws
colcon build --packages-select depth_anything_3_ros2

# Run tests
colcon test --packages-select depth_anything_3_ros2
```

### Pre-Commit Checks

Before committing, run:

```bash
# Format check (if using black)
black --check depth_anything_3_ros2/

# Lint check
flake8 depth_anything_3_ros2/

# Type check (if using mypy)
mypy depth_anything_3_ros2/

# Run tests
colcon test --packages-select depth_anything_3_ros2
```

## Release Process

For maintainers:

1. Update version in `package.xml` and `setup.py`
2. Update CHANGELOG.md
3. Create git tag: `git tag -a v1.x.x -m "Release v1.x.x"`
4. Push tag: `git push origin v1.x.x`

## Questions?

If you have questions about contributing:

1. Check existing documentation
2. Search closed issues/PRs
3. Open a GitHub Discussion
4. Ask in issue comments

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (MIT License).

---

Thank you for contributing to make this project better!
