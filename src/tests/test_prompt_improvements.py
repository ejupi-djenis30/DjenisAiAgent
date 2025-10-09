"""
Test script to verify prompt improvement implementations.
Run with: py test_prompt_improvements.py
"""

import platform

from src.core.prompts import prompt_builder, _detect_complexity, _format_context
from src.core.actions import action_registry


def test_complexity_detection():
    """Test automatic complexity detection."""
    print("=" * 60)
    print("TEST 1: Complexity Detection")
    print("=" * 60)
    
    test_cases = [
        ("open calculator", "simple"),
        ("click button", "simple"),
        ("open notepad and type hello", "medium"),
        ("go to youtube and search", "medium"),
        ("open chrome, navigate to youtube, then search for tutorials if the page loads", "complex"),
        ("type hello when the window opens", "complex"),
        ("word " * 30, "complex"),  # Very long request (30+ words)
    ]
    
    passed = 0
    failed = 0
    
    for request, expected in test_cases:
        result = _detect_complexity(request)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        display_request = request[:50] + "..." if len(request) > 50 else request
        print(f"{status} {display_request:50} -> {result:8} (expected: {expected})")
    
    print(f"\nResult: {passed} passed, {failed} failed\n")
    return failed == 0


def test_context_formatting():
    """Test context formatting with various inputs."""
    print("=" * 60)
    print("TEST 2: Context Formatting")
    print("=" * 60)
    
    # Test with full context
    full_context = {
        'active_window': 'Chrome - YouTube',
        'screen_size': (1920, 1080),
        'running_processes': ['chrome.exe', 'notepad.exe', 'calc.exe', 'explorer.exe'],
        'timestamp': '2025-10-09T10:30:00',
        'agent_version': '2.0'
    }
    
    result = _format_context(full_context)
    print("Full context result:")
    print(result)
    print(f"Length: {len(result)} chars")
    
    # Test with empty context
    empty_result = _format_context({})
    print(f"\nEmpty context result: '{empty_result}' (should be empty)")
    print(f"Is empty: {empty_result == ''}")
    
    # Test with partial context
    partial_context = {'active_window': 'Notepad'}
    partial_result = _format_context(partial_context)
    print(f"\nPartial context length: {len(partial_result)} chars")
    print(f"Has active window: {'Active Window' in partial_result}")
    
    success = (len(result) > 0 and empty_result == '' and 'Active Window' in partial_result)
    print(f"\n{'✓' if success else '✗'} Context formatting test {'passed' if success else 'failed'}\n")
    return success


def test_prompt_generation():
    """Test prompt generation for different complexities."""
    print("=" * 60)
    print("TEST 3: Prompt Generation")
    print("=" * 60)
    
    test_cases = [
        ("open calculator", "simple"),
        ("open notepad and type hello world", "medium"),
        ("open browser and search for python tutorials if connection works", "complex"),
    ]
    
    all_passed = True
    
    for request, expected_complexity in test_cases:
        prompt = prompt_builder.build_task_planning_prompt(request)
        detected = _detect_complexity(request)
        
        # Check expected sections
        has_windows_context = "Windows Environment Context" in prompt
        has_execution_strategies = "Execution Best Practices" in prompt
        has_chain_of_thought = "Reason about the task explicitly" in prompt
        has_schema = "understood" in prompt and "steps" in prompt
        
        print(f"\nRequest: {request}")
        print(f"  Detected complexity: {detected}")
        print(f"  Prompt length: {len(prompt)} chars")
        print(f"  Has Windows context: {has_windows_context}")
        print(f"  Has execution strategies: {has_execution_strategies}")
        print(f"  Has chain of thought: {has_chain_of_thought}")
        print(f"  Has JSON schema: {has_schema}")
        
        # Validate
        if detected == "simple":
            expected = has_windows_context and has_schema and not has_execution_strategies and not has_chain_of_thought
        elif detected == "medium":
            expected = has_windows_context and has_execution_strategies and has_schema and not has_chain_of_thought
        else:  # complex
            expected = has_windows_context and has_execution_strategies and has_chain_of_thought and has_schema
        
        status = "✓" if expected else "✗"
        print(f"  {status} Sections correct for {detected} complexity")
        
        if not expected:
            all_passed = False
    
    print(f"\n{'✓' if all_passed else '✗'} Prompt generation test {'passed' if all_passed else 'failed'}\n")
    return all_passed


