"""Action Executor - Handles execution of all automation actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List
import time
from datetime import datetime
import difflib

from src.utils.logger import setup_logger
from src.config.config import config
from src.automation.ui_automation import UIAutomationEngine
from src.core.actions import action_registry

logger = setup_logger("ActionExecutor")


@dataclass
class ActionResult:
    """Structured telemetry for a single automation action."""

    action: str
    target: str
    parameters: Dict[str, Any]
    success: bool
    started_at: float
    finished_at: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Return execution time in seconds."""
        return max(0.0, self.finished_at - self.started_at)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result for logs/history."""
        return {
            "action": self.action,
            "target": self.target,
            "parameters": self.parameters,
            "success": self.success,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": self.duration,
            "error": self.error,
            "metadata": self.metadata,
        }


class ActionExecutor:
    """Executes automation actions with comprehensive error handling."""
    
    def __init__(self, ui_engine: UIAutomationEngine):
        """Initialize action executor."""
        self.ui = ui_engine
        logger.info("Action executor initialized")
    
    def execute(
        self,
        action: str,
        target: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> ActionResult:
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
        start_time = time.time()

        if hasattr(self, method_name):
            method = getattr(self, method_name)
            try:
                raw_result = method(target, parameters)
            except Exception as e:
                logger.error(f"Error executing {normalized_action}: {e}", exc_info=True)
                raw_result = {"success": False, "error": str(e)}
        else:
            raw_result = self._execute_generic(normalized_action, target, parameters)

        finished_at = time.time()
        return self._convert_result(
            normalized_action,
            target,
            parameters,
            raw_result,
            start_time,
            finished_at
        )

    # -- Internal helpers -------------------------------------------------

    def _convert_result(
        self,
        action: str,
        target: str,
        parameters: Dict[str, Any],
        raw_result: Any,
        started_at: float,
        finished_at: float
    ) -> ActionResult:
        """Normalize loose handler outputs into :class:`ActionResult`."""

        success = False
        error: Optional[str] = None
        metadata: Dict[str, Any] = {}

        if isinstance(raw_result, ActionResult):
            return raw_result

        if isinstance(raw_result, dict):
            success = bool(raw_result.get("success", False))
            error = raw_result.get("error")
            metadata = {
                k: v
                for k, v in raw_result.items()
                if k not in {"success", "error"}
            }
        else:
            success = bool(raw_result)

        result = ActionResult(
            action=action,
            target=target,
            parameters=parameters,
            success=success,
            started_at=started_at,
            finished_at=finished_at,
            error=error,
            metadata=metadata,
        )

        if not success and not error:
            result.error = "Unknown execution failure"

        return result
    
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
    
    def _parse_coordinates(self, coord_str: str) -> Optional[Tuple[int, int]]:
        """Parse coordinate string like '100,200' into tuple."""
        try:
            if "," in coord_str:
                x, y = map(int, coord_str.split(","))
                return (x, y)
        except (ValueError, AttributeError):
            pass
        return None
    
    def _execute_click(self, target: str, params: Dict) -> Dict[str, Any]:
        """Click on an element or at coordinates with position verification."""
        # Get coordinates from params or target
        x = params.get("x")
        y = params.get("y")
        
        if x is not None and y is not None:
            # Coordinates provided in params
            x, y = int(x), int(y)
        else:
            # Check if target is coordinates
            coords = self._parse_coordinates(target)
            if coords:
                x, y = coords
            else:
                # Try to find element
                location = self._find_element(target)
                if location:
                    x, y = location
                else:
                    return {"success": False, "error": f"Could not find element: {target}"}
        
        # Move mouse to target position first
        logger.info(f"Moving mouse to ({x}, {y})")
        self.ui.move_to(x, y)
        time.sleep(0.3)  # Brief pause for mouse to move
        
        # Verify mouse is at expected position
        current_pos = self.ui.get_mouse_position()
        if current_pos:
            actual_x, actual_y = current_pos
            # Allow small tolerance (±5 pixels)
            if abs(actual_x - x) > 5 or abs(actual_y - y) > 5:
                logger.warning(f"Mouse position mismatch! Expected ({x}, {y}), got ({actual_x}, {actual_y})")
                logger.warning(f"Offset: ({actual_x - x}, {actual_y - y})")
                print(f"   ⚠️  Mouse position verification:")
                print(f"      Expected: ({x}, {y})")
                print(f"      Actual: ({actual_x}, {actual_y})")
                print(f"      Offset: ({actual_x - x}, {actual_y - y})")
                
                # Return position info for AI to adjust
                return {
                    "success": False,
                    "error": "Mouse position mismatch",
                    "expected": (x, y),
                    "actual": (actual_x, actual_y),
                    "offset": (actual_x - x, actual_y - y)
                }
            else:
                logger.info(f"✓ Mouse position verified at ({actual_x}, {actual_y})")
                print(f"   ✓ Mouse position verified")
        
        # Click at current position
        success = self.ui.click(x, y)
        return {"success": success}
    
    def _execute_move_to(self, target: str, params: Dict) -> Dict[str, Any]:
        """Move mouse to coordinates with position verification."""
        # Get coordinates from params or target
        x = params.get("x")
        y = params.get("y")
        
        if x is not None and y is not None:
            x, y = int(x), int(y)
        else:
            # Check if target is coordinates
            coords = self._parse_coordinates(target)
            if coords:
                x, y = coords
            else:
                return {"success": False, "error": f"Invalid coordinates: {target}"}
        
        # Move mouse
        logger.info(f"Moving mouse to ({x}, {y})")
        success = self.ui.move_to(x, y)
        time.sleep(0.2)
        
        # Verify position
        current_pos = self.ui.get_mouse_position()
        if current_pos:
            actual_x, actual_y = current_pos
            logger.info(f"Mouse moved to ({actual_x}, {actual_y})")
            print(f"   📍 Mouse at ({actual_x}, {actual_y})")
            
            return {
                "success": success,
                "position": (actual_x, actual_y),
                "target": (x, y)
            }
        
        return {"success": success}
    
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
    
    # Advanced Action Handlers
    
    def _execute_copy(self, target: str, params: Dict) -> Dict[str, Any]:
        """Copy selected content."""
        self.ui.hotkey('ctrl', 'c')
        return {"success": True}
    
    def _execute_paste(self, target: str, params: Dict) -> Dict[str, Any]:
        """Paste clipboard content."""
        self.ui.hotkey('ctrl', 'v')
        return {"success": True}
    
    def _execute_cut(self, target: str, params: Dict) -> Dict[str, Any]:
        """Cut selected content."""
        self.ui.hotkey('ctrl', 'x')
        return {"success": True}
    
    def _execute_select_all(self, target: str, params: Dict) -> Dict[str, Any]:
        """Select all content."""
        self.ui.hotkey('ctrl', 'a')
        return {"success": True}
    
    def _execute_undo(self, target: str, params: Dict) -> Dict[str, Any]:
        """Undo last action."""
        self.ui.hotkey('ctrl', 'z')
        return {"success": True}
    
    def _execute_redo(self, target: str, params: Dict) -> Dict[str, Any]:
        """Redo last action."""
        self.ui.hotkey('ctrl', 'y')
        return {"success": True}
    
    def _execute_save(self, target: str, params: Dict) -> Dict[str, Any]:
        """Save file/document."""
        self.ui.hotkey('ctrl', 's')
        return {"success": True}
    
    def _execute_find_text(self, target: str, params: Dict) -> Dict[str, Any]:
        """Open find dialog."""
        self.ui.hotkey('ctrl', 'f')
        return {"success": True}
    
    def _execute_new_tab(self, target: str, params: Dict) -> Dict[str, Any]:
        """Open new tab."""
        self.ui.hotkey('ctrl', 't')
        return {"success": True}
    
    def _execute_close_tab(self, target: str, params: Dict) -> Dict[str, Any]:
        """Close current tab."""
        self.ui.hotkey('ctrl', 'w')
        return {"success": True}
    
    def _execute_switch_tab(self, target: str, params: Dict) -> Dict[str, Any]:
        """Switch tabs."""
        direction = target.lower() if target else "next"
        if "prev" in direction or "back" in direction:
            self.ui.hotkey('ctrl', 'shift', 'tab')
        else:
            self.ui.hotkey('ctrl', 'tab')
        return {"success": True}
    
    def _execute_refresh(self, target: str, params: Dict) -> Dict[str, Any]:
        """Refresh/reload page."""
        self.ui.press_key('f5')
        return {"success": True}
    
    def _execute_zoom_in(self, target: str, params: Dict) -> Dict[str, Any]:
        """Zoom in."""
        self.ui.hotkey('ctrl', 'plus')
        return {"success": True}
    
    def _execute_zoom_out(self, target: str, params: Dict) -> Dict[str, Any]:
        """Zoom out."""
        self.ui.hotkey('ctrl', 'minus')
        return {"success": True}
    
    def _execute_fullscreen(self, target: str, params: Dict) -> Dict[str, Any]:
        """Toggle fullscreen."""
        self.ui.press_key('f11')
        return {"success": True}
    
    def _execute_read_text(self, target: str, params: Dict) -> Dict[str, Any]:
        """Read text from screen."""
        text = self.ui.find_text_on_screen(target)
        return {"success": text is not None, "text": text}
    
    def _execute_get_clipboard(self, target: str, params: Dict) -> Dict[str, Any]:
        """Get clipboard content."""
        import pyperclip
        try:
            content = pyperclip.paste()
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _execute_set_clipboard(self, target: str, params: Dict) -> Dict[str, Any]:
        """Set clipboard content."""
        import pyperclip
        try:
            text = target or params.get("text", "")
            pyperclip.copy(text)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _execute_run_command(self, target: str, params: Dict) -> Dict[str, Any]:
        """Run system command."""
        import subprocess
        try:
            command = target or params.get("command", "")
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _execute_move_mouse(self, target: str, params: Dict) -> Dict[str, Any]:
        """Move mouse to position."""
        coords = self._parse_coordinates(target)
        if coords:
            x, y = coords
            self.ui.move_to(x, y)
            return {"success": True, "position": (x, y)}
        return {"success": False, "error": "Invalid coordinates"}
    
    def _execute_get_mouse_position(self, target: str, params: Dict) -> Dict[str, Any]:
        """Get current mouse position."""
        pos = self.ui.get_mouse_position()
        return {"success": True, "position": pos}
    
    def _execute_take_screenshot_region(self, target: str, params: Dict) -> Dict[str, Any]:
        """Take screenshot of specific region."""
        try:
            x = params.get("x", 0)
            y = params.get("y", 0)
            width = params.get("width", 500)
            height = params.get("height", 500)
            
            import pyautogui
            from pathlib import Path
            screenshot = pyautogui.screenshot(region=(x, y, width, height))
            
            # Save screenshot
            screenshot_path = config.screenshots_dir / f"region_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            screenshot.save(screenshot_path)
            
            return {"success": True, "path": str(screenshot_path)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
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
            suggestions = self._suggest_actions(action)
            error_msg = f"Unknown action: {action}"
            metadata = {"suggestions": suggestions} if suggestions else {}
            logger.warning(f"Cannot infer execution for action: {action}")
            if metadata:
                logger.warning(f"Suggested alternatives: {', '.join(suggestions)}")
            return {"success": False, "error": error_msg, **metadata}
    
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

    def _suggest_actions(self, action_name: str) -> List[str]:
        """Suggest close action matches for unknown commands."""

        available = [definition.name for definition in action_registry.get_all_actions()]
        suggestions = difflib.get_close_matches(action_name, available, n=3, cutoff=0.4)
        if not suggestions:
            alias_candidates = list(action_registry.actions.keys())
            suggestions = difflib.get_close_matches(action_name, alias_candidates, n=3, cutoff=0.5)
        return suggestions
