"""Action Executor - Handles execution of all automation actions."""

from typing import Dict, Any, Optional, Tuple
import time

from logger import setup_logger
from ui_automation import UIAutomationEngine
from src.core.actions import action_registry

logger = setup_logger("ActionExecutor")


class ActionExecutor:
    """Executes automation actions with comprehensive error handling."""
    
    def __init__(self, ui_engine: UIAutomationEngine):
        """Initialize action executor."""
        self.ui = ui_engine
        logger.info("Action executor initialized")
    
    def execute(self, action: str, target: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute an action with the given parameters.
        
        Returns:
            Dict with 'success' bool and optional 'error' or 'result' fields
        """
        if parameters is None:
            parameters = {}
        
        # Normalize action name
        action_def = action_registry.get_action(action)
        if action_def:
            normalized_action = action_def.name
            logger.debug(f"Normalized '{action}' to '{normalized_action}'")
        else:
            normalized_action = action.lower().replace("-", "_").replace(" ", "_")
            logger.debug(f"Unknown action '{action}', using: {normalized_action}")
        
        # Get execution method
        method_name = f"_execute_{normalized_action}"
        if hasattr(self, method_name):
            method = getattr(self, method_name)
            try:
                return method(target, parameters)
            except Exception as e:
                logger.error(f"Error executing {normalized_action}: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        # Try generic execution
        return self._execute_generic(normalized_action, target, parameters)
    
    # Application Actions
    
    def _execute_open_application(self, target: str, params: Dict) -> Dict[str, Any]:
        """Open or launch an application."""
        success = self.ui.open_application(target)
        return {"success": success}
    
    def _execute_close_application(self, target: str, params: Dict) -> Dict[str, Any]:
        """Close an application."""
        # Try Alt+F4 on the active window
        success = self.ui.hotkey('alt', 'f4')
        time.sleep(0.5)
        return {"success": success}
    
    # Keyboard Actions
    
    def _execute_type_text(self, target: str, params: Dict) -> Dict[str, Any]:
        """Type text at current cursor position."""
        text = params.get("text", target)
        
        # Skip if text is a placeholder
        if text in ["active window", "focused element", "current window", "text field"]:
            logger.debug("Skipping placeholder text")
            return {"success": True, "note": "Placeholder text skipped"}
        
        interval = params.get("interval", 0.05)
        success = self.ui.type_text(text, interval)
        return {"success": success}
    
    def _execute_press_key(self, target: str, params: Dict) -> Dict[str, Any]:
        """Press a single key."""
        key = params.get("key", target)
        presses = params.get("presses", 1)
        success = self.ui.press_key(key, presses)
        return {"success": success}
    
    def _execute_hotkey(self, target: str, params: Dict) -> Dict[str, Any]:
        """Press a combination of keys."""
        # Parse key combination
        if "+" in target:
            keys = [k.strip().lower() for k in target.split("+")]
        else:
            keys = [target.lower()]
        
        success = self.ui.hotkey(*keys)
        return {"success": success}
    
    # Mouse Actions
    
    def _execute_click(self, target: str, params: Dict) -> Dict[str, Any]:
        """Click on an element or at coordinates."""
        # Check if target is coordinates
        if "," in target:
            try:
                x, y = map(int, target.split(","))
                success = self.ui.click(x, y)
                return {"success": success}
            except ValueError:
                pass
        
        # Find element and click
        location = self._find_element(target)
        if location:
            success = self.ui.click(location[0], location[1])
            return {"success": success}
        else:
            return {"success": False, "error": f"Could not find element: {target}"}
    
    def _execute_double_click(self, target: str, params: Dict) -> Dict[str, Any]:
        """Double-click on an element."""
        location = self._find_element(target)
        if location:
            success = self.ui.double_click(location[0], location[1])
            return {"success": success}
        else:
            return {"success": False, "error": f"Could not find element: {target}"}
    
    def _execute_right_click(self, target: str, params: Dict) -> Dict[str, Any]:
        """Right-click on an element."""
        location = self._find_element(target)
        if location:
            success = self.ui.right_click(location[0], location[1])
            return {"success": success}
        else:
            return {"success": False, "error": f"Could not find element: {target}"}
    
    def _execute_drag(self, target: str, params: Dict) -> Dict[str, Any]:
        """Drag from one location to another."""
        start = params.get("start", target)
        end = params.get("end", "")
        duration = params.get("duration", 1.0)
        
        try:
            start_x, start_y = map(int, start.split(","))
            end_x, end_y = map(int, end.split(","))
            success = self.ui.drag(start_x, start_y, end_x, end_y, duration)
            return {"success": success}
        except ValueError:
            return {"success": False, "error": "Invalid drag coordinates"}
    
    def _execute_scroll(self, target: str, params: Dict) -> Dict[str, Any]:
        """Scroll up or down."""
        direction = target.lower()
        amount = params.get("amount", 3)
        
        # Parse amount if in target
        if any(word in direction for word in ["up", "down"]):
            parts = direction.split()
            if len(parts) > 1 and parts[-1].isdigit():
                amount = int(parts[-1])
            direction = parts[0]
        
        clicks = amount if "down" in direction else -amount
        success = self.ui.scroll(clicks)
        return {"success": success}
    
    # Window Actions
    
    def _execute_focus_window(self, target: str, params: Dict) -> Dict[str, Any]:
        """Focus or activate a window."""
        success = self.ui.focus_window(target)
        return {"success": success}
    
    def _execute_activate_window(self, target: str, params: Dict) -> Dict[str, Any]:
        """Activate a window (try focus first, then open)."""
        success = self.ui.focus_window(target)
        if not success:
            success = self.ui.open_application(target)
        return {"success": success}
    
    def _execute_minimize_window(self, target: str, params: Dict) -> Dict[str, Any]:
        """Minimize a window."""
        # Focus window first
        self.ui.focus_window(target)
        time.sleep(0.3)
        # Press Win+Down to minimize
        success = self.ui.hotkey('win', 'down')
        return {"success": success}
    
    def _execute_maximize_window(self, target: str, params: Dict) -> Dict[str, Any]:
        """Maximize a window."""
        self.ui.focus_window(target)
        time.sleep(0.3)
        success = self.ui.hotkey('win', 'up')
        return {"success": success}
    
    # Navigation Actions
    
    def _execute_navigate_to(self, target: str, params: Dict) -> Dict[str, Any]:
        """Navigate to a URL."""
        url = params.get("url", target)
        
        # Ensure URL has protocol
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        # Focus address bar (Ctrl+L or Alt+D)
        self.ui.hotkey('ctrl', 'l')
        time.sleep(0.3)
        
        # Type URL
        self.ui.type_text(url)
        time.sleep(0.3)
        
        # Press Enter
        self.ui.press_key('enter')
        
        return {"success": True}
    
    # System Actions
    
    def _execute_wait(self, target: str, params: Dict) -> Dict[str, Any]:
        """Wait for a specified duration."""
        seconds = params.get("seconds", 1.0)
        
        # Try to parse seconds from target
        if isinstance(target, (int, float)):
            seconds = float(target)
        elif isinstance(target, str):
            # Extract number from strings like "2 seconds", "1.5"
            import re
            match = re.search(r'(\d+\.?\d*)', target)
            if match:
                seconds = float(match.group(1))
        
        self.ui.wait(seconds)
        return {"success": True}
    
    def _execute_screenshot(self, target: str, params: Dict) -> Dict[str, Any]:
        """Take a screenshot."""
        filename = params.get("filename", target if target else None)
        filepath = self.ui.save_screenshot(filename)
        return {"success": True, "filepath": filepath}
    
    # Verification Actions
    
    def _execute_verify(self, target: str, params: Dict) -> Dict[str, Any]:
        """Verify a condition."""
        # This is a placeholder that always succeeds
        # In practice, you'd implement specific verification logic
        logger.info(f"Verification step: {target}")
        return {"success": True, "note": "Verification step"}
    
    def _execute_find_element(self, target: str, params: Dict) -> Dict[str, Any]:
        """Find a UI element."""
        location = self._find_element(target)
        return {
            "success": location is not None,
            "location": location
        }
    
    # Generic execution for unmapped actions
    
    def _execute_generic(self, action: str, target: str, params: Dict) -> Dict[str, Any]:
        """Try to infer and execute unknown actions."""
        
        action_lower = action.lower().replace("_", " ")
        
        logger.info(f"Attempting generic execution for: {action}")
        
        # Infer action type
        if any(word in action_lower for word in ["open", "launch", "start", "run"]):
            return self._execute_open_application(target, params)
        
        elif any(word in action_lower for word in ["close", "exit", "quit"]):
            return self._execute_close_application(target, params)
        
        elif any(word in action_lower for word in ["type", "write", "input", "enter"]):
            return self._execute_type_text(target, params)
        
        elif any(word in action_lower for word in ["click", "tap"]):
            return self._execute_click(target, params)
        
        elif any(word in action_lower for word in ["press", "hit"]) and "key" in action_lower:
            return self._execute_press_key(target, params)
        
        elif any(word in action_lower for word in ["focus", "activate", "switch"]):
            return self._execute_focus_window(target, params)
        
        elif any(word in action_lower for word in ["wait", "pause", "sleep"]):
            return self._execute_wait(target, params)
        
        elif any(word in action_lower for word in ["scroll"]):
            return self._execute_scroll(target, params)
        
        else:
            logger.warning(f"Cannot infer execution for action: {action}")
            return {"success": False, "error": f"Unknown action: {action}"}
    
    def _find_element(self, description: str) -> Optional[Tuple[int, int]]:
        """Find an element on screen (placeholder - uses OCR in real implementation)."""
        # Try text search first
        location = self.ui.find_text_on_screen(description)
        if location:
            logger.debug(f"Found element by text: {description}")
            return location
        
        # In production, you'd use AI vision here
        logger.debug(f"Could not find element: {description}")
        return None
