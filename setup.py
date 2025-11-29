"""Setup script for depth_anything_3_ros2 package."""

from setuptools import setup
from setuptools.command.install import install
import os
from glob import glob

package_name = 'depth_anything_3_ros2'


class PostInstallCommand(install):
    """Post-installation command to create lib/<package_name> directory."""

    def run(self):
        install.run(self)
        # Create lib/<package_name> directory for ROS2 launch compatibility
        lib_dir = os.path.join(self.install_lib, '..', '..', '..', 'lib', package_name)
        bin_dir = os.path.join(self.install_lib, '..', '..', '..', 'bin')

        try:
            os.makedirs(lib_dir, exist_ok=True)
            # Create symlinks to executables
            for executable in ['depth_anything_3_node', 'depth_anything_3_node_optimized']:
                src = os.path.join(bin_dir, executable)
                dst = os.path.join(lib_dir, executable)
                if os.path.exists(src) and not os.path.exists(dst):
                    os.symlink(os.path.relpath(src, lib_dir), dst)
        except Exception as e:
            print(f"Warning: Could not create lib/{package_name} symlinks: {e}")


setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Launch files
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'launch', 'examples'),
            glob('launch/examples/*.launch.py')),
        # Config files
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
        (os.path.join('share', package_name, 'config', 'camera_configs'),
            glob('config/camera_configs/*.yaml')),
        # RViz config
        (os.path.join('share', package_name, 'rviz'),
            glob('rviz/*.rviz')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='your@email.com',
    description='Camera-agnostic ROS2 wrapper for Depth Anything 3 monocular depth estimation',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'depth_anything_3_node = depth_anything_3_ros2.depth_anything_3_node:main',
            'depth_anything_3_node_optimized = depth_anything_3_ros2.depth_anything_3_node_optimized:main',
        ],
    },
    cmdclass={
        'install': PostInstallCommand,
    },
)
