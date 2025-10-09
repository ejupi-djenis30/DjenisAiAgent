"""
Test script for the perception module.

This script demonstrates the functionality of the screen_capture module
by capturing a screenshot and UI tree.
"""

import sys
from src.perception.screen_capture import get_multimodal_context, ScreenCapture


def test_perception():
    """Test the perception module."""
    print("Testing Perception Module...")
    print("=" * 60)
    
    try:
        # Test the standalone function
        print("\n1. Testing get_multimodal_context() function...")
        screenshot, ui_tree = get_multimodal_context()
        
        print(f"   ✓ Screenshot captured: {screenshot.size[0]}x{screenshot.size[1]} pixels")
        print(f"   ✓ UI Tree length: {len(ui_tree)} characters")
        print("\n   First 500 characters of UI Tree:")
        print("   " + "-" * 56)
        print("   " + ui_tree[:500].replace('\n', '\n   '))
        if len(ui_tree) > 500:
            print("   ...")
        
        # Test the class-based approach
        print("\n2. Testing ScreenCapture class...")
        sc = ScreenCapture()
        
        # Test capture_screen method
        img = sc.capture_screen()
        print(f"   ✓ capture_screen(): {img.size[0]}x{img.size[1]} pixels")
        
        # Test get_context method
        img2, tree2 = sc.get_context()
        print(f"   ✓ get_context(): {img2.size[0]}x{img2.size[1]} pixels, {len(tree2)} chars")
        
        # Test prepare_for_gemini
        prepared = sc.prepare_for_gemini(img)
        print(f"   ✓ prepare_for_gemini(): {prepared.size[0]}x{prepared.size[1]} pixels")
        
        print("\n" + "=" * 60)
        print("✓ All perception tests passed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error during testing: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_perception()
