"""Action Executor - Handles execution of all automation actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List, TYPE_CHECKING
import time
from datetime import datetime
import difflib

from src.utils.logger import setup_logger
from src.config.config import config
from src.automation.ui_automation import UIAutomationEngine, MouseMoveTelemetry
from src.core.actions import action_registry

logger = setup_logger("ActionExecutor")

if TYPE_CHECKING:
    from src.core.gemini_client import EnhancedGeminiClient


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
    
    def __init__(
        self,
        ui_engine: UIAutomationEngine,
        gemini_client: Optional["EnhancedGeminiClient"] = None,
    ):
        """Initialize action executor."""
        self.ui = ui_engine
        self.gemini = gemini_client
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
    
    def _serialize_mouse_telemetry(self, telemetry: MouseMoveTelemetry) -> Dict[str, Any]:
        """Convert telemetry dataclass into JSON-friendly dict."""

        return {
            "success": telemetry.success,
            "attempts": telemetry.attempts,
            "target": telemetry.target,
            "final_position": telemetry.final_position,
            "residual_offset": telemetry.residual_offset,
            "tolerance": telemetry.tolerance,
            "path": [
                {
                    "timestamp": point.timestamp,
                    "x": point.x,
                    "y": point.y,
                    "duration": point.duration,
                }
                for point in telemetry.path
            ],
            "corrections_applied": telemetry.corrections_applied,
        }

    def _auto_correct_mouse_target(
        self,
        description: str,
        requested_target: Tuple[int, int],
        telemetry: MouseMoveTelemetry,
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Use vision model to propose corrected mouse coordinates."""

        if not self.gemini:
            logger.debug("Gemini client unavailable – skipping auto mouse correction")
            return None

        focus_image = None
        focus_center: Optional[Tuple[int, int]] = telemetry.final_position or telemetry.target

        try:
            screenshot = self.ui.take_screenshot()
            if focus_center:
                try:
                    focus_image = self.ui.crop_focus_region(screenshot, focus_center)
                except Exception as exc:  # pragma: no cover - crop should rarely fail
                    logger.debug(f"Unable to crop focus region for correction: {exc}")
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.debug(f"Failed to capture screenshot for auto correction: {exc}")
            return None

        path_excerpt = [
            {"x": pt.x, "y": pt.y, "duration": round(pt.duration, 4)}
            for pt in telemetry.path[-10:]
        ]

        prompt = f"""We attempted to align the mouse cursor with a target.

TARGET DESCRIPTION: {description}
REQUESTED COORDINATES: {requested_target}
FINAL POSITION REACHED: {telemetry.final_position}
RESIDUAL OFFSET (target - final): {telemetry.residual_offset}
TOLERANCE: ±{telemetry.tolerance}px
MOVEMENT ATTEMPTS: {telemetry.attempts}
PATH TRACE (last points): {path_excerpt}

Analyze the screenshot and report refined coordinates for the target if visible.

Respond with JSON only, using this schema:
{{
  "found": true/false,
  "x": <int>,
  "y": <int>,
  "confidence": "high|medium|low",
  "reason": "Detailed reasoning about the correction",
  "notes": "Any advice for future attempts"
}}

If the target cannot be identified, set "found" to false and explain in "reason"."""

        additional_images = [focus_image] if focus_image is not None else None
        response = self.gemini.analyze_screen(
            screenshot,
            prompt,
            additional_images=additional_images,
        )

        import json

        candidate: Optional[Dict[str, Any]] = None
        try:
            json_blob = response
            if "```json" in response:
                json_blob = response.split("```json")[1].split("```", 1)[0].strip()
            elif "```" in response:
                json_blob = response.split("```", 1)[1].split("```", 1)[0].strip()
            candidate = json.loads(json_blob)
        except Exception as exc:
            logger.debug(f"Auto correction JSON parse failed: {exc}")
            logger.debug(f"Gemini response: {response[:400]}")
            return None

        if not candidate or not candidate.get("found"):
            logger.info("Gemini could not identify better coordinates for target")
            return {
                "suggestion": candidate,
                "telemetry": telemetry,
            }

        try:
            suggested_x = int(candidate["x"])
            suggested_y = int(candidate["y"])
        except (KeyError, ValueError, TypeError):
            logger.debug(f"Invalid coordinate suggestion returned: {candidate}")
            return None

        logger.info(
            f"Gemini suggests refined mouse coordinates ({suggested_x}, {suggested_y}) "
            f"with confidence {candidate.get('confidence', 'unknown')}"
        )

        refined_telemetry = self.ui.move_to(
            suggested_x,
            suggested_y,
            duration=float(params.get("duration", config.mouse_base_duration)),
            tolerance=params.get("tolerance"),
            max_attempts=params.get("max_attempts"),
            return_telemetry=True,
        )

        result_payload: Dict[str, Any] = {
            "suggestion": candidate,
            "telemetry": refined_telemetry
            if isinstance(refined_telemetry, MouseMoveTelemetry)
            else telemetry,
        }

        if focus_center:
            result_payload["focus_center"] = focus_center

        if isinstance(refined_telemetry, MouseMoveTelemetry):
            return result_payload

        # move_to returning bool indicates failure to fetch telemetry; wrap into dict for consistency
        current_pos = self.ui.get_mouse_position()
        fallback_telemetry = MouseMoveTelemetry(
            success=bool(refined_telemetry),
            attempts=telemetry.attempts,
            target=(suggested_x, suggested_y),
            final_position=current_pos,
            residual_offset=(
                suggested_x - current_pos[0],
                suggested_y - current_pos[1],
            ),
            tolerance=params.get("tolerance", config.mouse_tolerance_px),
            path=[],
            corrections_applied=[],
        )

        result_payload["telemetry"] = fallback_telemetry
        return result_payload

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
        
        move_duration = float(params.get("duration", config.mouse_base_duration or 0.5))
        telemetry_attempts: List[MouseMoveTelemetry] = []

        telemetry_raw = self.ui.move_to(
            x,
            y,
            duration=move_duration,
            tolerance=params.get("tolerance"),
            max_attempts=params.get("max_attempts"),
            return_telemetry=True,
        )

        if isinstance(telemetry_raw, MouseMoveTelemetry):
            telemetry = telemetry_raw
        else:
            logger.warning("Telemetry unavailable from move_to; falling back to simple click")
            telemetry = MouseMoveTelemetry(
                success=bool(telemetry_raw),
                attempts=1,
                target=(x, y),
                final_position=self.ui.get_mouse_position(),
                residual_offset=(0, 0),
                tolerance=params.get("tolerance", config.mouse_tolerance_px),
                path=[],
                corrections_applied=[],
            )
        telemetry_attempts.append(telemetry)

        auto_correction_result: Optional[Dict[str, Any]] = None

        if not telemetry.success and params.get("auto_correct", True):
            logger.warning(
                "Mouse failed to reach target within tolerance; requesting AI correction"
            )
            auto_correction_result = self._auto_correct_mouse_target(
                target,
                (x, y),
                telemetry,
                params,
            )

            if auto_correction_result and "telemetry" in auto_correction_result:
                refined = auto_correction_result["telemetry"]
                if isinstance(refined, MouseMoveTelemetry):
                    telemetry = refined
                    telemetry_attempts.append(refined)
                else:
                    logger.debug("Auto correction did not return telemetry dataclass")

        serialized_history: List[Dict[str, Any]] = []
        focus_centers: List[Tuple[int, int]] = []

        for attempt_index, attempt in enumerate(telemetry_attempts, start=1):
            record = self._serialize_mouse_telemetry(attempt)

            center = attempt.final_position or attempt.target
            if center:
                record["focus_center"] = center
                if config.enable_screen_recording:
                    focus_centers.append(center)

            serialized_history.append(record)

        if config.enable_screen_recording and focus_centers:
            unique_focus = []
            for center in focus_centers:
                if center not in unique_focus:
                    unique_focus.append(center)
            focus_centers = unique_focus[-config.screen_focus_history :]

        base_metadata = self._serialize_mouse_telemetry(telemetry)
        current_metadata: Dict[str, Any] = {
            **base_metadata,
            "history": serialized_history,
            "auto_correction": (
                auto_correction_result.get("suggestion") if auto_correction_result else None
            ),
        }

        if focus_centers:
            current_metadata["focus_centers"] = focus_centers

        if telemetry.success:
            final_x, final_y = telemetry.final_position
            logger.info(
                f"✓ Mouse positioned within ±{telemetry.tolerance}px at {telemetry.final_position}"
            )
            print(
                f"   ✓ Mouse locked at {telemetry.final_position} (offset {telemetry.residual_offset})"
            )
            success = self.ui.click(final_x, final_y)
            return {
                "success": success,
                "mouse": current_metadata,
            }

        logger.warning(
            f"Mouse remained outside tolerance after corrections. Residual offset: {telemetry.residual_offset}"
        )
        print(
            f"   ⚠️ Mouse offset still {telemetry.residual_offset} beyond ±{telemetry.tolerance}px"
        )
        return {
            "success": False,
            "error": "Mouse position mismatch",
            "mouse": current_metadata,
        }
    
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
        
        telemetry_raw = self.ui.move_to(
            x,
            y,
            duration=float(params.get("duration", config.mouse_base_duration or 0.5)),
            tolerance=params.get("tolerance"),
            max_attempts=params.get("max_attempts"),
            return_telemetry=True,
        )

        if isinstance(telemetry_raw, MouseMoveTelemetry):
            telemetry = telemetry_raw
        else:
            telemetry = MouseMoveTelemetry(
                success=bool(telemetry_raw),
                attempts=1,
                target=(x, y),
                final_position=self.ui.get_mouse_position(),
                residual_offset=(0, 0),
                tolerance=params.get("tolerance", config.mouse_tolerance_px),
                path=[],
                corrections_applied=[],
            )

        base_metadata = self._serialize_mouse_telemetry(telemetry)
        metadata = dict(base_metadata)
        history: List[Dict[str, Any]] = [dict(base_metadata)]

        center = telemetry.final_position or telemetry.target
        if center:
            history[0]["focus_center"] = center
            if config.enable_screen_recording:
                metadata["focus_centers"] = [center]

        metadata["history"] = history

        print(
            f"   📍 Mouse at {telemetry.final_position} (offset {telemetry.residual_offset}, tolerance ±{telemetry.tolerance}px)"
        )

        return {
            "success": telemetry.success,
            "position": telemetry.final_position,
            "target": (x, y),
            "mouse": metadata,
        }
    
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
