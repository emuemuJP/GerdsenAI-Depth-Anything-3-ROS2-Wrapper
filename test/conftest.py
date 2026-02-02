"""
Pytest configuration for depth_anything_3_ros2 tests.

Provides fixtures and markers for handling ROS2 availability.
"""

import pytest

# Detect ROS2 availability at collection time
try:
    import rclpy
    from sensor_msgs.msg import Image
    from std_msgs.msg import Header

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    rclpy = None
    Image = None
    Header = None


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "requires_ros2: mark test as requiring ROS2 installation"
    )


# Skip marker for tests requiring ROS2
requires_ros2 = pytest.mark.skipif(
    not ROS2_AVAILABLE,
    reason="ROS2 not available (rclpy not installed or environment not sourced)",
)


@pytest.fixture(scope="module")
def ros2_context():
    """
    Initialize ROS2 context for a test module.

    Yields:
        True if ROS2 is available and initialized, False otherwise.
    """
    if not ROS2_AVAILABLE:
        yield False
        return

    rclpy.init()
    try:
        yield True
    finally:
        rclpy.shutdown()
