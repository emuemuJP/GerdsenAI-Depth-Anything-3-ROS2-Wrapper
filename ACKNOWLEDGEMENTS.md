# Acknowledgements

This project builds upon the work of several organizations and open-source projects. We extend our gratitude to the following:

## Core Technology

### Depth Anything 3

This ROS2 wrapper is built around Depth Anything 3, developed by the ByteDance Seed Team. Their state-of-the-art work on monocular depth estimation has made this project possible.

- **Team**: ByteDance Seed Team
- **Paper**: "Depth Anything 3: A New Foundation for Metric and Relative Depth Estimation" (arXiv:2511.10647)
- **Repository**: [ByteDance-Seed/Depth-Anything-3](https://github.com/ByteDance-Seed/Depth-Anything-3)
- **Project Page**: [depth-anything-3.github.io](https://depth-anything-3.github.io/)

### NVIDIA TensorRT

Production inference is powered by NVIDIA TensorRT 10.3, enabling real-time performance (23+ FPS) on Jetson platforms.

- **Website**: [developer.nvidia.com/tensorrt](https://developer.nvidia.com/tensorrt)
- **Version**: TensorRT 10.3+ (required for DINOv2 backbone support)

### Jetson Containers

Docker base images for Jetson deployment are provided by dusty-nv's jetson-containers project.

- **Repository**: [dusty-nv/jetson-containers](https://github.com/dusty-nv/jetson-containers)
- **Base Image**: `dustynv/ros:humble-desktop-l4t-r36.4.0`

## Frameworks and Libraries

### ROS2

This project is built on the Robot Operating System 2 (ROS2) framework, developed and maintained by Open Robotics.

- **Website**: [ros.org](https://www.ros.org/)
- **Distribution**: ROS2 Humble Hawksbill

### PyTorch

PyTorch is used as a library dependency for the DA3 Python package (development/testing only; production uses TensorRT).

- **Website**: [pytorch.org](https://pytorch.org/)

### Hugging Face

Model weights and ONNX exports are hosted on Hugging Face Hub.

- **Website**: [huggingface.co](https://huggingface.co/)
- **Models**: [huggingface.co/depth-anything](https://huggingface.co/depth-anything)
- **ONNX**: [huggingface.co/onnx-community/depth-anything-v3-small](https://huggingface.co/onnx-community/depth-anything-v3-small)

### OpenCV

Image processing capabilities are provided by OpenCV (Open Source Computer Vision Library).

- **Website**: [opencv.org](https://opencv.org/)

## Contributors

We thank all contributors who have helped improve this project through bug reports, feature suggestions, and code contributions. See the [Contributors](https://github.com/GerdsenAI/GerdsenAI-Depth-Anything-3-ROS2-Wrapper/graphs/contributors) page for a full list.

## GerdsenAI

Developed and maintained by GerdsenAI.

- **GitHub**: [GerdsenAI](https://github.com/GerdsenAI)

## Special Thanks

- The open-source robotics community for their continuous support and feedback
- All users who have tested and provided feedback on this wrapper

---

If you believe your work should be acknowledged here, please open an issue or submit a pull request.