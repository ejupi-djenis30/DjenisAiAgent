"""
Extended test to show more UI tree output.
"""

from src.perception.screen_capture import get_multimodal_context

screenshot, ui_tree = get_multimodal_context()

print("=" * 80)
print("SCREENSHOT INFO:")
print(f"Size: {screenshot.size[0]}x{screenshot.size[1]} pixels")
print(f"Mode: {screenshot.mode}")
print()
print("=" * 80)
print("UI TREE (first 2000 characters):")
print("=" * 80)
print(ui_tree[:2000])
print("\n... (truncated)")
print()
print("=" * 80)
print(f"Total UI Tree Length: {len(ui_tree)} characters")
print("=" * 80)
