"""
Comprehensive demonstration of the Perception Module.

This script demonstrates all capabilities of the perception module
and shows how it would be used in the actual agent.
"""

import sys
from src.perception.screen_capture import get_multimodal_context, ScreenCapture


def main():
    """Demonstrate perception module functionality."""
    print("\n" + "=" * 80)
    print(" PERCEPTION MODULE - COMPREHENSIVE DEMONSTRATION")
    print("=" * 80)
    
    print("\n📸 Capturing current UI state...")
    print("-" * 80)
    
    # Capture multimodal context
    screenshot, ui_tree = get_multimodal_context()
    
    # Display screenshot information
    print(f"\n✓ Visual Capture Complete:")
    print(f"  - Resolution: {screenshot.size[0]}x{screenshot.size[1]} pixels")
    print(f"  - Color Mode: {screenshot.mode}")
    print(f"  - Format: PIL Image object")
    
    # Display UI tree information
    print(f"\n✓ Structural Capture Complete:")
    print(f"  - UI Tree Length: {len(ui_tree):,} characters")
    print(f"  - Lines in Tree: {len(ui_tree.splitlines())}")
    
    # Show sample of UI tree
    print("\n📋 UI Tree Sample (first 1000 characters):")
    print("-" * 80)
    lines = ui_tree.splitlines()
    char_count = 0
    for line in lines:
        if char_count + len(line) > 1000:
            break
        print(line)
        char_count += len(line) + 1
    print("...")
    print("-" * 80)
    
    # Demonstrate class-based usage
    print("\n🔧 Testing ScreenCapture Class Methods:")
    print("-" * 80)
    
    sc = ScreenCapture()
    
    # Test individual methods
    img1 = sc.capture_screen()
    print(f"  ✓ capture_screen(): {img1.size[0]}x{img1.size[1]}")
    
    img2, tree2 = sc.get_context()
    print(f"  ✓ get_context(): {img2.size[0]}x{img2.size[1]}, {len(tree2):,} chars")
    
    prepared = sc.prepare_for_gemini(img1)
    print(f"  ✓ prepare_for_gemini(): {prepared.size[0]}x{prepared.size[1]}")
    
    # Show how this would be used in the agent
    print("\n💡 Usage in Agent Loop:")
    print("-" * 80)
    print("""
    # In the orchestration/agent_loop.py:
    
    perception = ScreenCapture()
    
    # At each iteration:
    screenshot, ui_tree = perception.get_context()
    
    # Send to Gemini:
    response = gemini_core.generate_response(
        prompt=f"Current task: {user_command}\\n\\nUI Elements:\\n{ui_tree}",
        image=screenshot
    )
    
    # Parse response and execute actions...
    """)
    
    print("\n" + "=" * 80)
    print(" ✅ PERCEPTION MODULE READY FOR INTEGRATION")
    print("=" * 80)
    print("\nThe perception module can now:")
    print("  • Capture full-screen screenshots")
    print("  • Extract UI element hierarchy (UIA + Win32 backends)")
    print("  • Clean and format output for LLM consumption")
    print("  • Handle multiple window types and fallback scenarios")
    print("  • Provide multimodal context for reasoning")
    print("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
