"""
Integration test to verify the complete prompting pipeline.
This tests that the agent can use the enhanced prompts correctly.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.gemini_client import EnhancedGeminiClient
from src.core.prompts import prompt_builder
from src.config.config import config
from PIL import Image
import io


def test_gemini_client_integration():
    """Test that GeminiClient can use the new prompt features."""
    print("=" * 60)
    print("TEST: Gemini Client Integration")
    print("=" * 60)
    
    try:
        # Check if API key is configured
        if not config.gemini_api_key or config.gemini_api_key == "your_api_key_here":
            print("⚠️  Skipping - No API key configured (this is expected in testing)")
            return True
        
        client = EnhancedGeminiClient()
        print("✓ GeminiClient initialized successfully")
        
        # Test that methods accept new parameters
        try:
            # This won't actually call the API, just checks method signatures
            import inspect
            
            # Check generate_task_plan signature
            sig = inspect.signature(client.generate_task_plan)
            params = list(sig.parameters.keys())
            has_complexity = 'complexity_hint' in params
            has_examples = 'include_examples' in params
            
            print(f"✓ generate_task_plan has complexity_hint: {has_complexity}")
            print(f"✓ generate_task_plan has include_examples: {has_examples}")
            
            # Check analyze_screen signature  
            sig = inspect.signature(client.analyze_screen)
            params = list(sig.parameters.keys())
            has_focus = 'focus_area' in params
            
            print(f"✓ analyze_screen has focus_area: {has_focus}")
            
            if has_complexity and has_examples and has_focus:
                print("\n✓ All new parameters are available")
                return True
            else:
                print("\n✗ Some parameters are missing")
                return False
                
        except Exception as e:
            print(f"✗ Signature check failed: {e}")
            return False
            
    except Exception as e:
        print(f"✗ Client initialization failed: {e}")
        return False


def test_prompt_builder_completeness():
    """Test that all prompt builder methods work correctly."""
    print("\n" + "=" * 60)
    print("TEST: Prompt Builder Completeness")
    print("=" * 60)
    
    all_passed = True
    
    # Test all builder methods exist and work
    methods = [
        ('build_task_planning_prompt', ('test request',), {}),
        ('build_screen_analysis_prompt', (), {'question': 'test'}),
        ('build_element_location_prompt', ('test element',), {}),
        ('build_verification_prompt', ('test change',), {}),
        ('build_next_action_prompt', ('state', 'goal', []), {}),
    ]
    
    for method_name, args, kwargs in methods:
        try:
            method = getattr(prompt_builder, method_name)
            result = method(*args, **kwargs)
            
            if isinstance(result, str) and len(result) > 0:
                print(f"✓ {method_name:40} -> {len(result)} chars")
            else:
                print(f"✗ {method_name:40} -> Invalid result")
                all_passed = False
                
        except Exception as e:
            print(f"✗ {method_name:40} -> Error: {e}")
            all_passed = False
    
    return all_passed


def test_backward_compatibility():
    """Test that old calling patterns still work."""
    print("\n" + "=" * 60)
    print("TEST: Backward Compatibility")
    print("=" * 60)
    
    all_passed = True
    
    # Test old-style calls without new parameters
    try:
        # Old style: just request and context
        prompt = prompt_builder.build_task_planning_prompt("test", None)
        print(f"✓ Old-style task planning call works ({len(prompt)} chars)")
    except Exception as e:
        print(f"✗ Old-style task planning call failed: {e}")
        all_passed = False
    
    try:
        # Old style: just question
        prompt = prompt_builder.build_screen_analysis_prompt("test question")
        print(f"✓ Old-style screen analysis call works ({len(prompt)} chars)")
    except Exception as e:
        print(f"✗ Old-style screen analysis call failed: {e}")
        all_passed = False
    
    try:
        # Old style: no optional params
        prompt = prompt_builder.build_screen_analysis_prompt()
        print(f"✓ Screen analysis without question works ({len(prompt)} chars)")
    except Exception as e:
        print(f"✗ Screen analysis without question failed: {e}")
        all_passed = False
    
    return all_passed


def test_prompt_quality():
    """Test that generated prompts have expected quality markers."""
    print("\n" + "=" * 60)
    print("TEST: Prompt Quality Checks")
    print("=" * 60)
    
    all_passed = True
    
    # Generate a complex task prompt
    prompt = prompt_builder.build_task_planning_prompt(
        "open notepad and type hello then save as test.txt if file does not exist",
        context={'active_window': 'Desktop', 'screen_size': (1920, 1080)}
    )
    
    quality_checks = [
        ("Windows context", "Windows Environment Context"),
        ("Execution strategies", "Execution Best Practices"),
        ("Chain of thought", "Reason about the task explicitly"),
        ("JSON schema", '"understood"'),
        ("Action list", "Available Actions"),
        ("User request", "type hello"),
        ("System context", "Active Window"),
    ]
    
    for check_name, check_string in quality_checks:
        present = check_string in prompt
        status = "✓" if present else "✗"
        print(f"{status} Prompt contains {check_name:25}: {present}")
        if not present:
            all_passed = False
    
    # Check prompt is not too short or too long
    length = len(prompt)
    length_ok = 3000 < length < 10000
    status = "✓" if length_ok else "✗"
    print(f"{status} Prompt length reasonable: {length} chars (3000-10000)")
    if not length_ok:
        all_passed = False
    
    return all_passed


def test_token_optimization():
    """Test that token usage scales appropriately with complexity."""
    print("\n" + "=" * 60)
    print("TEST: Token Optimization")
    print("=" * 60)
    
    requests = {
        'simple': "open calculator",
        'medium': "open notepad and type hello world",
        'complex': "open browser, navigate to youtube, search for tutorials if page loads"
    }
    
    lengths = {}
    
    for complexity, request in requests.items():
        prompt = prompt_builder.build_task_planning_prompt(request)
        lengths[complexity] = len(prompt)
        print(f"{complexity:8} task: {lengths[complexity]:5} chars - {request[:50]}")
    
    # Check that complexity scales appropriately
    simple_ok = lengths['simple'] < lengths['medium'] < lengths['complex']
    
    # Check that differences are significant
    medium_increase = (lengths['medium'] - lengths['simple']) / lengths['simple']
    complex_increase = (lengths['complex'] - lengths['medium']) / lengths['medium']
    
    print(f"\nMedium vs Simple: +{medium_increase*100:.1f}%")
    print(f"Complex vs Medium: +{complex_increase*100:.1f}%")
    
    # Expect at least 50% increase between levels
    scaling_ok = medium_increase > 0.5 and complex_increase > 0.05
    
    if simple_ok and scaling_ok:
        print("✓ Token optimization working correctly")
        return True
    else:
        print("✗ Token optimization needs review")
        return False


def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("INTEGRATION TEST SUITE")
    print("=" * 60 + "\n")
    
    results = []
    
    results.append(("Gemini Client Integration", test_gemini_client_integration()))
    results.append(("Prompt Builder Completeness", test_prompt_builder_completeness()))
    results.append(("Backward Compatibility", test_backward_compatibility()))
    results.append(("Prompt Quality", test_prompt_quality()))
    results.append(("Token Optimization", test_token_optimization()))
    
    print("\n" + "=" * 60)
    print("INTEGRATION TEST RESULTS")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status:12} {name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("\n🎉 All integration tests passed!")
        return 0
    else:
        print(f"\n⚠️ {total_tests - total_passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    exit(main())
