import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agent_core import AgentCore

class TestAgentCore(unittest.TestCase):
    
    @patch('src.agent_core.ShortTermMemory')
    @patch('src.agent_core.TaskMemory')
    @patch('src.agent_core.ScreenAnalyzer')
    @patch('src.agent_core.Win11Capture')
    @patch('src.agent_core.Planner')
    @patch('src.agent_core.Win11InputTool')
    @patch('src.agent_core.MCPTool')
    @patch('src.agent_core.GeminiClient')
    @patch('src.agent_core.PromptManager')
    def setUp(self, mock_prompt_manager, mock_gemini, mock_mcp, mock_input, 
              mock_planner, mock_capture, mock_analyzer, mock_task, mock_memory):
        """Set up test fixtures with mocked components."""
        # Mock config
        self.config = {
            "general": {"debug_mode": True},
            "memory": {"max_items": 10, "task_storage_dir": "test_storage"},
            "perception": {"screenshot_dir": "test_screenshots"},
            "gemini": {"api_key": "test_key", "model_name": "test_model"},
            "mcp": {"host": "localhost", "port": 8080},
            "tools": {"input": {"safety_delay": 0.01}}
        }
        
        # Create instance with mocked dependencies
        self.agent = AgentCore(self.config)
        
        # Store mocks for assertions
        self.mock_memory = mock_memory
        self.mock_task = mock_task
        self.mock_analyzer = mock_analyzer
        self.mock_capture = mock_capture
        self.mock_planner = mock_planner
        self.mock_input = mock_input
        self.mock_mcp = mock_mcp
        self.mock_gemini = mock_gemini
        self.mock_prompt_manager = mock_prompt_manager

    def test_initialization(self):
        """Test that the agent initializes all components correctly."""
        # Check that all components were initialized
        self.assertIn("short_term_memory", self.agent.components)
        self.assertIn("task_memory", self.agent.components)
        self.assertIn("screen_capture", self.agent.components)
        self.assertIn("screen_analyzer", self.agent.components)
        self.assertIn("planner", self.agent.components)
        self.assertIn("input_tool", self.agent.components)
        self.assertIn("mcp_tool", self.agent.components)
        self.assertIn("gemini_client", self.agent.components)
        self.assertIn("prompt_manager", self.agent.components)

    @patch('src.agent_core.AgentCore._main_loop')
    def test_start_stop(self, mock_main_loop):
        """Test start/stop functionality."""
        # Test start
        self.agent.start()
        self.assertTrue(self.agent.running)
        mock_main_loop.assert_called_once()
        
        # Test stop
        self.agent.stop()
        self.assertFalse(self.agent.running)

    def test_pause_resume(self):
        """Test pause/resume functionality."""
        # Test pause
        self.agent.pause()
        self.assertTrue(self.agent.paused)
        
        # Test resume
        self.agent.resume()
        self.assertFalse(self.agent.paused)

    @patch('src.agent_core.time.sleep', return_value=None)
    def test_execute_decision(self, mock_sleep):
        """Test decision execution."""
        # Set up mocked input tool
        input_tool_mock = MagicMock()
        self.agent.components["input_tool"] = input_tool_mock
        
        # Test click action
        self.agent._execute_decision({"action_type": "click", "parameters": {"x": 100, "y": 200}})
        input_tool_mock.simulate_mouse_click.assert_called_with(100, 200)
        
        # Test type text action
        self.agent._execute_decision({"action_type": "type_text", "parameters": {"text": "Hello World"}})
        input_tool_mock.type_text.assert_called_with("Hello World")
        
        # Test key press action
        self.agent._execute_decision({"action_type": "key_press", "parameters": {"key": "enter"}})
        input_tool_mock.simulate_key_press.assert_called_with("enter")
        
        # Test wait action
        self.agent._execute_decision({"action_type": "wait", "parameters": {"seconds": 2}})
        mock_sleep.assert_called_with(2)

    @patch('src.agent_core.time.time', return_value=12345)
    def test_process_user_request(self, mock_time):
        """Test processing a user request."""
        # Mock components
        screenshot_mock = MagicMock()
        self.agent.components["screen_capture"] = MagicMock()
        self.agent.components["screen_capture"].capture_screen.return_value = screenshot_mock
        self.agent.components["screen_capture"].save_capture.return_value = "test_path.png"
        
        self.agent.components["screen_analyzer"] = MagicMock()
        self.agent.components["screen_analyzer"].analyze.return_value = {"test": "data"}
        self.agent.components["screen_analyzer"].extract_information.return_value = {"screen_state": "desktop"}
        
        self.agent.components["prompt_manager"] = MagicMock()
        self.agent.components["prompt_manager"].format_prompt.return_value = "formatted prompt"
        
        self.agent.components["gemini_client"] = MagicMock()
        self.agent.components["gemini_client"].send_request.return_value = {"text": "AI response"}
        self.agent.components["gemini_client"].handle_response.return_value = {
            "text": "AI response",
            "actions": [{"type": "click", "parameters": {"x": 100, "y": 200}}]
        }
        
        self.agent.components["short_term_memory"] = MagicMock()
        self.agent.components["task_memory"] = MagicMock()
        
        # Process a request
        result = self.agent.process_user_request("Open settings")
        
        # Verify calls
        self.agent.components["screen_capture"].capture_screen.assert_called_once()
        self.agent.components["screen_analyzer"].analyze.assert_called_once()
        self.agent.components["prompt_manager"].format_prompt.assert_called_once()
        self.agent.components["gemini_client"].send_request.assert_called_once()
        self.agent.components["short_term_memory"].store.assert_called_once()
        self.agent.components["task_memory"].create_task.assert_called_once()
        
        # Check result
        self.assertEqual(result["text"], "AI response")
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["type"], "click")

    def test_get_status(self):
        """Test getting agent status."""
        status = self.agent.get_status()
        
        self.assertIn("running", status)
        self.assertIn("paused", status)
        self.assertIn("last_error", status)
        self.assertIn("timestamp", status)

if __name__ == '__main__':
    unittest.main()