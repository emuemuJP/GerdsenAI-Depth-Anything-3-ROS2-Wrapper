"""Setup script for depth_anything_3_ros2 package."""

import os
from glob import glob

from setuptools import setup  # type: ignore[import-untyped]

package_name = 'depth_anything_3_ros2'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Node scripts (installed to lib/<package>/ for ros2 launch
        # compatibility)
        (os.path.join('lib', package_name),
            glob('depth_anything_3_ros2/scripts/*')),
        # Launch files
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'launch', 'examples'),
            glob('launch/examples/*.launch.py')),
        # Config files
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
        (os.path.join('share', package_name, 'config',
                      'camera_configs'),
            glob('config/camera_configs/*.yaml')),
        # RViz config
        (os.path.join('share', package_name, 'rviz'),
            glob('rviz/*.rviz')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='your@email.com',
    description=(
        'Camera-agnostic ROS2 wrapper for Depth Anything 3 '
        'monocular depth estimation'
    ),
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'depth_anything_3_node = '
            'depth_anything_3_ros2.depth_anything_3_node:main',
        ],
    },
)
