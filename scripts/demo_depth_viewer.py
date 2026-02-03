#!/usr/bin/env python3
"""
Depth Anything 3 - Live Depth Viewer Demo

This script displays a live side-by-side view of:
- Left: Original camera feed
- Right: Colorized depth estimation

Requirements:
- TRT inference service running (started automatically)
- Camera connected (/dev/video0)
- Display connected to Jetson

Usage:
    python3 scripts/demo_depth_viewer.py

Controls:
    q - Quit
    s - Save current frame
    f - Toggle FPS display
"""

import cv2
import numpy as np
import subprocess
import signal
import sys
import time
import os
from pathlib import Path

# ROS2 imports
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import Image
    from cv_bridge import CvBridge
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    print("ROS2 not available - running in standalone mode")


class DepthViewer:
    """Live depth visualization viewer."""

    def __init__(self):
        self.bridge = CvBridge() if ROS2_AVAILABLE else None
        self.latest_rgb = None
        self.latest_depth = None
        self.fps_display = True
        self.frame_count = 0
        self.start_time = time.time()
        self.last_fps = 0
        self.running = True

        # Window setup
        self.window_name = "Depth Anything 3 - Live Demo"
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1280, 480)

    def rgb_callback(self, msg):
        """Handle incoming RGB image."""
        try:
            self.latest_rgb = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            print(f"RGB conversion error: {e}")

    def depth_callback(self, msg):
        """Handle incoming depth image."""
        try:
            self.latest_depth = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            self.frame_count += 1
        except Exception as e:
            print(f"Depth conversion error: {e}")

    def calculate_fps(self):
        """Calculate current FPS."""
        elapsed = time.time() - self.start_time
        if elapsed > 1.0:
            self.last_fps = self.frame_count / elapsed
            self.frame_count = 0
            self.start_time = time.time()
        return self.last_fps

    def create_display(self):
        """Create side-by-side display image."""
        if self.latest_rgb is None and self.latest_depth is None:
            # Show waiting message
            display = np.zeros((480, 1280, 3), dtype=np.uint8)
            cv2.putText(display, "Waiting for camera and depth data...",
                       (400, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            return display

        # Target size for each panel
        panel_width, panel_height = 640, 480

        # Process RGB
        if self.latest_rgb is not None:
            rgb = cv2.resize(self.latest_rgb, (panel_width, panel_height))
        else:
            rgb = np.zeros((panel_height, panel_width, 3), dtype=np.uint8)
            cv2.putText(rgb, "No RGB", (250, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (128, 128, 128), 2)

        # Process Depth
        if self.latest_depth is not None:
            depth = cv2.resize(self.latest_depth, (panel_width, panel_height))
        else:
            depth = np.zeros((panel_height, panel_width, 3), dtype=np.uint8)
            cv2.putText(depth, "No Depth", (230, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (128, 128, 128), 2)

        # Add labels
        cv2.putText(rgb, "Camera", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(depth, "Depth (TensorRT)", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

        # Combine side by side
        display = np.hstack([rgb, depth])

        # Add FPS if enabled
        if self.fps_display:
            fps = self.calculate_fps()
            cv2.putText(display, f"FPS: {fps:.1f}", (1100, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        # Add instructions
        cv2.putText(display, "Q: Quit | S: Save | F: Toggle FPS", (10, 465),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        return display

    def save_frame(self):
        """Save current frame to disk."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_dir = Path("demo_captures")
        save_dir.mkdir(exist_ok=True)

        if self.latest_rgb is not None:
            cv2.imwrite(str(save_dir / f"rgb_{timestamp}.jpg"), self.latest_rgb)
        if self.latest_depth is not None:
            cv2.imwrite(str(save_dir / f"depth_{timestamp}.jpg"), self.latest_depth)

        print(f"Saved frames to {save_dir}/")

    def run(self):
        """Main display loop."""
        print("\n" + "="*50)
        print("Depth Anything 3 - Live Demo")
        print("="*50)
        print("Controls:")
        print("  Q - Quit")
        print("  S - Save current frame")
        print("  F - Toggle FPS display")
        print("="*50 + "\n")

        while self.running:
            display = self.create_display()
            cv2.imshow(self.window_name, display)

            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                self.running = False
            elif key == ord('s'):
                self.save_frame()
            elif key == ord('f'):
                self.fps_display = not self.fps_display

        cv2.destroyAllWindows()


def start_trt_service():
    """Start the TRT inference service if not running."""
    # Check if already running
    result = subprocess.run(
        ["pgrep", "-f", "trt_inference_service"],
        capture_output=True
    )
    if result.returncode == 0:
        print("[OK] TRT inference service already running")
        return None

    print("[...] Starting TRT inference service...")

    # Find script directory
    script_dir = Path(__file__).parent.parent
    engine_path = script_dir / "models" / "tensorrt" / "da3-small-fp16.engine"
    service_script = script_dir / "scripts" / "trt_inference_service.py"

    if not engine_path.exists():
        print(f"[ERROR] TensorRT engine not found: {engine_path}")
        print("Run: bash scripts/deploy_jetson.sh --host-trt")
        sys.exit(1)

    # Clear shared directory
    shared_dir = Path("/tmp/da3_shared")
    shared_dir.mkdir(exist_ok=True)
    for f in shared_dir.glob("*"):
        f.unlink()

    # Start service
    proc = subprocess.Popen(
        ["python3", str(service_script),
         "--engine", str(engine_path),
         "--poll-interval", "0.001"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Wait for service to be ready
    status_file = shared_dir / "status"
    for _ in range(50):  # 5 second timeout
        time.sleep(0.1)
        if status_file.exists():
            status = status_file.read_text().strip()
            if status.startswith("ready") or status.startswith("complete"):
                print("[OK] TRT inference service started")
                return proc

    print("[WARN] TRT service may not be ready")
    return proc


def main():
    """Main entry point."""
    trt_proc = None

    def signal_handler(signum, frame):
        print("\nShutting down...")
        if trt_proc:
            trt_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start TRT service
    trt_proc = start_trt_service()

    if not ROS2_AVAILABLE:
        print("\n[ERROR] ROS2 is required for this demo.")
        print("Run inside the Docker container:")
        print("  docker exec -it da3_ros2_jetson bash")
        print("  python3 /ros2_ws/src/depth_anything_3_ros2/scripts/demo_depth_viewer.py")
        sys.exit(1)

    # Initialize ROS2
    rclpy.init()

    # Create viewer
    viewer = DepthViewer()

    # Create ROS2 node
    node = rclpy.create_node('depth_viewer')

    qos = QoSProfile(
        reliability=ReliabilityPolicy.BEST_EFFORT,
        history=HistoryPolicy.KEEP_LAST,
        depth=1
    )

    # Subscribe to topics
    node.create_subscription(
        Image, '/camera/image_raw', viewer.rgb_callback, qos)
    node.create_subscription(
        Image, '/depth_anything_3/depth_colored', viewer.depth_callback, qos)

    print("[OK] Subscribed to camera and depth topics")
    print("[...] Waiting for data (make sure camera and depth nodes are running)...\n")

    # Spin in background thread
    import threading
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    # Run viewer
    try:
        viewer.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
        if trt_proc:
            trt_proc.terminate()


if __name__ == "__main__":
    main()
