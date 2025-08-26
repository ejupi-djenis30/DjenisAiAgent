import unittest
import os
import sys
from unittest.mock import patch, MagicMock, mock_open
import socket
import json
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.win11_input import Win11InputTool
from src.tools.mcp_tool import MCPTool

class TestWin11InputTool(unittest.TestCase):

    @patch('src.tools.win11_input.pyautogui')
    @patch('src.tools.win11_input.keyboard')
    @patch('src.tools.win11_input.win32api')
    @patch('src.tools.win11_input.win32con')
    def setUp(self, mock_win32con, mock_win32api, mock_keyboard, mock_pyautogui):
        """Set up test fixtures."""
        # Configure PyAutoGUI mock
        self.mock_pyautogui = mock_pyautogui
        
        # Create tool instance
        self.input_tool = Win11InputTool(safety_delay=0.01)

    @patch('src.tools.win11_input.time.sleep')
    def test_simulate_key_press(self, mock_sleep):
        """Test key press simulation."""
        # Test single key
        result = self.input_tool.simulate_key_press('a')
        self.mock_pyautogui.keyDown.assert_called_with('a')
        self.mock_pyautogui.keyUp.assert_called_with('a')
        mock_sleep.assert_called()
        self.assertTrue(result)
        
        # Test key combination
        result = self.input_tool.simulate_key_press('ctrl+c')
        self.mock_pyautogui.hotkey.assert_called_with('ctrl', 'c')
        self.assertTrue(result)

    @patch('src.tools.win11_input.time.sleep')
    def test_simulate_mouse_click(self, mock_sleep):
        """Test mouse click simulation."""
        # Test left click
        result = self.input_tool.simulate_mouse_click(100, 200)
        self.mock_pyautogui.click.assert_called_with(x=100, y=200, button='left', clicks=1, interval=0.25)
        mock_sleep.assert_called()
        self.assertTrue(result)
        
        # Test right click
        result = self.input_tool.simulate_mouse_click(300, 400, button='right')
        self.mock_pyautogui.click.assert_called_with(x=300, y=400, button='right', clicks=1, interval=0.25)
        self.assertTrue(result)

    @patch('src.tools.win11_input.time.sleep')
    def test_simulate_mouse_move(self, mock_sleep):
        """Test mouse movement simulation."""
        result = self.input_tool.simulate_mouse_move(100, 200)
        self.mock_pyautogui.moveTo.assert_called_with(100, 200, duration=0.5)
        mock_sleep.assert_called()
        self.assertTrue(result)

    @patch('src.tools.win11_input.time.sleep')
    def test_type_text(self, mock_sleep):
        """Test text typing simulation."""
        result = self.input_tool.type_text("Hello World")
        self.mock_pyautogui.typewrite.assert_called_with("Hello World", interval=0.05)
        mock_sleep.assert_called()
        self.assertTrue(result)

    @patch('src.tools.win11_input.time.sleep')
    def test_scroll(self, mock_sleep):
        """Test scrolling functionality."""
        # Test scroll without position
        result = self.input_tool.scroll(100)
        self.mock_pyautogui.scroll.assert_called_with(100)
        mock_sleep.assert_called()
        self.assertTrue(result)
        
        # Test scroll with position
        result = self.input_tool.scroll(100, x=200, y=300)
        self.mock_pyautogui.moveTo.assert_called_with(200, 300)
        self.mock_pyautogui.scroll.assert_called_with(100)
        self.assertTrue(result)

    @patch('src.tools.win11_input.time.sleep')
    def test_drag_and_drop(self, mock_sleep):
        """Test drag and drop functionality."""
        result = self.input_tool.drag_and_drop(100, 200, 300, 400)
        self.mock_pyautogui.moveTo.assert_called_with(100, 200)
        self.mock_pyautogui.dragTo.assert_called_with(300, 400, duration=0.5, button='left')
        mock_sleep.assert_called()
        self.assertTrue(result)

class TestMCPTool(unittest.TestCase):

    @patch('src.tools.mcp_tool.socket.socket')
    def setUp(self, mock_socket):
        """Set up test fixtures."""
        # Set up socket mock
        self.mock_socket = MagicMock()
        mock_socket.return_value = self.mock_socket
        
        # Create tool instance
        self.mcp_tool = MCPTool(host="localhost", port=8080, timeout=5.0)

    def test_connect_to_server(self):
        """Test connection to MCP server."""
        # Test successful connection
        result = self.mcp_tool.connect_to_server()
        self.mock_socket.connect.assert_called_with(("localhost", 8080))
        self.assertTrue(result)
        self.assertTrue(self.mcp_tool.connected)
        
        # Test connection failure
        self.mock_socket.connect.side_effect = Exception("Connection failed")
        result = self.mcp_tool.connect_to_server()
        self.assertFalse(result)
        self.assertFalse(self.mcp_tool.connected)

    def test_send_command(self):
        """Test sending command to MCP server."""
        # Set up socket to return valid response
        self.mcp_tool.connected = True
        self.mock_socket.recv.return_value = b'{"jsonrpc": "2.0", "id": 1, "result": "success"}\n'
        
        # Test sending command
        result = self.mcp_tool.send_command("test_method", {"param": "value"})
        
        # Verify command was sent correctly
        sent_data = self.mock_socket.sendall.call_args[0][0].decode('utf-8')
        sent_json = json.loads(sent_data.strip())
        
        self.assertEqual(sent_json["method"], "test_method")
        self.assertEqual(sent_json["params"], {"param": "value"})
        self.assertEqual(sent_json["jsonrpc"], "2.0")
        
        # Verify response was parsed correctly
        self.assertEqual(result["result"], "success")
        
    def test_send_command_not_connected(self):
        """Test sending command when not connected."""
        # Set up not connected state with failed connection
        self.mcp_tool.connected = False
        self.mock_socket.connect.side_effect = Exception("Connection failed")
        
        # Try to send command
        result = self.mcp_tool.send_command("test_method", {})
        
        # Should return error
        self.assertIn("error", result)
        
    def test_receive_response(self):
        """Test receiving response from MCP server."""
        # Set up socket to return valid response
        self.mcp_tool.connected = True
        self.mock_socket.recv.return_value = b'{"jsonrpc": "2.0", "id": 1, "result": "received"}\n'
        
        # Test receiving response
        result = self.mcp_tool.receive_response()
        
        # Verify response was parsed correctly
        self.assertEqual(result["result"], "received")
        
    def test_disconnect(self):
        """Test disconnecting from MCP server."""
        # Set up connected state
        self.mcp_tool.connected = True
        
        # Test disconnect
        result = self.mcp_tool.disconnect()
        
        # Verify socket was closed
        self.mock_socket.close.assert_called_once()
        self.assertFalse(self.mcp_tool.connected)
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()