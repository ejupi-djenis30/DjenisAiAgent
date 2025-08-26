import os
import time
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
import json
import numpy as np
try:
    import cv2
    from PIL import Image
    import pytesseract
    import torch
    HAS_DEPENDENCIES = True
except ImportError:
    print("Warning: Required libraries for screen analysis not installed.")
    print("Please install: opencv-python, pillow, pytesseract, torch")
    HAS_DEPENDENCIES = False

from perception.screen_analyzer import ScreenAnalyzer
from perception.win11_capture import Win11Capture
from memory.ui_memory import UIMemory

logger = logging.getLogger(__name__)

class EnhancedScreenAnalyzer(ScreenAnalyzer):
    """
    Enhanced screen analyzer with improved UI element detection, text recognition,
    and pattern matching capabilities.
    """
    def __init__(self, 
                ocr_enabled: bool = True, 
                ui_detection_enabled: bool = True, 
                cache_dir: str = "analysis_cache",
                ui_memory: Optional[UIMemory] = None):
        """
        Initialize the enhanced screen analyzer.
        
        Args:
            ocr_enabled: Whether to enable OCR for text extraction
            ui_detection_enabled: Whether to enable UI element detection
            cache_dir: Directory to cache analysis results
            ui_memory: UIMemory instance for pattern recognition
        """
        super().__init__(ocr_enabled, ui_detection_enabled, cache_dir)
        
        # Use UI memory for pattern recognition if provided
        self.ui_memory = ui_memory or UIMemory()
        
        # Additional CV parameters for enhanced detection
        self.min_element_area = 50  # Minimum area to consider a UI element
        self.text_overlap_threshold = 0.6  # Threshold for text-element association
        
        # Enhanced OCR params
        self.ocr_config = r'--oem 3 --psm 11'  # Improved OCR mode
        
        # Common UI element patterns for Windows 11
        self.ui_patterns = {
            "button": {
                "aspect_ratio_range": (1.5, 5.0),  # width/height
                "min_size": (20, 10),
                "has_text": True
            },
            "checkbox": {
                "aspect_ratio_range": (0.8, 1.2),
                "min_size": (10, 10),
                "max_size": (30, 30)
            },
            "text_input": {
                "aspect_ratio_range": (3.0, 20.0),
                "min_size": (50, 20)
            },
            "scrollbar": {
                "aspect_ratio_range": (0.1, 0.3),
                "is_vertical": True
            }
        }
    
    def analyze(self, image: Image.Image) -> Dict[str, Any]:
        """
        Enhanced analysis of an image to extract UI elements with improved accuracy.
        
        Args:
            image: PIL Image to analyze
            
        Returns:
            Dictionary with analysis results
        """
        # Basic analysis from parent class
        results = super().analyze(image)
        
        # Enhanced UI analysis
        img_cv = np.array(image)
        img_bgr = cv2.cvtColor(img_cv, cv2.COLOR_RGB2BGR)
        
        # Enhance UI element detection
        if self.ui_detection_enabled:
            enhanced_ui_results = self._enhanced_ui_detection(img_bgr, results["text_elements"])
            results["ui_elements"] = enhanced_ui_results["ui_elements"]
            results["ui_element_count"] = len(results["ui_elements"])
            
        # Add window hierarchy estimation
        results["window_hierarchy"] = self._estimate_window_hierarchy(results["ui_elements"])
        
        # Look up patterns in UI memory
        results["recognized_patterns"] = self._recognize_patterns(results["ui_elements"])
        
        return results
    
    def _enhanced_ui_detection(self, img_bgr: np.ndarray, text_elements: List[Dict]) -> Dict[str, Any]:
        """
        Enhanced UI element detection that integrates multiple detection methods.
        
        Args:
            img_bgr: OpenCV image in BGR format
            text_elements: List of detected text elements from OCR
            
        Returns:
            Dictionary with detected UI elements
        """
        ui_elements = []
        element_id = 0
        
        # Convert to different color spaces for better element detection
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        
        # Apply multiple edge detection techniques
        edges_canny = cv2.Canny(gray, 50, 150)
        _, edges_thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        
        # Combine edge results for better detection
        edges_combined = cv2.bitwise_or(edges_canny, edges_thresh)
        
        # Find contours using combined edges
        contours, hierarchy = cv2.findContours(edges_combined, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        # Process contours to identify UI elements
        for i, contour in enumerate(contours):
            # Filter small contours
            if cv2.contourArea(contour) < self.min_element_area:
                continue
                
            x, y, w, h = cv2.boundingRect(contour)
            
            # Skip if ROI is empty or too small
            if w < 5 or h < 5:
                continue
            
            # Get ROI for feature analysis
            roi = img_bgr[y:y+h, x:x+w]
            
            # Analyze element features
            element_type, confidence = self._classify_element_type(roi, w, h)
            
            # Check if the element contains text
            contained_text, text_confidence = self._find_contained_text(x, y, w, h, text_elements)
            
            # Check if element is likely interactive
            is_interactive = self._is_likely_interactive(roi, element_type, contained_text)
            
            # Calculate element position relative to screen
            relative_pos = {
                "x_rel": x / img_bgr.shape[1],
                "y_rel": y / img_bgr.shape[0]
            }
            
            # Create element record
            ui_element = {
                "id": f"elem_{element_id}",
                "type": element_type,
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "clickable": is_interactive,
                "relative_position": relative_pos,
                "confidence": confidence,
                "contains_text": bool(contained_text),
                "text": contained_text,
                "text_confidence": text_confidence,
                "depth": 0 if hierarchy is None else hierarchy[0][i][3]  # Nesting level
            }
            
            # Add visual features
            ui_element.update(self._extract_visual_features(roi))
            
            ui_elements.append(ui_element)
            element_id += 1
            
        return {"ui_elements": ui_elements}
    
    def _classify_element_type(self, roi: np.ndarray, width: int, height: int) -> Tuple[str, float]:
        """
        Classify the type of UI element based on visual features.
        
        Args:
            roi: Region of interest (element image)
            width: Width of the element
            height: Height of the element
            
        Returns:
            Tuple of (element_type, confidence)
        """
        # Calculate aspect ratio
        aspect_ratio = width / height if height > 0 else 0
        
        # Initialize variables for classification
        element_type = "unknown"
        max_confidence = 0.0
        
        # Check against known UI patterns
        for pattern_name, pattern in self.ui_patterns.items():
            confidence = 0.0
            
            # Check aspect ratio
            if "aspect_ratio_range" in pattern:
                min_ratio, max_ratio = pattern["aspect_ratio_range"]
                if min_ratio <= aspect_ratio <= max_ratio:
                    confidence += 0.4
            
            # Check size
            if "min_size" in pattern:
                min_w, min_h = pattern["min_size"]
                if width >= min_w and height >= min_h:
                    confidence += 0.2
            
            if "max_size" in pattern:
                max_w, max_h = pattern["max_size"]
                if width <= max_w and height <= max_h:
                    confidence += 0.2
            
            # Check if vertical (for scrollbars)
            if "is_vertical" in pattern:
                is_vertical = height > width * 3
                if is_vertical == pattern["is_vertical"]:
                    confidence += 0.3
            
            # Update if this is the best match so far
            if confidence > max_confidence:
                max_confidence = confidence
                element_type = pattern_name
        
        # If no specific type detected with high confidence, use generic types
        if max_confidence < 0.4:
            if aspect_ratio > 3.0:
                element_type = "text_field"
                max_confidence = 0.3
            elif aspect_ratio < 0.3:
                element_type = "scrollbar"
                max_confidence = 0.3
            elif abs(aspect_ratio - 1.0) < 0.2:
                element_type = "icon"
                max_confidence = 0.4
            else:
                element_type = "panel"
                max_confidence = 0.2
        
        return element_type, max_confidence
    
    def _find_contained_text(self, x: int, y: int, w: int, h: int, 
                           text_elements: List[Dict]) -> Tuple[str, float]:
        """
        Find text that is contained within a UI element.
        
        Args:
            x, y, w, h: Bounding box of the UI element
            text_elements: List of text elements detected by OCR
            
        Returns:
            Tuple of (text_content, confidence)
        """
        contained_texts = []
        confidences = []
        
        for text_elem in text_elements:
            tx = text_elem["x"]
            ty = text_elem["y"]
            tw = text_elem["width"]
            th = text_elem["height"]
            
            # Calculate overlap
            x_overlap = max(0, min(x+w, tx+tw) - max(x, tx))
            y_overlap = max(0, min(y+h, ty+th) - max(y, ty))
            
            if x_overlap <= 0 or y_overlap <= 0:
                continue
                
            # Calculate overlap area as a percentage of text element area
            text_area = tw * th
            overlap_area = x_overlap * y_overlap
            overlap_ratio = overlap_area / text_area if text_area > 0 else 0
            
            # If significant overlap
            if overlap_ratio > self.text_overlap_threshold:
                contained_texts.append(text_elem["text"])
                confidences.append(text_elem.get("confidence", 0.5) * overlap_ratio)
        
        if not contained_texts:
            return "", 0.0
            
        # Join all contained text
        text = " ".join(contained_texts)
        avg_confidence = np.mean(confidences) if confidences else 0.5
        
        return text, avg_confidence
    
    def _is_likely_interactive(self, roi: np.ndarray, 
                             element_type: str, 
                             contained_text: str) -> bool:
        """
        Determine if an element is likely interactive (clickable).
        
        Args:
            roi: Region of interest (element image)
            element_type: Type of the element
            contained_text: Text contained in the element
            
        Returns:
            Boolean indicating if element is likely interactive
        """
        # Elements that are typically interactive
        interactive_types = ["button", "checkbox", "text_input", "dropdown"]
        
        # Text suggesting interactivity
        interactive_text = ["ok", "cancel", "submit", "save", "next", "back", "yes", "no"]
        
        # Check if element type suggests interactivity
        if element_type in interactive_types:
            return True
            
        # Check if text suggests interactivity
        if contained_text:
            if any(keyword in contained_text.lower() for keyword in interactive_text):
                return True
                
        # Visual features suggesting interactivity (like contrasting border)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges) / (roi.shape[0] * roi.shape[1]) if roi.size > 0 else 0
        
        # High edge density may indicate a bordered button
        if edge_density > 0.2:
            return True
            
        return False
    
    def _extract_visual_features(self, roi: np.ndarray) -> Dict[str, Any]:
        """
        Extract visual features from an element for better identification.
        
        Args:
            roi: Region of interest (element image)
            
        Returns:
            Dictionary of visual features
        """
        if roi.size == 0:
            return {"color": [0, 0, 0], "has_border": False, "texture": "unknown"}
            
        # Mean color
        mean_color = cv2.mean(roi)[:3]
        
        # Check for borders
        if roi.shape[0] > 2 and roi.shape[1] > 2:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_count = np.sum(edges > 0)
            perimeter = 2 * (roi.shape[0] + roi.shape[1])
            has_border = edge_count / perimeter > 0.5 if perimeter > 0 else False
        else:
            has_border = False
        
        # Texture analysis - simplistic approach
        if roi.shape[0] > 5 and roi.shape[1] > 5:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            # Calculate standard deviation as a simple texture measure
            texture_variation = float(np.std(gray))
            if texture_variation < 10:
                texture = "smooth"
            elif texture_variation < 30:
                texture = "moderate"
            else:
                texture = "textured"
        else:
            texture = "unknown"
            
        return {
            "color": [float(c) for c in mean_color],
            "has_border": has_border,
            "texture": texture
        }
    
    def _estimate_window_hierarchy(self, ui_elements: List[Dict]) -> List[Dict]:
        """
        Estimate the window hierarchy based on UI element positions and sizes.
        
        Args:
            ui_elements: List of detected UI elements
            
        Returns:
            Hierarchical representation of UI elements
        """
        if not ui_elements:
            return []
            
        # Sort elements by area (largest first)
        sorted_elements = sorted(
            ui_elements, 
            key=lambda e: e["width"] * e["height"], 
            reverse=True
        )
        
        # Build hierarchy - simple approach using containment
        hierarchy = []
        processed_ids = set()
        
        # Process top-level containers first (usually largest elements)
        for i, elem in enumerate(sorted_elements):
            if elem["id"] in processed_ids:
                continue
                
            processed_ids.add(elem["id"])
            
            # Create hierarchy node
            node = {
                "id": elem["id"],
                "type": elem["type"],
                "bounds": {
                    "x": elem["x"],
                    "y": elem["y"],
                    "width": elem["width"],
                    "height": elem["height"]
                },
                "children": []
            }
            
            # Find children (elements contained within this element)
            for child_elem in sorted_elements:
                if child_elem["id"] in processed_ids:
                    continue
                    
                # Check if child is contained within parent
                if (elem["x"] <= child_elem["x"] and
                    elem["y"] <= child_elem["y"] and
                    elem["x"] + elem["width"] >= child_elem["x"] + child_elem["width"] and
                    elem["y"] + elem["height"] >= child_elem["y"] + child_elem["height"]):
                    
                    processed_ids.add(child_elem["id"])
                    
                    # Add as child
                    node["children"].append({
                        "id": child_elem["id"],
                        "type": child_elem["type"],
                        "bounds": {
                            "x": child_elem["x"],
                            "y": child_elem["y"],
                            "width": child_elem["width"],
                            "height": child_elem["height"]
                        }
                    })
            
            hierarchy.append(node)
        
        # Add remaining elements that weren't identified as children
        for elem in sorted_elements:
            if elem["id"] not in processed_ids:
                hierarchy.append({
                    "id": elem["id"],
                    "type": elem["type"],
                    "bounds": {
                        "x": elem["x"],
                        "y": elem["y"],
                        "width": elem["width"],
                        "height": elem["height"]
                    },
                    "children": []
                })
                
        return hierarchy
    
    def _recognize_patterns(self, ui_elements: List[Dict]) -> List[Dict]:
        """
        Recognize UI patterns based on memory.
        
        Args:
            ui_elements: List of detected UI elements
            
        Returns:
            List of recognized patterns
        """
        # Use UI Memory to find known patterns
        return self.ui_memory.find_matching_patterns(ui_elements)
        
    def extract_text_with_enhanced_ocr(self, image: Image.Image) -> Dict[str, Any]:
        """
        Enhanced OCR text extraction with improved preprocessing.
        
        Args:
            image: PIL Image to extract text from
            
        Returns:
            Dictionary with extracted text information
        """
        if not self.ocr_enabled:
            return {"text_elements": [], "text": ""}
            
        try:
            # Make a copy of the image for preprocessing
            img_np = np.array(image)
            
            # Apply preprocessing for better OCR
            # Convert to grayscale
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            
            # Apply adaptive thresholding
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 11, 2
            )
            
            # Remove noise
            kernel = np.ones((1, 1), np.uint8)
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            
            # Convert back to PIL Image
            processed_img = Image.fromarray(opening)
            
            # Extract text using enhanced configuration
            text = pytesseract.image_to_string(processed_img, config=self.ocr_config)
            
            # Extract text with position information
            data = pytesseract.image_to_data(
                processed_img, 
                output_type=pytesseract.Output.DICT,
                config=self.ocr_config
            )
            
            text_elements = []
            
            # Process each detected text element
            for i in range(len(data['text'])):
                # Skip empty text
                if not data['text'][i].strip():
                    continue
                    
                # Skip low confidence text
                if int(data['conf'][i]) < 30:
                    continue
                    
                text_elements.append({
                    "text": data['text'][i],
                    "x": data['left'][i],
                    "y": data['top'][i],
                    "width": data['width'][i],
                    "height": data['height'][i],
                    "confidence": float(data['conf'][i]) / 100 if data['conf'][i] > 0 else 0,
                    "block_num": data['block_num'][i],  # Track text blocks
                    "line_num": data['line_num'][i]     # Track text lines
                })
                
            # Group text by lines for better context
            text_by_line = {}
            for elem in text_elements:
                key = f"{elem['block_num']}_{elem['line_num']}"
                if key not in text_by_line:
                    text_by_line[key] = []
                text_by_line[key].append(elem)
            
            # Sort each line by x-coordinate
            for key in text_by_line:
                text_by_line[key].sort(key=lambda e: e['x'])
            
            # Reconstruct lines
            line_texts = []
            for key, elems in sorted(text_by_line.items()):
                line_text = " ".join(e['text'] for e in elems)
                line_texts.append(line_text)
            
            # Final text with line breaks
            final_text = "\n".join(line_texts)
                
            return {
                "text_elements": text_elements,
                "text_by_line": line_texts,
                "text": final_text
            }
            
        except Exception as e:
            logger.error(f"Error extracting text with enhanced OCR: {str(e)}")
            return {"text_elements": [], "text": ""}
            
    def analyze_accessibility_information(self, screenshot: Image.Image) -> Dict[str, Any]:
        """
        Analyze accessibility information in the screenshot.
        Uses Windows UI Automation framework when available (Windows only).
        
        Returns:
            Dictionary with accessibility information
        """
        # This is a placeholder - in a real implementation, this would
        # connect to accessibility APIs for the operating system
        # For Windows, this would use UIAutomation or pywinauto
        # For now, return a placeholder structure
        
        return {
            "accessibility_available": False,
            "accessibility_elements": [],
            "accessibility_tree": {},
            "note": "Accessibility analysis not implemented in this version"
        }
