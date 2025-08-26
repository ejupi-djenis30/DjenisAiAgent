import unittest
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock, mock_open
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.perception.screen_analyzer import ScreenAnalyzer
from src.perception.win11_capture import Win11Capture

class TestWin11Capture(unittest.TestCase):

    @patch('src.perception.win11_capture.pyautogui')
    @patch('src.perception.win11_capture.cv2')
    @patch('src.perception.win11_capture.os.makedirs')
    def setUp(self, mock_makedirs, mock_cv2, mock_pyautogui):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.win11_capture = Win11Capture(screenshot_dir=self.temp_dir)
        
        # Mock PIL Image
        self.mock_screenshot = MagicMock()
        self.mock_screenshot.size = (1920, 1080)
        mock_pyautogui.screenshot.return_value = self.mock_screenshot

    def tearDown(self):
        """Clean up after tests."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.perception.win11_capture.pyautogui')
    def test_capture_screen(self, mock_pyautogui):
        """Test screen capture functionality."""
        # Mock screenshot
        mock_img = MagicMock()
        mock_pyautogui.screenshot.return_value = mock_img
        
        # Test capture with no region
        result = self.win11_capture.capture_screen()
        mock_pyautogui.screenshot.assert_called_with(region=None)
        self.assertEqual(result, mock_img)
        
        # Test capture with region
        region = (0, 0, 800, 600)
        result = self.win11_capture.capture_screen(region=region)
        mock_pyautogui.screenshot.assert_called_with(region=region)
        self.assertEqual(result, mock_img)

    @patch('src.perception.win11_capture.cv2')
    @patch('numpy.array')
    def test_process_capture(self, mock_np_array, mock_cv2):
        """Test image processing functionality."""
        # Mock numpy array and cv2
        mock_array = MagicMock()
        mock_np_array.return_value = mock_array
        
        mock_processed = MagicMock()
        mock_cv2.cvtColor.return_value = mock_processed
        
        # Process a capture
        result = self.win11_capture.process_capture(self.mock_screenshot)
        
        # Verify processing
        mock_np_array.assert_called_with(self.mock_screenshot)
        mock_cv2.cvtColor.assert_called_with(mock_array, mock_cv2.COLOR_RGB2BGR)
        self.assertEqual(result, mock_processed)

    @patch('builtins.open', new_callable=mock_open)
    def test_save_capture(self, mock_file):
        """Test saving screenshot functionality."""
        # Set up mocked PIL image
        self.mock_screenshot.save = MagicMock()
        
        # Test with explicit path
        file_path = os.path.join(self.temp_dir, "test_screenshot.png")
        result = self.win11_capture.save_capture(self.mock_screenshot, file_path)
        
        # Verify save was called and path returned
        self.mock_screenshot.save.assert_called_with(file_path)
        self.assertEqual(result, file_path)
        
        # Test with auto-generated path
        result = self.win11_capture.save_capture(self.mock_screenshot)
        self.mock_screenshot.save.assert_called()
        self.assertTrue(result.startswith(self.temp_dir))
        self.assertTrue(result.endswith(".png"))

class TestScreenAnalyzer(unittest.TestCase):

    @patch('src.perception.screen_analyzer.cv2')
    @patch('src.perception.screen_analyzer.pytesseract')
    @patch('src.perception.screen_analyzer.Win11Capture')
    def setUp(self, mock_win11_capture, mock_pytesseract, mock_cv2):
        """Set up test fixtures."""
        # Mock components
        mock_pytesseract.get_tesseract_version.return_value = "4.0.0"
        
        # Create analyzer
        self.screen_analyzer = ScreenAnalyzer(ocr_enabled=True, ui_detection_enabled=True)
        
        # Mock capturer
        self.mock_capturer = MagicMock()
        self.screen_analyzer.capturer = self.mock_capturer
        
        # Create test image
        self.test_image = MagicMock()
        self.test_image.size = (1920, 1080)
        
    @patch('numpy.array')
    @patch('src.perception.screen_analyzer.cv2')
    def test_analyze(self, mock_cv2, mock_np_array):
        """Test screen analysis functionality."""
        # Mock numpy and cv2
        mock_array = MagicMock()
        mock_np_array.return_value = mock_array
        
        mock_bgr = MagicMock()
        mock_cv2.cvtColor.return_value = mock_bgr
        
        # Set up color analysis mocks
        mock_cv2.resize.return_value = mock_array
        mock_cv2.kmeans.return_value = (None, MagicMock(), MagicMock())
        
        # Patch internal methods
        with patch.object(self.screen_analyzer, '_detect_ui_elements', return_value={"ui_elements": []}):
            with patch.object(self.screen_analyzer, '_extract_text', return_value={"text_elements": [], "text": ""}):
                with patch.object(self.screen_analyzer, '_analyze_colors', return_value={"dominant_colors": []}):
                    # Analyze image
                    result = self.screen_analyzer.analyze(self.test_image)
                    
                    # Verify conversion and analysis
                    mock_np_array.assert_called_with(self.test_image)
                    mock_cv2.cvtColor.assert_called_with(mock_array, mock_cv2.COLOR_RGB2BGR)
                    
                    # Check result structure
                    self.assertIn("timestamp", result)
                    self.assertIn("resolution", result)
                    self.assertIn("ui_elements", result)
                    self.assertIn("text_elements", result)
                    self.assertIn("colors", result)

    def test_extract_information(self):
        """Test information extraction from analysis results."""
        # Create mock analysis data
        analysis_data = {
            "ui_elements": [
                {
                    "id": "elem_0",
                    "type": "button",
                    "x": 100,
                    "y": 100,
                    "width": 50,
                    "height": 30,
                    "clickable": True,
                    "confidence": 0.8
                }
            ],
            "text_elements": [
                {
                    "text": "Login",
                    "x": 110,
                    "y": 105,
                    "width": 30,
                    "height": 20,
                    "confidence": 0.9
                }
            ]
        }
        
        # Extract information
        result = self.screen_analyzer.extract_information(analysis_data)
        
        # Verify extraction
        self.assertEqual(result["identified_elements"], analysis_data["ui_elements"])
        self.assertEqual(len(result["potential_actions"]), 1)
        self.assertEqual(result["potential_actions"][0]["type"], "click")
        self.assertEqual(result["potential_actions"][0]["coordinates"], (125, 115))  # Middle of button
        
    def test_make_decision_error_screen(self):
        """Test decision making for error screens."""
        # Mock extracted info for an error screen
        extracted_info = {
            "screen_state": "error",
            "potential_actions": [
                {
                    "type": "click",
                    "target": "OK button",
                    "coordinates": (500, 400),
                    "confidence": 0.9
                }
            ]
        }
        
        # Make decision
        decision = self.screen_analyzer.make_decision(extracted_info)
        
        # Verify decision
        self.assertEqual(decision["action_type"], "click")
        self.assertEqual(decision["parameters"]["x"], 500)
        self.assertEqual(decision["parameters"]["y"], 400)

    def test_make_decision_login_screen(self):
        """Test decision making for login screens."""
        # Mock extracted info for login screen
        extracted_info = {
            "screen_state": "login",
            "potential_actions": []
        }
        
        # Make decision
        decision = self.screen_analyzer.make_decision(extracted_info)
        
        # Verify decision - should ask for user input
        self.assertEqual(decision["action_type"], "report")
        self.assertTrue("login" in decision["parameters"]["message"].lower())

    def test_make_decision_unknown_screen(self):
        """Test decision making for unknown screens with actions."""
        # Mock extracted info for unknown screen with actions
        extracted_info = {
            "screen_state": "unknown",
            "potential_actions": [
                {
                    "type": "click",
                    "target": "Button 1",
                    "coordinates": (100, 200),
                    "confidence": 0.7
                },
                {
                    "type": "click",
                    "target": "Button 2",
                    "coordinates": (300, 400),
                    "confidence": 0.9
                }
            ]
        }
        
        # Make decision
        decision = self.screen_analyzer.make_decision(extracted_info)
        
        # Verify decision - should pick highest confidence action
        self.assertEqual(decision["action_type"], "click")
        self.assertEqual(decision["parameters"]["x"], 300)
        self.assertEqual(decision["parameters"]["y"], 400)
        
    def test_make_decision_no_actions(self):
        """Test decision making when no actions are available."""
        # Mock extracted info with no actions
        extracted_info = {
            "screen_state": "unknown",
            "potential_actions": []
        }
        
        # Make decision
        decision = self.screen_analyzer.make_decision(extracted_info)
        
        # Verify decision - should wait
        self.assertEqual(decision["action_type"], "wait")

if __name__ == '__main__':
    unittest.main()