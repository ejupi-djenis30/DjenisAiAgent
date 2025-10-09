"""
Test script to verify AI Agent setup and functionality.
"""

import sys
import locale

def test_imports():
    """Test if all required packages can be imported."""
    print("Testing imports...")
    
    packages = [
        ("google.generativeai", "Google Generative AI"),
        ("pyautogui", "PyAutoGUI"),
        ("pywinauto", "PyWinAuto"),
        ("PIL", "Pillow"),
        ("cv2", "OpenCV"),
        ("pytesseract", "PyTesseract"),
        ("psutil", "psutil"),
        ("pygetwindow", "PyGetWindow"),
        ("pyperclip", "Pyperclip"),
        ("keyboard", "Keyboard")
    ]
    
    failed = []
    
    for module, name in packages:
        try:
            __import__(module)
            print(f"  ✅ {name}")
        except ImportError as e:
            print(f"  ❌ {name}: {e}")
            failed.append(name)
    
    if failed:
        print(f"\n❌ Failed to import: {', '.join(failed)}")
        return False
    
    print("\n✅ All imports successful!")
    return True


def test_tesseract():
    """Test if Tesseract OCR is available."""
    print("\nTesting Tesseract OCR...")
    
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        print(f"  ✅ Tesseract version: {version}")
        return True
    except Exception as e:
        print(f"  ⚠️  Tesseract not available: {e}")
        print("     OCR features will not work. Install from:")
        print("     https://github.com/UB-Mannheim/tesseract/wiki")
        return False


def test_config():
    """Test if configuration is valid."""
    print("\nTesting configuration...")
    
    try:
        import config
        
        # Check API key
        if hasattr(config, 'gemini_api_key') and config.gemini_api_key:  # type: ignore
            if config.gemini_api_key == "your_api_key_here":  # type: ignore
                print("  ⚠️  Gemini API key not configured")
                print("     Edit config.py and set your API key")
                print("     Get one from: https://makersuite.google.com/app/apikey")
                return False
            else:
                key_preview = config.gemini_api_key[:10] + "..." + config.gemini_api_key[-4:]  # type: ignore
                print(f"  ✅ API key configured: {key_preview}")
        else:
            print("  ❌ API key not found in config")
            return False
        
        # Check model
        if hasattr(config, 'gemini_model'):
            print(f"  ✅ Model: {config.gemini_model}")  # type: ignore
        
        return True
        
    except ImportError:
        print("  ❌ config.py not found")
        return False
    except Exception as e:
        print(f"  ❌ Configuration error: {e}")
        return False


def test_language():
    """Test system language detection."""
    print("\nTesting language detection...")
    
    try:
        system_lang = locale.getlocale()[0] or "Unknown"
        print(f"  System locale: {system_lang}")
        
        # Map Windows locale names to language codes
        lang_map = {
            "german": "de",
            "deutsch": "de",
            "spanish": "es",
            "french": "fr",
            "italian": "it",
            "portuguese": "pt",
            "russian": "ru",
            "chinese": "zh",
            "japanese": "ja",
            "korean": "ko",
            "english": "en"
        }
        
        lang_lower = system_lang.lower()
        lang_code = "en"
        
        for key, code in lang_map.items():
            if key in lang_lower:
                lang_code = code
                break
        
        # Also check for standard format
        if '_' in system_lang and lang_code == "en":
            parts = system_lang.split('_')
            if len(parts[0]) == 2:
                lang_code = parts[0].lower()
        
        print(f"  Detected language code: {lang_code.upper()}")
        
        if lang_code != "en":
            print(f"  ⚠️  Non-English system detected!")
            print(f"     UI elements will be in {lang_code.upper()}")
            print(f"     Example: Calculator = ", end="")
            
            calc_names = {
                "de": "Rechner",
                "es": "Calculadora",
                "fr": "Calculatrice",
                "it": "Calcolatrice",
                "pt": "Calculadora"
            }
            print(calc_names.get(lang_code, "Calculator"))
        
        return True
        
    except Exception as e:
        print(f"  ⚠️  Could not detect language: {e}")
        return True  # Not critical


def test_ui_overlay():
    """Test if UI overlay can be created."""
    print("\nTesting UI overlay...")
    
    try:
        from src.core.ui_overlay import get_overlay
        
        print("  Creating overlay instance...")
        overlay = get_overlay()
        
        print("  ✅ UI overlay created successfully")
        print("     Note: UI will only display when agent is running")
        
        return True
        
    except Exception as e:
        print(f"  ❌ UI overlay error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("AI Agent - Setup Verification")
    print("=" * 60)
    print()
    
    results = {
        "Imports": test_imports(),
        "Tesseract OCR": test_tesseract(),
        "Configuration": test_config(),
        "Language Detection": test_language(),
        "UI Overlay": test_ui_overlay()
    }
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test:.<40} {status}")
    
    print()
    
    # Overall result
    all_critical_passed = results["Imports"] and results["Configuration"]
    
    if all_critical_passed:
        print("✅ Setup is complete! Agent is ready to use.")
        print()
        print("Try running:")
        print("  python main.py 'open calculator'")
        print()
        return 0
    else:
        print("❌ Setup incomplete. Please fix the errors above.")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
