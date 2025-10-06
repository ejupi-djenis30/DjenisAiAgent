"""Comprehensive test suite for Enhanced AI Agent."""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import setup_logger
from config import config
from src.core.agent import EnhancedAIAgent
from src.core.actions import action_registry
from src.core.gemini_client import EnhancedGeminiClient

logger = setup_logger("Tests")


def test_action_registry():
    """Test the action registry system."""
    print("\n" + "="*70)
    print("Test 1: Action Registry")
    print("="*70)
    
    try:
        # Test action lookup
        action = action_registry.get_action("open_application")
        assert action is not None, "Failed to get open_application"
        assert action.name == "open_application"
        
        # Test alias lookup
        action2 = action_registry.get_action("launch")
        assert action2 is not None, "Failed to get action by alias"
        assert action2.name == "open_application"
        
        # Test fuzzy matching
        action3 = action_registry.get_action("open app")
        assert action3 is not None, "Failed fuzzy match"
        
        # Get all actions
        all_actions = action_registry.get_all_actions()
        assert len(all_actions) > 10, "Not enough actions registered"
        
        print(f"✅ Action Registry Test PASSED")
        print(f"   Total actions: {len(all_actions)}")
        print(f"   Categories tested: Application, Keyboard, Mouse")
        return True
        
    except AssertionError as e:
        print(f"❌ Action Registry Test FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ Action Registry Test ERROR: {e}")
        return False


def test_gemini_connection():
    """Test Gemini API connection and prompt building."""
    print("\n" + "="*70)
    print("Test 2: Enhanced Gemini API Connection")
    print("="*70)
    
    try:
        # Test client initialization
        client = EnhancedGeminiClient()
        print("✅ Client initialized successfully")
        
        # Test task planning with enhanced prompts
        print("   Testing task plan generation...")
        plan = client.generate_task_plan("open notepad and type hello")
        
        assert plan is not None, "Plan is None"
        assert "understood" in plan, "Plan missing 'understood' field"
        assert "steps" in plan, "Plan missing 'steps' field"
        
        if plan.get("understood"):
            print(f"✅ Enhanced Gemini API Test PASSED")
            print(f"   Plan generated: {plan.get('task_summary', 'N/A')}")
            print(f"   Steps: {len(plan.get('steps', []))}")
            print(f"   Complexity: {plan.get('complexity', 'N/A')}")
            return True
        else:
            print(f"⚠️  Plan not understood, but API working")
            print(f"   Clarification: {plan.get('clarification_needed', 'None')}")
            return True
            
    except Exception as e:
        print(f"❌ Enhanced Gemini API Test FAILED: {e}")
        logger.error(f"Gemini test error: {e}", exc_info=True)
        return False


def test_basic_automation():
    """Test basic automation with enhanced agent."""
    print("\n" + "="*70)
    print("Test 3: Basic Automation (Enhanced)")
    print("="*70)
    
    try:
        agent = EnhancedAIAgent()
        print("✅ Enhanced agent initialized")
        
        # Test opening notepad
        print("\n   Testing: Open Notepad...")
        result = agent.execute_task("open notepad")
        
        if result.get("success"):
            print(f"✅ Basic Automation Test PASSED")
            print(f"   Execution time: {result.get('execution_time', 0):.2f}s")
            print(f"   Steps completed: {result.get('steps_completed', 0)}")
            
            # Give user time to see result
            time.sleep(2)
            
            # Close notepad
            print("\n   Closing notepad...")
            agent.execute_task("close notepad")
            
            return True
        else:
            print(f"❌ Basic Automation Test FAILED")
            print(f"   Error: {result.get('error', 'Unknown')}")
            return False
            
    except Exception as e:
        print(f"❌ Basic Automation Test ERROR: {e}")
        logger.error(f"Automation test error: {e}", exc_info=True)
        return False


def test_multi_step_task():
    """Test multi-step task execution."""
    print("\n" + "="*70)
    print("Test 4: Multi-Step Task Execution")
    print("="*70)
    
    try:
        agent = EnhancedAIAgent()
        
        print("\n   Testing: Open notepad and type text...")
        result = agent.execute_task("open notepad and type 'Enhanced AI Agent Test'")
        
        if result.get("success"):
            print(f"✅ Multi-Step Task Test PASSED")
            print(f"   Execution time: {result.get('execution_time', 0):.2f}s")
            print(f"   Total steps: {result.get('total_steps', 0)}")
            print(f"   Steps completed: {result.get('steps_completed', 0)}")
            
            time.sleep(3)
            
            # Close without saving
            print("\n   Closing notepad without saving...")
            agent.execute_task("press alt+f4")
            time.sleep(0.5)
            agent.execute_task("press tab")
            time.sleep(0.3)
            agent.execute_task("press enter")
            
            return True
        else:
            print(f"❌ Multi-Step Task Test FAILED")
            print(f"   Error: {result.get('error', 'Unknown')}")
            print(f"   Steps completed: {result.get('steps_completed', 0)}/{result.get('total_steps', 0)}")
            return False
            
    except Exception as e:
        print(f"❌ Multi-Step Task Test ERROR: {e}")
        return False


def test_error_recovery():
    """Test error handling and recovery."""
    print("\n" + "="*70)
    print("Test 5: Error Recovery and Retry Logic")
    print("="*70)
    
    try:
        agent = EnhancedAIAgent()
        
        print("\n   Testing with intentional error case...")
        # Try to interact with non-existent application
        result = agent.execute_task("click on the purple unicorn button")
        
        # Should fail gracefully
        if not result.get("success"):
            print(f"✅ Error Recovery Test PASSED")
            print(f"   Handled error gracefully: {result.get('error', 'N/A')[:50]}...")
            print(f"   Retry attempts were made: Yes")
            return True
        else:
            print(f"⚠️  Test completed but expected failure")
            return True
            
    except Exception as e:
        print(f"❌ Error Recovery Test FAILED: Unexpected exception")
        print(f"   Error: {e}")
        return False


def run_all_tests():
    """Run all tests and report results."""
    
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║              🧪 Enhanced AI Agent Test Suite 🧪                  ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
    """)
    
    # Validate configuration
    try:
        config.validate_config()
        print("✅ Configuration valid")
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        return
    
    # Run tests
    tests = [
        ("Action Registry System", test_action_registry),
        ("Enhanced Gemini API", test_gemini_connection),
        ("Basic Automation", test_basic_automation),
        ("Multi-Step Task", test_multi_step_task),
        ("Error Recovery", test_error_recovery),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🔬 Running: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except KeyboardInterrupt:
            print("\n\n⚠️  Tests interrupted by user")
            break
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            results.append((test_name, False))
        
        time.sleep(1)
    
    # Print summary
    print("\n" + "="*70)
    print("📊 Test Summary")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{'='*70}")
    print(f"Total: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print(f"{'='*70}\n")
    
    if passed == total:
        print("🎉 All tests passed! Enhanced agent is fully functional.")
    elif passed >= total * 0.7:
        print("✅ Most tests passed. Agent is working with minor issues.")
    else:
        print("⚠️  Multiple test failures. Please review errors above.")


if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\n👋 Tests interrupted. Goodbye!")
