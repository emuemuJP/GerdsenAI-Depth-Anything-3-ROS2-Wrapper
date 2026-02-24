"""
Primary launch file for Depth Anything 3 ROS2 node.

This launch file provides a fully configurable single-camera depth estimation setup.
All parameters can be overridden via command-line arguments.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for Depth Anything 3 node."""

    return LaunchDescription([
        # Camera topic configuration
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

        # Model configuration
        DeclareLaunchArgument(
            'model_name',
            default_value='depth-anything/DA3-BASE',
            description='Hugging Face model ID or local path. Options: '
                        'depth-anything/DA3-SMALL, depth-anything/DA3-BASE, '
                        'depth-anything/DA3-LARGE, depth-anything/DA3-GIANT, '
                        'depth-anything/DA3NESTED-GIANT-LARGE'
        ),
        DeclareLaunchArgument(
            'device',
            default_value='cuda',
            description='Inference device: cuda or cpu'
        ),
        DeclareLaunchArgument(
            'cache_dir',
            default_value='',
            description='Model cache directory (empty for default)'
        ),

        # Image processing parameters
        DeclareLaunchArgument(
            'inference_height',
            default_value='518',
            description='Height for inference (model input size)'
        ),
        DeclareLaunchArgument(
            'inference_width',
            default_value='518',
            description='Width for inference (model input size)'
        ),
        DeclareLaunchArgument(
            'input_encoding',
            default_value='bgr8',
            description='Expected input image encoding (bgr8 or rgb8)'
        ),
        DeclareLaunchArgument(
            'keep_image_size',
            default_value='false',
            description='Resize output depth map to match input image resolution'
        ),

        # Output configuration
        DeclareLaunchArgument(
            'normalize_depth',
            default_value='true',
            description='Normalize depth to [0, 1] range'
        ),
        DeclareLaunchArgument(
            'publish_colored',
            default_value='true',
            description='Publish colorized depth visualization'
        ),
        DeclareLaunchArgument(
            'publish_confidence',
            default_value='true',
            description='Publish confidence map'
        ),
        DeclareLaunchArgument(
            'colormap',
            default_value='turbo',
            description='Colormap for depth visualization: turbo, viridis, plasma, '
                        'magma, jet, etc.'
        ),

        # Performance parameters
        DeclareLaunchArgument(
            'queue_size',
            default_value='1',
            description='Subscriber queue size (1 for latest frame only)'
        ),
        DeclareLaunchArgument(
            'processing_threads',
            default_value='1',
            description='Number of processing threads'
        ),

        # Logging parameters
        DeclareLaunchArgument(
            'log_inference_time',
            default_value='false',
            description='Log per-frame inference time and performance metrics'
        ),

        # Jetson TRT mode (host-container split)
        DeclareLaunchArgument(
            'use_shared_memory',
            default_value='false',
            description='Use shared memory for host TRT service communication (Jetson only)'
        ),

        # Node
        Node(
            package='depth_anything_3_ros2',
            executable='depth_anything_3_node',
            name='depth_anything_3',
            namespace=LaunchConfiguration('namespace'),
            output='screen',
            remappings=[
                ('~/image_raw', LaunchConfiguration('image_topic')),
                ('~/camera_info', LaunchConfiguration('camera_info_topic')),
            ],
            parameters=[{
                'model_name': LaunchConfiguration('model_name'),
                'device': LaunchConfiguration('device'),
                'cache_dir': LaunchConfiguration('cache_dir'),
                'inference_height': LaunchConfiguration('inference_height'),
                'inference_width': LaunchConfiguration('inference_width'),
                'input_encoding': LaunchConfiguration('input_encoding'),
                'keep_image_size': LaunchConfiguration('keep_image_size'),
                'normalize_depth': LaunchConfiguration('normalize_depth'),
                'publish_colored': LaunchConfiguration('publish_colored'),
                'publish_confidence': LaunchConfiguration('publish_confidence'),
                'colormap': LaunchConfiguration('colormap'),
                'queue_size': LaunchConfiguration('queue_size'),
                'processing_threads': LaunchConfiguration('processing_threads'),
                'log_inference_time': LaunchConfiguration('log_inference_time'),
                'use_shared_memory': LaunchConfiguration('use_shared_memory'),
            }]
        ),
    ])
