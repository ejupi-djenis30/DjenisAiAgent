"""
Test script for AI-powered window identification fallback.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.automation.ui_automation import UIAutomationEngine

def test_window_enumeration():
    """Test getting all open windows."""
    print("=" * 60)
    print("Testing Window Enumeration")
    print("=" * 60)
    
    ui = UIAutomationEngine()
    
    print("\nGetting all open windows...")
    windows = ui.get_all_open_windows()
    
    print(f"\nFound {len(windows)} total windows")
    print("\nFiltering out system windows...")
    
    user_windows = [
        window for window in windows
        if window.get('title') and not ui._is_system_window(window.get('title', ''))
    ]
    
    print(f"Found {len(user_windows)} user windows:")
    print()
    
    for i, window in enumerate(user_windows[:20], 1):
        print(f"  {i:2}. {window.get('title')}")
    
    if len(user_windows) > 20:
        print(f"  ... and {len(user_windows) - 20} more")
    
    print()


def test_ai_window_identification():
    """Test AI-powered window identification."""
    print("=" * 60)
    print("Testing AI Window Identification")
    print("=" * 60)
    
    ui = UIAutomationEngine()
    
    # Test cases
    test_cases = [
        "Calculator",
        "Notepad",
        "Visual Studio Code",
        "Chrome",
        "Edge"
    ]
    
    print("\nTesting different window patterns...")
    print()
    
    for pattern in test_cases:
        print(f"Testing: '{pattern}'")
        print("-" * 40)
        
        result = ui._ai_identify_window(pattern)
        
        if result:
            print(f"✅ Successfully identified and focused window")
        else:
            print(f"⚠️  Could not identify matching window")
        
        print()


def test_focus_with_fallback():
    """Test complete focus_window with AI fallback."""
    print("=" * 60)
    print("Testing Complete Focus Flow with AI Fallback")
    print("=" * 60)
    
    ui = UIAutomationEngine()
    
    # Test with calculator (might be in different language)
    print("\nTest 1: Focusing Calculator")
    print("-" * 40)
    print("This should work even if the window is named 'Rechner', 'Calculadora', etc.")
    print()
    
    result = ui.focus_window("Calculator")
    
    if result:
        print("✅ Successfully focused Calculator window!")
    else:
        print("⚠️  Could not focus Calculator window")
        print("   Make sure Calculator is open")
    
    print()
    
    # Test with Edge/Chrome
    print("\nTest 2: Focusing Browser")
    print("-" * 40)
    
    result = ui.focus_window("Edge")
    
    if result:
        print("✅ Successfully focused Edge window!")
    else:
        print("⚠️  Could not focus Edge window")
        print("   Trying Chrome...")
        
        result = ui.focus_window("Chrome")
        if result:
            print("✅ Successfully focused Chrome window!")
        else:
            print("⚠️  Could not focus any browser")
    
    print()


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "AI Window Identification Test Suite" + " " * 12 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    print("This test suite verifies the AI-powered window identification")
    print("fallback system that helps find windows even when their titles")
    print("are in different languages or don't match exactly.")
    print()
    
    input("Press Enter to start tests...")
    print()
    
    try:
        # Test 1: Window Enumeration
        test_window_enumeration()
        input("\nPress Enter to continue...")
        print()
        
        # Test 2: AI Identification (requires API key)
        test_ai_window_identification()
        input("\nPress Enter to continue...")
        print()
        
        # Test 3: Complete Flow
        test_focus_with_fallback()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print()
    print("=" * 60)
    print("✅ Test suite completed!")
    print("=" * 60)
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
