import os
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

class UIMemory:
    """
    Stores and retrieves UI patterns for common applications.
    This helps the agent remember successful interactions and repeat them.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize UI memory.
        
        Args:
            config: Configuration dictionary (optional)
        """
        if config is None:
            config = {}
            
        self.storage_path = config.get('ui_memory_path', 'data/ui_memory')
        self.patterns_file = config.get('ui_patterns_file', 'data/ui_patterns.json')
        self.max_entries_per_app = config.get('max_ui_memory_entries', 100)
        self.expiry_days = config.get('ui_memory_expiry_days', 30)
        self.known_patterns = self._load_patterns()
        self.ui_patterns = self._load_ui_patterns()
        
        # Create storage directory if it doesn't exist
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path, exist_ok=True)
            
    def _load_ui_patterns(self) -> Dict[str, Any]:
        """Load predefined UI patterns from file."""
        try:
            if os.path.exists(self.patterns_file):
                with open(self.patterns_file, 'r') as f:
                    return json.load(f)
            return {"common_patterns": [], "application_patterns": {}}
        except Exception as e:
            print(f"Error loading UI patterns from {self.patterns_file}: {str(e)}")
            return {"common_patterns": [], "application_patterns": {}}
        
    def _load_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load saved UI interaction patterns."""
        patterns = {}
        
        if not os.path.exists(self.storage_path):
            return patterns
            
        for filename in os.listdir(self.storage_path):
            if not filename.endswith('.json'):
                continue
                
            app_name = filename.replace('.json', '')
            file_path = os.path.join(self.storage_path, filename)
            
            try:
                with open(file_path, 'r') as f:
                    app_patterns = json.load(f)
                    
                # Filter out expired entries
                current_time = time.time()
                cutoff_time = current_time - (self.expiry_days * 24 * 60 * 60)
                valid_patterns = [
                    p for p in app_patterns 
                    if p.get('timestamp', current_time) > cutoff_time
                ]
                
                patterns[app_name] = valid_patterns
            except Exception as e:
                print(f"Error loading UI patterns for {app_name}: {str(e)}")
                patterns[app_name] = []
                
        return patterns
        
    def _save_patterns(self):
        """Save UI interaction patterns to disk."""
        for app_name, patterns in self.known_patterns.items():
            if not patterns:
                continue
                
            # Limit entries per app
            if len(patterns) > self.max_entries_per_app:
                # Keep most recent entries
                patterns.sort(key=lambda p: p.get('timestamp', 0), reverse=True)
                patterns = patterns[:self.max_entries_per_app]
                self.known_patterns[app_name] = patterns
                
            file_path = os.path.join(self.storage_path, f"{app_name}.json")
            
            try:
                with open(file_path, 'w') as f:
                    json.dump(patterns, f, indent=2)
            except Exception as e:
                print(f"Error saving UI patterns for {app_name}: {str(e)}")
        
    def remember_successful_interaction(self, app_name: str, element_descriptor: Dict[str, Any], 
                                       action_taken: Dict[str, Any], result: Dict[str, Any]):
        """
        Remember successful UI interactions.
        
        Args:
            app_name: Name of the application
            element_descriptor: Description of UI element that was interacted with
            action_taken: Action that was performed
            result: Result of the action
        """
        if app_name not in self.known_patterns:
            self.known_patterns[app_name] = []
            
        self.known_patterns[app_name].append({
            'element': element_descriptor,
            'action': action_taken,
            'result': result,
            'timestamp': time.time(),
            'datetime': datetime.now().isoformat()
        })
        
        self._save_patterns()
    
    def get_suggestions_for_app(self, app_name: str, current_ui_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get action suggestions based on previous interactions.
        
        Args:
            app_name: Name of the application
            current_ui_state: Current UI state to match against
            
        Returns:
            List of suggested actions
        """
        if app_name not in self.known_patterns:
            return []
            
        suggestions = [
            p for p in self.known_patterns[app_name] 
            if self._matches_current_state(p['element'], current_ui_state)
        ]
        
        # Sort by recency
        suggestions.sort(key=lambda p: p.get('timestamp', 0), reverse=True)
        
        return suggestions
        
    def _matches_current_state(self, saved_element: Dict[str, Any], current_ui_state: Dict[str, Any]) -> bool:
        """
        Check if saved element matches current UI state.
        
        Args:
            saved_element: Saved element descriptor
            current_ui_state: Current UI state
            
        Returns:
            True if matches, False otherwise
        """
        # Simple matching based on element type, text, and position similarity
        if 'ui_elements' not in current_ui_state:
            return False
            
        for element in current_ui_state['ui_elements']:
            # Calculate similarity score between saved_element and current element
            similarity_score = self._calculate_element_similarity(saved_element, element)
            
            if similarity_score > 0.8:  # 80% similarity threshold
                return True
                
        return False
        
    def _calculate_element_similarity(self, elem1: Dict[str, Any], elem2: Dict[str, Any]) -> float:
        """
        Calculate similarity between two UI elements.
        
        Args:
            elem1: First element
            elem2: Second element
            
        Returns:
            Similarity score (0-1)
        """
        score = 0.0
        total_weight = 0.0
        
        # Type match
        if elem1.get('type') == elem2.get('type'):
            score += 0.3
        total_weight += 0.3
        
        # Text match
        text1 = elem1.get('text')
        text2 = elem2.get('text')
        if text1 and text2:
            text1 = text1.lower()
            text2 = text2.lower()
            if text1 == text2:
                score += 0.4
            elif text1 in text2 or text2 in text1:
                score += 0.2
        total_weight += 0.4
        
        # Position similarity
        if all(k in elem1 and k in elem2 for k in ['x', 'y', 'width', 'height']):
            # Calculate position overlap
            x1 = max(elem1['x'], elem2['x'])
            y1 = max(elem1['y'], elem2['y'])
            x2 = min(elem1['x'] + elem1['width'], elem2['x'] + elem2['width'])
            y2 = min(elem1['y'] + elem1['height'], elem2['y'] + elem2['height'])
            
            if x2 > x1 and y2 > y1:
                overlap_area = (x2 - x1) * (y2 - y1)
                elem1_area = elem1['width'] * elem1['height']
                elem2_area = elem2['width'] * elem2['height']
                overlap_ratio = overlap_area / min(elem1_area, elem2_area)
                
                score += 0.3 * overlap_ratio
        total_weight += 0.3
        
        return score / total_weight if total_weight > 0 else 0.0
        
    def find_matching_patterns(self, ui_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Find UI patterns that match the detected UI elements.
        
        Args:
            ui_elements: List of detected UI elements
            
        Returns:
            List of matched patterns with their confidence scores
        """
        matched_patterns = []
        
        # Check common patterns first
        for pattern in self.ui_patterns.get("common_patterns", []):
            matches = self._find_elements_matching_pattern(ui_elements, pattern)
            matched_patterns.extend(matches)
            
        # Check application-specific patterns
        for app_name, patterns in self.ui_patterns.get("application_patterns", {}).items():
            for pattern in patterns:
                matches = self._find_elements_matching_pattern(ui_elements, pattern)
                # Add app information to matches
                for match in matches:
                    match["application"] = app_name
                matched_patterns.extend(matches)
        
        # Sort by confidence
        matched_patterns.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        return matched_patterns
    
    def _find_elements_matching_pattern(self, 
                                      ui_elements: List[Dict[str, Any]], 
                                      pattern: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find elements that match a specific pattern.
        
        Args:
            ui_elements: List of UI elements
            pattern: Pattern to match against
            
        Returns:
            List of matched elements with pattern information
        """
        matches = []
        pattern_id = pattern.get("id", "unknown_pattern")
        pattern_name = pattern.get("name", "Unknown Pattern")
        confidence_threshold = pattern.get("confidence_threshold", 0.7)
        
        for element in ui_elements:
            confidence = self._match_element_to_pattern(element, pattern)
            
            if confidence >= confidence_threshold:
                matches.append({
                    "element_id": element.get("id", ""),
                    "pattern_id": pattern_id,
                    "pattern_name": pattern_name,
                    "pattern_description": pattern.get("description", ""),
                    "confidence": confidence,
                    "element": element
                })
                
        return matches
    
    def _match_element_to_pattern(self, element: Dict[str, Any], pattern: Dict[str, Any]) -> float:
        """
        Calculate how well an element matches a pattern.
        
        Args:
            element: UI element
            pattern: Pattern to match against
            
        Returns:
            Confidence score (0-1)
        """
        confidence = 0.0
        total_checks = 0
        
        # Check visual features
        visual_features = pattern.get("visual_features", {})
        
        # Check aspect ratio
        if "aspect_ratio_range" in visual_features and "width" in element and "height" in element:
            total_checks += 1
            aspect_ratio = element["width"] / element["height"] if element["height"] > 0 else 0
            min_ratio, max_ratio = visual_features["aspect_ratio_range"]
            
            if min_ratio <= aspect_ratio <= max_ratio:
                confidence += 1.0
            elif abs(aspect_ratio - min_ratio) < 0.2 or abs(aspect_ratio - max_ratio) < 0.2:
                confidence += 0.5  # Close to range
                
        # Check size
        if "min_size" in visual_features and "width" in element and "height" in element:
            total_checks += 1
            min_w, min_h = visual_features["min_size"]
            
            if element["width"] >= min_w and element["height"] >= min_h:
                confidence += 1.0
            elif element["width"] >= min_w * 0.8 and element["height"] >= min_h * 0.8:
                confidence += 0.5  # Close to minimum size
                
        if "max_size" in visual_features and "width" in element and "height" in element:
            total_checks += 1
            max_w, max_h = visual_features["max_size"]
            
            if element["width"] <= max_w and element["height"] <= max_h:
                confidence += 1.0
            elif element["width"] <= max_w * 1.2 and element["height"] <= max_h * 1.2:
                confidence += 0.5  # Close to maximum size
        
        # Check border
        if "has_border" in visual_features and "has_border" in element:
            total_checks += 1
            if element["has_border"] == visual_features["has_border"]:
                confidence += 1.0
                
        # Check position
        if "position" in visual_features and "relative_position" in element:
            total_checks += 1
            rel_pos = element["relative_position"]
            
            if visual_features["position"] == "top" and rel_pos["y_rel"] < 0.2:
                confidence += 1.0
            elif visual_features["position"] == "bottom" and rel_pos["y_rel"] > 0.8:
                confidence += 1.0
            elif visual_features["position"] == "top-right" and rel_pos["y_rel"] < 0.2 and rel_pos["x_rel"] > 0.8:
                confidence += 1.0
            elif visual_features["position"] == "top-left" and rel_pos["y_rel"] < 0.2 and rel_pos["x_rel"] < 0.2:
                confidence += 1.0
                
        # Check text patterns
        if "text_patterns" in pattern and "text" in element and element["text"]:
            total_checks += 1
            element_text = element["text"].lower()
            
            for text_pattern in pattern["text_patterns"]:
                if text_pattern.lower() in element_text:
                    confidence += 1.0
                    break
                    
        # Return normalized confidence
        return confidence / total_checks if total_checks > 0 else 0.0