def test_action_registry():
    """Test action registry formatting methods."""
    print("=" * 60)
    print("TEST 4: Action Registry")
    print("=" * 60)
    
    # Test compact format
    compact = action_registry.to_compact_prompt_string()
    print(f"Compact format: {len(compact)} chars")
    print(f"  Has action names: {'open_application' in compact}")
    
    # Test detailed without examples
    detailed_no_ex = action_registry.to_prompt_string(include_examples=False)
    print(f"\nDetailed (no examples): {len(detailed_no_ex)} chars")
    print(f"  Has categories: {'APPLICATION ACTIONS' in detailed_no_ex}")
    print(f"  Has parameters: {'Parameters:' in detailed_no_ex}")
    
    # Test detailed with examples
    detailed_with_ex = action_registry.to_prompt_string(include_examples=True)
    print(f"\nDetailed (with examples): {len(detailed_with_ex)} chars")
    print(f"  Has example block: {'Detailed Action Examples' in detailed_with_ex}")
    
    # Test max_per_category
    limited = action_registry.to_prompt_string(max_per_category=3)
    limited_lines = limited.count('\n')
    full_lines = detailed_with_ex.count('\n')
    print(f"\nLimited to 3 per category: {len(limited)} chars ({limited_lines} lines)")
    print(f"  Shorter than full: {limited_lines < full_lines}")
    
    success = (
        len(compact) < len(detailed_no_ex) < len(detailed_with_ex) and
        limited_lines < full_lines
    )
    
    print(f"\n{'✓' if success else '✗'} Action registry test {'passed' if success else 'failed'}\n")
    return success


def test_screen_analysis():
    """Test screen analysis prompt with focus areas."""
    print("=" * 60)
    print("TEST 5: Screen Analysis Prompts")
    print("=" * 60)
    
    focus_areas = ["center", "top", "bottom", "left", "right", "full", None]
    
    all_passed = True
    
    for focus in focus_areas:
        prompt = prompt_builder.build_screen_analysis_prompt(
            question="where is the save button",
            focus_area=focus
        )
        
        has_question = "where is the save button" in prompt
        has_focus = focus is None or (focus in ["center", "top", "bottom", "left", "right", "full"] and 
                                       ("Focus on" in prompt or focus == "full"))
        
        status = "✓" if (has_question and has_focus) else "✗"
        print(f"{status} Focus: {focus or 'none':8} -> {len(prompt)} chars, has question: {has_question}, has focus: {has_focus}")
        
        if not (has_question and has_focus):
            all_passed = False
    
    print(f"\n{'✓' if all_passed else '✗'} Screen analysis test {'passed' if all_passed else 'failed'}\n")
    return all_passed


def test_system_app_discovery():
    """Test that system application discovery integrates with prompts on Windows."""

    print("=" * 60)
    print("TEST 6: System Application Discovery")
    print("=" * 60)

    if platform.system() != "Windows":
        print("⚠️  Skipped: System application discovery is Windows-only.")
        return True

    try:
        from src.utils.system_apps import get_apps_catalog_formatted, find_executable
    except Exception as exc:  # pragma: no cover - import guards handle non-Windows
        print(f"✗ Failed to import system apps utilities: {exc}")
        return False

    catalog = get_apps_catalog_formatted()
    print("Catalog preview:")
    preview_lines = "\n".join(catalog.splitlines()[:6])
    print(preview_lines)

    resolved_edge = find_executable("edge")
    resolved_calc = find_executable("calculator")

    success = catalog.startswith("Available Windows applications") and (
        resolved_edge.endswith(".exe")
    ) and (
        resolved_calc.endswith(".exe")
    )

    status = "✓" if success else "✗"
    print(f"{status} Discovery integration working\n")
    return success


def test_edge_cases():
    """Test edge cases and error handling."""
    print("=" * 60)
    print("TEST 7: Edge Cases")
    print("=" * 60)
    
    all_passed = True
    
    # Empty request
    try:
        prompt = prompt_builder.build_task_planning_prompt("")
        print("✓ Empty request handled")
    except Exception as e:
        print(f"✗ Empty request failed: {e}")
        all_passed = False
    
    # Very long request
    try:
        long_request = "open " + " and ".join(["application"] * 50)
        prompt = prompt_builder.build_task_planning_prompt(long_request)
        complexity = _detect_complexity(long_request)
        print(f"✓ Very long request handled (complexity: {complexity})")
    except Exception as e:
        print(f"✗ Long request failed: {e}")
        all_passed = False
    
    # Special characters
    try:
        special = "open 'notepad.exe' && type \"hello\""
        prompt = prompt_builder.build_task_planning_prompt(special)
        print("✓ Special characters handled")
    except Exception as e:
        print(f"✗ Special characters failed: {e}")
        all_passed = False
    
    # None context
    try:
        prompt = prompt_builder.build_task_planning_prompt("test", context=None)
        print("✓ None context handled")
    except Exception as e:
        print(f"✗ None context failed: {e}")
        all_passed = False
    
    print(f"\n{'✓' if all_passed else '✗'} Edge cases test {'passed' if all_passed else 'failed'}\n")
    return all_passed


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PROMPT IMPROVEMENTS VERIFICATION")
    print("=" * 60 + "\n")
    
    results = []
    
    results.append(("Complexity Detection", test_complexity_detection()))
    results.append(("Context Formatting", test_context_formatting()))
    results.append(("Prompt Generation", test_prompt_generation()))
    results.append(("Action Registry", test_action_registry()))
    results.append(("Screen Analysis", test_screen_analysis()))
    results.append(("System App Discovery", test_system_app_discovery()))
    results.append(("Edge Cases", test_edge_cases()))
    
    print("=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status:12} {name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("\n🎉 All tests passed! Implementation is working correctly.")
        return 0
    else:
        print(f"\n⚠️ {total_tests - total_passed} test(s) failed. Please review.")
        return 1


if __name__ == "__main__":
    exit(main())
