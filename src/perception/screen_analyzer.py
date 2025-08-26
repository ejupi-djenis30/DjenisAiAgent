import os
import time
from typing import Dict, Any, List, Optional, Tuple
import json
import numpy as np
try:
    import cv2
    from PIL import Image
    import pytesseract
    import torch
except ImportError:
    print("Warning: Required libraries for screen analysis not installed. Please install: opencv-python, pillow, pytesseract, torch")

from perception.win11_capture import Win11Capture

class ScreenAnalyzer:
    """
    Analyzes screen content to extract UI elements, text, and other visual information.
    Uses computer vision techniques to understand the screen content.
    """
    def __init__(self, 
                ocr_enabled: bool = True, 
                ui_detection_enabled: bool = True, 
                cache_dir: str = "analysis_cache"):
        """
        Initialize the screen analyzer.
        
        Args:
            ocr_enabled: Whether to enable OCR for text extraction
            ui_detection_enabled: Whether to enable UI element detection
            cache_dir: Directory to cache analysis results
        """
        self.ocr_enabled = ocr_enabled
        self.ui_detection_enabled = ui_detection_enabled
        self.cache_dir = cache_dir
        
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
            
        # Initialize the screen capture module
        self.capturer = Win11Capture()
        
        # Set up OCR if enabled
        if ocr_enabled:
            try:
                # Check if pytesseract is properly configured
                pytesseract.get_tesseract_version()
            except Exception as e:
                print(f"Warning: OCR initialization failed: {str(e)}")
                print("Make sure Tesseract OCR is installed and in your PATH")
                self.ocr_enabled = False
                
    def capture_and_analyze(self, region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
        """
        Captures the screen and performs analysis in one step.
        
        Args:
            region: Optional tuple of (left, top, width, height) to capture a specific region
            
        Returns:
            Dictionary with analysis results
        """
        # Capture the screen
        screenshot = self.capturer.capture_screen(region=region)
        
        # Analyze the captured screen
        return self.analyze(screenshot)
    
    def analyze(self, image: Image.Image) -> Dict[str, Any]:
        """
        Analyzes an image to extract UI elements, text, and other visual information.
        
        Args:
            image: PIL Image to analyze
            
        Returns:
            Dictionary with analysis results
        """
        # Process the image for analysis
        img_cv = np.array(image)
        img_bgr = cv2.cvtColor(img_cv, cv2.COLOR_RGB2BGR)
        
        # Initialize results dictionary
        results = {
            "timestamp": time.time(),
            "resolution": image.size,
            "ui_elements": [],
            "text_elements": [],
            "colors": {}
        }
        
        # Extract UI elements if enabled
        if self.ui_detection_enabled:
            ui_results = self._detect_ui_elements(img_bgr)
            results.update(ui_results)
        
        # Extract text if OCR is enabled
        if self.ocr_enabled:
            text_results = self._extract_text(image)
            results.update(text_results)
        
        # Extract color information
        results["colors"] = self._analyze_colors(img_cv)
        
        return results
    
    def extract_information(self, analyzed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts high-level information from analyzed screen data.
        
        Args:
            analyzed_data: Output from the analyze method
            
        Returns:
            Dictionary with extracted high-level information
        """
        extracted = {
            "screen_state": "unknown",
            "identified_elements": [],
            "potential_actions": [],
            "context": {}
        }
        
        # Extract UI context
        if "ui_elements" in analyzed_data:
            elements = analyzed_data["ui_elements"]
            extracted["identified_elements"] = elements
            
            # Determine potential clickable elements
            clickable = [elem for elem in elements if elem.get("clickable", False)]
            extracted["potential_actions"] = [
                {
                    "type": "click",
                    "target": elem["id"],
                    "coordinates": (elem["x"] + elem["width"]//2, elem["y"] + elem["height"]//2),
                    "confidence": elem.get("confidence", 0.5)
                }
                for elem in clickable
            ]
        
        # Extract text context
        if "text_elements" in analyzed_data:
            text_content = " ".join([elem["text"] for elem in analyzed_data["text_elements"]])
            extracted["context"]["text_content"] = text_content
            
            # Try to determine screen state based on text
            if "error" in text_content.lower():
                extracted["screen_state"] = "error"
            elif "welcome" in text_content.lower() or "login" in text_content.lower():
                extracted["screen_state"] = "login"
            elif "menu" in text_content.lower() or "settings" in text_content.lower():
                extracted["screen_state"] = "menu"
                
        return extracted
    
    def make_decision(self, extracted_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Makes a decision based on extracted information.
        
        Args:
            extracted_info: Output from the extract_information method
            
        Returns:
            Dictionary with decision
        """
        decision = {
            "action_type": None,
            "parameters": {},
            "confidence": 0.0,
            "reasoning": ""
        }
        
        # Simple rule-based decision making
        if extracted_info["screen_state"] == "error":
            decision["action_type"] = "click"
            # Look for OK or Cancel buttons in potential actions
            ok_buttons = [
                action for action in extracted_info["potential_actions"] 
                if any(kw in action["target"].lower() for kw in ["ok", "cancel", "close", "dismiss"])
            ]
            if ok_buttons:
                best_action = max(ok_buttons, key=lambda x: x["confidence"])
                decision["parameters"] = {"x": best_action["coordinates"][0], "y": best_action["coordinates"][1]}
                decision["confidence"] = best_action["confidence"]
                decision["reasoning"] = f"Error screen detected, clicking {best_action['target']} button"
            else:
                decision["action_type"] = "escape_key"
                decision["reasoning"] = "Error screen detected, no buttons found, trying escape key"
                
        elif extracted_info["screen_state"] == "login":
            decision["action_type"] = "report"
            decision["parameters"] = {"message": "Login screen detected, user input required"}
            decision["reasoning"] = "Login requires credentials, need human input"
            
        elif extracted_info["potential_actions"]:
            # If we have potential actions but don't recognize the screen state,
            # select the highest confidence action
            best_action = max(extracted_info["potential_actions"], key=lambda x: x["confidence"])
            decision["action_type"] = best_action["type"]
            decision["parameters"] = {"x": best_action["coordinates"][0], "y": best_action["coordinates"][1]}
            decision["confidence"] = best_action["confidence"]
            decision["reasoning"] = f"Selected highest confidence action: {best_action['target']}"
            
        else:
            # Default decision if we can't determine what to do
            decision["action_type"] = "wait"
            decision["reasoning"] = "Unable to determine appropriate action, waiting for screen change"
            
        return decision
        
    def _detect_ui_elements(self, img_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Detects UI elements in the image using computer vision techniques.
        
        Args:
            img_bgr: OpenCV image in BGR format
            
        Returns:
            Dictionary with UI elements
        """
        ui_elements = []
        element_id = 0
        
        # Convert to grayscale
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        
        # Apply edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Process each contour
        for contour in contours:
            # Filter small contours (noise)
            if cv2.contourArea(contour) < 100:
                continue
                
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)
            
            # Analyze the region within the contour
            roi = img_bgr[y:y+h, x:x+w]
            
            # Skip if ROI is empty
            if roi.size == 0:
                continue
                
            # Determine if element is likely clickable
            # Simple heuristic: elements with distinct colors compared to surroundings
            # and with rectangular shapes are more likely to be buttons
            is_clickable = False
            
            # Calculate mean color
            mean_color = cv2.mean(roi)[:3]
            
            # Check if shape is approximately rectangular
            approx = cv2.approxPolyDP(contour, 0.04 * cv2.arcLength(contour, True), True)
            if len(approx) == 4:
                is_clickable = True
            
            # Add to UI elements
            ui_elements.append({
                "id": f"elem_{element_id}",
                "type": "button" if is_clickable else "element",
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "clickable": is_clickable,
                "color": [float(c) for c in mean_color],
                "confidence": 0.7 if is_clickable else 0.3
            })
            
            element_id += 1
            
        return {"ui_elements": ui_elements, "ui_element_count": len(ui_elements)}
    
    def _extract_text(self, image: Image.Image) -> Dict[str, Any]:
        """
        Extracts text from the image using OCR.
        
        Args:
            image: PIL Image to extract text from
            
        Returns:
            Dictionary with extracted text information
        """
        if not self.ocr_enabled:
            return {"text_elements": [], "text": ""}
            
        try:
            # Extract text using pytesseract
            text = pytesseract.image_to_string(image)
            
            # Extract text with position information
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            text_elements = []
            
            # Process each detected text element
            for i in range(len(data['text'])):
                # Skip empty text
                if not data['text'][i].strip():
                    continue
                    
                text_elements.append({
                    "text": data['text'][i],
                    "x": data['left'][i],
                    "y": data['top'][i],
                    "width": data['width'][i],
                    "height": data['height'][i],
                    "confidence": float(data['conf'][i]) / 100 if data['conf'][i] > 0 else 0
                })
                
            return {
                "text_elements": text_elements,
                "text": text
            }
            
        except Exception as e:
            print(f"Error extracting text: {str(e)}")
            return {"text_elements": [], "text": ""}
    
    def _analyze_colors(self, img_cv: np.ndarray) -> Dict[str, Any]:
        """
        Analyzes the color distribution in the image.
        
        Args:
            img_cv: OpenCV image
            
        Returns:
            Dictionary with color analysis
        """
        # Reduce image size for faster processing
        resized = cv2.resize(img_cv, (100, 100))
        
        # Reshape for k-means
        pixels = resized.reshape(-1, 3)
        
        # Use k-means to find dominant colors (simplified)
        pixels = pixels.astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(pixels, 5, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        # Count pixels in each cluster
        counts = np.bincount(labels.flatten())
        
        # Calculate color percentages
        total = counts.sum()
        percentages = counts / total
        
        # Convert centers to RGB
        centers = centers.astype(np.uint8)
        
        color_info = {
            "dominant_colors": [
                {
                    "rgb": [int(c) for c in centers[i]],
                    "percentage": float(percentages[i])
                }
                for i in range(len(centers))
            ],
            "brightness": float(np.mean(img_cv)),
            "contrast": float(np.std(img_cv))
        }
        
        return color_info