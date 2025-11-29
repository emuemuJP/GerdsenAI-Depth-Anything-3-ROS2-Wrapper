"""
Platform-Adaptive Launch File for Depth Anything 3 ROS2 Wrapper.

Automatically loads platform-specific configurations for NVIDIA Jetson devices.
Supports: Orin AGX, Orin Nano, Xavier NX, Thor

Usage:
    # Orin AGX (Quality-optimized, >30 FPS)
    ros2 launch depth_anything_3_ros2 performance.launch.py \
        platform:=orin_agx \
        image_topic:=/camera/image_raw

    # Orin Nano (Efficiency-optimized)
    ros2 launch depth_anything_3_ros2 performance.launch.py \
        platform:=orin_nano \
        image_topic:=/camera/image_raw

    # Auto-detect platform (experimental)
    ros2 launch depth_anything_3_ros2 performance.launch.py \
        platform:=auto \
        image_topic:=/camera/image_raw
"""

import os
import yaml
from pathlib import Path
from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def load_platform_config(platform_name: str) -> dict:
    """Load platform configuration from YAML file."""
    pkg_share = get_package_share_directory('depth_anything_3_ros2')
    config_path = Path(pkg_share) / 'config' / 'platforms' / f'{platform_name}.yaml'
    
    if not config_path.exists():
        raise FileNotFoundError(
            f"Platform config not found: {config_path}\n"
            f"Available platforms: orin_agx, orin_nano, xavier_nx, thor"
        )
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config


def auto_detect_platform() -> str:
    """Auto-detect Jetson platform (experimental)."""
    try:
        # Try to read from /etc/nv_tegra_release
        tegra_info_path = Path('/etc/nv_tegra_release')
        if tegra_info_path.exists():
            content = tegra_info_path.read_text()
            if 'ORIN' in content.upper():
                # Try to distinguish between AGX and Nano
                # This is a simplified heuristic
                import subprocess
                result = subprocess.run(
                    ['cat', '/proc/meminfo'], 
                    capture_output=True, 
                    text=True
                )
                if 'MemTotal' in result.stdout:
                    # Parse memory size
                    for line in result.stdout.split('\n'):
                        if 'MemTotal' in line:
                            mem_kb = int(line.split()[1])
                            mem_gb = mem_kb / (1024 ** 2)
                            
                            if mem_gb > 50:  # AGX has 64GB
                                return 'orin_agx'
                            else:  # Nano has 8GB
                                return 'orin_nano'
            elif 'XAVIER' in content.upper():
                return 'xavier_nx'
    except Exception as e:
        print(f"Warning: Auto-detection failed: {e}")
    
    # Default fallback
    print("Warning: Could not auto-detect platform, defaulting to orin_agx")
    return 'orin_agx'


def launch_setup(context, *args, **kwargs):
    """Setup launch based on platform configuration."""
    
    # Get platform from launch argument
    platform_arg = LaunchConfiguration('platform').perform(context)
    
    # Auto-detect if requested
    if platform_arg == 'auto':
        platform_name = auto_detect_platform()
        print(f"Auto-detected platform: {platform_name}")
    else:
        platform_name = platform_arg
    
    # Load platform config
    try:
        config = load_platform_config(platform_name)
        print(f"Loaded config for platform: {platform_name}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return []
    
    # Extract parameters from config
    model_config = config['model']
    resolution = config['resolution']
    gpu_config = config['gpu']
    output_config = config['output']
    perf_config = config['performance']
    
    # Get other launch arguments
    image_topic = LaunchConfiguration('image_topic')
    camera_info_topic = LaunchConfiguration('camera_info_topic')
    namespace_arg = LaunchConfiguration('namespace')
    trt_model_path = LaunchConfiguration('trt_model_path')
    
    # Create node with platform-specific parameters
    node = Node(
        package='depth_anything_3_ros2',
        executable='depth_anything_3_node_optimized',
        name=f'depth_anything_3_{platform_name}',
        namespace=namespace_arg,
        output='screen',
        remappings=[
            ('~/image_raw', image_topic),
            ('~/camera_info', camera_info_topic),
        ],
        parameters=[{
            # Model configuration
            'model_name': model_config['name'],
            'backend': model_config['backend'],
            'device': 'cuda',
            'trt_model_path': trt_model_path,
            
            # Resolution
            'model_input_height': resolution['model_input_height'],
            'model_input_width': resolution['model_input_width'],
            'output_height': resolution['output_height'],
            'output_width': resolution['output_width'],
            
            # GPU optimization
            'enable_upsampling': gpu_config['enable_upsampling'],
            'upsample_mode': gpu_config['upsample_mode'],
            'use_cuda_streams': gpu_config['use_cuda_streams'],
            
            # Output configuration
            'normalize_depth': output_config['normalize_depth'],
            'publish_colored': output_config['publish_colored'],
            'publish_confidence': output_config['publish_confidence'],
            'colormap': output_config['colormap'],
            'async_colorization': output_config['async_colorization'],
            'check_subscribers': output_config['check_subscribers'],
            
            # Performance
            'queue_size': perf_config['queue_size'],
            'log_inference_time': perf_config['log_inference_time'],
        }]
    )
    
    return [node]


def generate_launch_description():
    """Generate launch description with platform selection."""
    
    return LaunchDescription([
        # Platform selection
        DeclareLaunchArgument(
            'platform',
            default_value='orin_agx',
            description='Platform: orin_agx, orin_nano, xavier_nx, thor, auto'
        ),
        
        # Camera configuration
        DeclareLaunchArgument(
            'image_topic',
            default_value='/camera/image_raw',
            description='Input image topic from camera'
        ),
        DeclareLaunchArgument(
            'camera_info_topic',
            default_value='/camera/camera_info',
            description='Input camera info topic'
        ),
        DeclareLaunchArgument(
            'namespace',
            default_value='',
            description='Namespace for the node'
        ),
        
        # TensorRT model path (optional override)
        DeclareLaunchArgument(
            'trt_model_path',
            default_value='',
            description='Path to TensorRT model (overrides platform default)'
        ),
        
        # Execute launch setup
        OpaqueFunction(function=launch_setup)
    ])
