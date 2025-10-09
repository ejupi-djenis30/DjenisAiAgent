"""Test OCR integration with screen recording."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from PIL import Image, ImageDraw, ImageFont
from src.utils.ocr import get_ocr_engine, TesseractOCR
from src.core.gemini_client import EnhancedGeminiClient
from src.config.config import config


def create_test_image() -> Image.Image:
    """Create a simple test image with text."""
    # Create a white image
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use a default font, fallback to default if not available
    try:
        font = ImageFont.truetype("arial.ttf", 40)
        font_small = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
        font_small = font
    
    # Add some text elements
    draw.text((100, 50), "Welcome to Test App", fill='black', font=font)
    draw.text((100, 150), "Username:", fill='black', font=font_small)
    draw.text((100, 250), "Password:", fill='black', font=font_small)
    
    # Draw buttons
    draw.rectangle([100, 350, 250, 400], outline='black', width=2)
    draw.text((130, 365), "Login", fill='black', font=font_small)
    
    draw.rectangle([300, 350, 450, 400], outline='black', width=2)
    draw.text((320, 365), "Cancel", fill='black', font=font_small)
    
    # Add some status text
    draw.text((100, 500), "Status: Ready", fill='green', font=font_small)
    
    return img


def test_ocr_basic():
    """Test basic OCR text extraction."""
    print("=" * 60)
    print("TEST 1: Basic OCR Text Extraction")
    print("=" * 60)
    
    ocr = get_ocr_engine()
    if not ocr:
        print("❌ OCR engine not available")
        return False
    
    img = create_test_image()
    text = ocr.extract_text(img)
    
    print(f"Extracted text ({len(text)} chars):")
    print("-" * 60)
    print(text)
    print("-" * 60)
    
    # Check if key text is found
    expected_words = ["Welcome", "Test", "Username", "Password", "Login", "Cancel", "Status"]
    found_words = [word for word in expected_words if word in text]
    
    print(f"\n✓ Found {len(found_words)}/{len(expected_words)} expected words:")
    print(f"  {', '.join(found_words)}")
    
    success = len(found_words) >= len(expected_words) * 0.7  # 70% threshold
    print(f"\n{'✓ PASSED' if success else '✗ FAILED'}: Basic OCR extraction\n")
    return success


def test_ocr_screen_analysis():
    """Test comprehensive screen analysis."""
    print("=" * 60)
    print("TEST 2: Screen Analysis with Positions")
    print("=" * 60)
    
    ocr = get_ocr_engine()
    if not ocr:
        print("❌ OCR engine not available")
        return False
    
    img = create_test_image()
    analysis = ocr.analyze_screen(img, min_confidence=60.0)
    
    print(f"Analysis results:")
    print(f"  Words detected: {len(analysis.words)}")
    print(f"  Lines detected: {len(analysis.lines)}")
    print(f"  Blocks detected: {len(analysis.blocks)}")
    print(f"  Average confidence: {analysis.average_confidence:.1f}%")
    
    print(f"\nWord locations:")
    for i, word in enumerate(analysis.words[:10], 1):  # Show first 10
        print(f"  {i}. '{word.text}' at {word.center} (confidence: {word.confidence:.1f}%)")
    
    success = len(analysis.words) > 0 and analysis.average_confidence > 50
    print(f"\n{'✓ PASSED' if success else '✗ FAILED'}: Screen analysis\n")
    return success


def test_ocr_find_text():
    """Test finding specific text in image."""
    print("=" * 60)
    print("TEST 3: Find Specific Text")
    print("=" * 60)
    
    ocr = get_ocr_engine()
    if not ocr:
        print("❌ OCR engine not available")
        return False
    
    img = create_test_image()
    
    search_terms = ["Login", "Cancel", "Username", "Password", "Status"]
    results = {}
    
    for term in search_terms:
        matches = ocr.find_text(img, term, exact_match=False, min_confidence=60.0)
        results[term] = matches
        
        if matches:
            match = matches[0]
            print(f"✓ Found '{term}' at {match.center} (confidence: {match.confidence:.1f}%)")
        else:
            print(f"✗ Not found: '{term}'")
    
    found_count = sum(1 for matches in results.values() if matches)
    success = found_count >= len(search_terms) * 0.6  # 60% threshold
    
    print(f"\n{'✓ PASSED' if success else '✗ FAILED'}: Text search ({found_count}/{len(search_terms)} found)\n")
    return success


def test_gemini_ocr_integration():
    """Test Gemini client OCR integration."""
    print("=" * 60)
    print("TEST 4: Gemini Client OCR Integration")
    print("=" * 60)
    
    if not config.gemini_api_key:
        print("⚠ Skipped: No Gemini API key configured")
        return True  # Not a failure, just skipped
    
    try:
        client = EnhancedGeminiClient()
        
        if not client.ocr:
            print("⚠ OCR not available in Gemini client")
            return False
        
        img = create_test_image()
        
        # Test with OCR enabled
        print("Analyzing screen with OCR...")
        result_with_ocr = client.analyze_screen(
            img,
            question="What buttons are visible?",
            use_ocr=True
        )
        
        print(f"Analysis result (with OCR): {len(result_with_ocr)} chars")
        if "Login" in result_with_ocr or "Cancel" in result_with_ocr:
            print("✓ OCR text found in analysis result")
            success = True
        else:
            print("⚠ OCR text not clearly present in result")
            success = False
        
        print(f"\n{'✓ PASSED' if success else '✗ FAILED'}: Gemini OCR integration\n")
        return success
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_ocr_preprocessing():
    """Test image preprocessing for better OCR."""
    print("=" * 60)
    print("TEST 5: Image Preprocessing")
    print("=" * 60)
    
    ocr = get_ocr_engine()
    if not ocr:
        print("❌ OCR engine not available")
        return False
    
    img = create_test_image()
    
    # Test with and without preprocessing
    text_with_preprocess = ocr.extract_text(img, preprocess=True)
    text_without_preprocess = ocr.extract_text(img, preprocess=False)
    
    print(f"With preprocessing: {len(text_with_preprocess)} chars")
    print(f"Without preprocessing: {len(text_without_preprocess)} chars")
    
    # Both should work for our clean test image
    success = len(text_with_preprocess) > 20 and len(text_without_preprocess) > 20
    
    print(f"\n{'✓ PASSED' if success else '✗ FAILED'}: Preprocessing works\n")
    return success


def main():
    """Run all OCR tests."""
    print("\n" + "=" * 60)
    print("OCR INTEGRATION TEST SUITE")
    print("=" * 60 + "\n")
    
    results = []
    
    results.append(("Basic OCR Extraction", test_ocr_basic()))
    results.append(("Screen Analysis", test_ocr_screen_analysis()))
    results.append(("Text Search", test_ocr_find_text()))
    results.append(("Gemini Integration", test_gemini_ocr_integration()))
    results.append(("Preprocessing", test_ocr_preprocessing()))
    
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status:12} {name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("\n🎉 All tests passed! OCR integration is working correctly.")
        return 0
    else:
        print(f"\n⚠️ {total_tests - total_passed} test(s) failed. Please review.")
        return 1


if __name__ == "__main__":
    exit(main())
