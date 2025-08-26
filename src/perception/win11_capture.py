import os
import time
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

import numpy as np
try:
    import cv2
    import pyautogui
    import PIL.Image
    from PIL import Image
except ImportError:
    print("Warning: Required libraries for screen capture not installed. Please install: opencv-python, pyautogui, pillow")

class Win11Capture:
    """
    Screen capture utility specifically designed for Windows 11 environments.
    Provides methods to capture, process, save and analyze screen content.
    """
    def __init__(self, screenshot_dir: str = "screenshots"):
        """
        Initialize the screen capture utility.
        
        Args:
            screenshot_dir: Directory to save screenshots
        """
        self.screenshot_dir = screenshot_dir
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir, exist_ok=True)
    
    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> PIL.Image.Image:
        """
        Captures the current screen or a specific region.
        
        Args:
            region: Optional tuple of (left, top, width, height) to capture a specific region
            
        Returns:
            PIL Image object containing the captured screen
        """
        try:
            screenshot = pyautogui.screenshot(region=region)
            return screenshot
        except Exception as e:
            print(f"Error capturing screen: {str(e)}")
            # Return a blank image as a fallback
            if region:
                width, height = region[2], region[3]
            else:
                width, height = 1920, 1080  # Default resolution
            return Image.new('RGB', (width, height), color='black')
    
    def process_capture(self, image: PIL.Image.Image) -> np.ndarray:
        """
        Processes a captured image for analysis.
        
        Args:
            image: PIL Image to process
            
        Returns:
            Processed image as a numpy array
        """
        # Convert PIL Image to opencv format (numpy array)
        img_array = np.array(image)
        
        # Convert RGB to BGR format (OpenCV uses BGR)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        return img_bgr
    
    def save_capture(self, image: PIL.Image.Image, file_path: Optional[str] = None) -> str:
        """
        Saves the captured image to disk.
        
        Args:
            image: PIL Image to save
            file_path: Optional path to save the image to
            
        Returns:
            Path where the image was saved
        """
        if not file_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(self.screenshot_dir, f"screenshot_{timestamp}.png")
        
        image.save(file_path)
        return file_path
    
    def analyze_capture(self, image: PIL.Image.Image) -> Dict[str, Any]:
        """
        Performs basic analysis of the captured image.
        
        Args:
            image: PIL Image to analyze
            
        Returns:
            Dictionary with analysis results
        """
        img_array = np.array(image)
        
        # Convert to grayscale for analysis
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Detect edges
        edges = cv2.Canny(gray, 100, 200)
        
        # Calculate basic metrics
        brightness = np.mean(gray)
        contrast = np.std(gray)
        
        # Detect UI elements (basic)
        # This is a simplified version - real UI detection would be more complex
        _, thresholded = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresholded, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        ui_elements = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 10 and h > 10:  # Filter out very small elements
                ui_elements.append({
                    "x": int(x),
                    "y": int(y),
                    "width": int(w),
                    "height": int(h)
                })
        
        return {
            "resolution": image.size,
            "brightness": float(brightness),
            "contrast": float(contrast),
            "ui_elements_count": len(ui_elements),
            "ui_elements": ui_elements[:10],  # Limit to avoid too much data
            "timestamp": datetime.now().isoformat()
        }