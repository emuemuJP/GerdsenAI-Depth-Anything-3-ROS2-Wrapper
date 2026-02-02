"""
Demo launch file for Depth Anything V3.

This is a simplified launch file designed for demos and quick testing.
It combines camera input with depth estimation and enables all visualization options.

Usage:
    # With USB camera (auto-detect)
    ros2 launch depth_anything_3_ros2 demo.launch.py

    # With specific camera device
    ros2 launch depth_anything_3_ros2 demo.launch.py video_device:=/dev/video2

    # With existing image topic (no camera launch)
    ros2 launch depth_anything_3_ros2 demo.launch.py use_camera:=false image_topic:=/my/camera/image

Features:
    - Automatic USB camera setup via v4l2_camera
    - All visualization outputs enabled (depth, colored, confidence)
    - Performance logging enabled by default
    - Pre-configured for demo display
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for demo."""

    return LaunchDescription([
        # Camera configuration
        DeclareLaunchArgument(
            'use_camera',
            default_value='true',
            description='Launch v4l2_camera node (set false if using external camera)'
        ),
        DeclareLaunchArgument(
            'video_device',
            default_value='/dev/video0',
            description='Video device path for USB camera'
        ),
        DeclareLaunchArgument(
            'image_width',
            default_value='640',
            description='Camera image width'
        ),
        DeclareLaunchArgument(
            'image_height',
            default_value='480',
            description='Camera image height'
        ),

        # Depth estimation configuration
        DeclareLaunchArgument(
            'image_topic',
            default_value='/camera/image_raw',
            description='Input image topic'
        ),
        DeclareLaunchArgument(
            'model_name',
            default_value='depth-anything/DA3-SMALL',
            description='DA3 model (DA3-SMALL recommended for demo)'
        ),
        DeclareLaunchArgument(
            'device',
            default_value='cuda',
            description='Inference device (cuda or cpu)'
        ),
        DeclareLaunchArgument(
            'colormap',
            default_value='turbo',
            description='Colormap for depth visualization'
        ),

        # Launch v4l2_camera node (conditional)
        Node(
            package='v4l2_camera',
            executable='v4l2_camera_node',
            name='v4l2_camera',
            namespace='camera',
            condition=IfCondition(LaunchConfiguration('use_camera')),
            parameters=[{
                'video_device': LaunchConfiguration('video_device'),
                'image_size': [
                    LaunchConfiguration('image_width'),
                    LaunchConfiguration('image_height')
                ],
                'camera_frame_id': 'camera_optical_frame',
            }],
            output='screen',
        ),

        # Launch Depth Anything 3 node
        Node(
            package='depth_anything_3_ros2',
            executable='depth_anything_3_node',
            name='depth_anything_3',
            namespace='camera',
            output='screen',
            remappings=[
                ('~/image_raw', LaunchConfiguration('image_topic')),
                ('~/camera_info', '/camera/camera_info'),
            ],
            parameters=[{
                'model_name': LaunchConfiguration('model_name'),
                'device': LaunchConfiguration('device'),
                # Visualization options - all enabled for demo
                'normalize_depth': True,
                'publish_colored': True,
                'publish_confidence': True,
                'colormap': LaunchConfiguration('colormap'),
                # Performance logging - enabled for demo
                'log_inference_time': True,
            }]
        ),
    ])
