#!/usr/bin/env python3
"""
Quick validation script for Phase 1 PyTorch optimization.
Tests that the PIL bottleneck fix works correctly.
"""

import numpy as np
import time
import sys

def test_inference():
    """Test that inference works with NumPy arrays."""
    print("=" * 60)
    print("Phase 1 Validation: PIL Bottleneck Fix")
    print("=" * 60)
    
    # Import the optimized inference wrapper
    try:
        from depth_anything_3_ros2.da3_inference_optimized import DA3InferenceOptimized
        print("✓ Successfully imported DA3InferenceOptimized")
    except ImportError as e:
        print(f"✗ Failed to import: {e}")
        return False
    
    # Create a test image (640x480 RGB)
    test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    print(f"✓ Created test image: {test_image.shape}")
    
    # Test PyTorch backend
    try:
        print("\nInitializing PyTorch backend...")
        model = DA3InferenceOptimized(
            model_name="depth-anything/DA3-SMALL",
            backend="pytorch",
            device="cuda",
            model_input_size=(384, 384),
            enable_upsampling=True
        )
        print("✓ Model initialized")
    except Exception as e:
        print(f"✗ Model initialization failed: {e}")
        return False
    
    # Run inference
    try:
        print("\nRunning inference...")
        start = time.time()
        result = model.inference(
            test_image,
            return_confidence=True,
            output_size=(480, 640)
        )
        elapsed = time.time() - start
        
        print(f"✓ Inference completed in {elapsed*1000:.1f}ms")
        print(f"  - Depth shape: {result['depth'].shape}")
        print(f"  - Confidence shape: {result['confidence'].shape}")
        
        # Validate outputs
        assert result['depth'].shape == (480, 640), "Depth shape mismatch"
        assert result['confidence'].shape == (480, 640), "Confidence shape mismatch"
        print("✓ Output shapes validated")
        
    except Exception as e:
        print(f"✗ Inference failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    print("Phase 1 Validation: PASSED ✓")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_inference()
    sys.exit(0 if success else 1)
