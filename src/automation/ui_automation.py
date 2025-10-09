"""UI Automation engine for Windows."""

import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any

import pyautogui
import pywinauto
from PIL import Image
from pywinauto import Application

from src.automation.window_manager import WindowManager
from src.config.config import config
from src.core.gemini_client import EnhancedGeminiClient
from src.utils.logger import setup_logger
from src.utils.ocr import get_ocr_engine, OCRResult
from src.utils.screen_utils import ScreenUtils

logger = setup_logger("UIAutomation")

# Configure PyAutoGUI
pyautogui.FAILSAFE = True  # Move mouse to corner to abort
pyautogui.PAUSE = config.action_delay


@dataclass
class MouseTrajectoryPoint:
    """Single waypoint recorded during a mouse move."""

    timestamp: float
    x: int
    y: int
    duration: float


@dataclass
class MouseMoveTelemetry:
    """Detailed telemetry about a mouse movement."""

    success: bool
    attempts: int
    target: Tuple[int, int]
    final_position: Tuple[int, int]
    residual_offset: Tuple[int, int]
    tolerance: int
    path: List[MouseTrajectoryPoint] = field(default_factory=list)
    corrections_applied: List[Dict[str, Any]] = field(default_factory=list)


class UIAutomationEngine:
    """Engine for performing UI automation on Windows."""
    
    def __init__(self):
        """Initialize the UI automation engine."""
        self.screen_size = pyautogui.size()
        logger.info(f"Initialized UI automation engine. Screen size: {self.screen_size}")
        self._default_tolerance = config.mouse_tolerance_px
        self._max_attempts = config.mouse_max_attempts
        self._path_segments = max(0, config.mouse_path_segments)
        self._curve_jitter = config.mouse_curve_jitter
        self._base_duration = config.mouse_base_duration
        self._micro_correction = config.mouse_micro_correction_duration
        self._ocr_engine = get_ocr_engine()
        self.screen_utils = ScreenUtils(screen_size=self.screen_size, logger=logger)
        gemini_client = None
        try:
            gemini_client = EnhancedGeminiClient()
        except Exception as exc:  # pragma: no cover - network/config dependent
            logger.warning("Gemini client unavailable: %s", exc)
        self.window_manager = WindowManager(logger=logger, gemini_client=gemini_client)
        if self._ocr_engine:
            logger.info("Tesseract OCR engine detected for text search")
        else:
            logger.warning("Tesseract OCR engine unavailable; text search will be disabled")

    @staticmethod
    def _distance(a: Tuple[int, int], b: Tuple[int, int]) -> float:
        """Return Euclidean distance between two points."""
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _compute_segment_duration(self, start: Tuple[int, int], end: Tuple[int, int], base_duration: float) -> float:
        """Scale movement duration relative to travelled distance."""
        distance = self._distance(start, end)
        screen_diag = self._distance((0, 0), self.screen_size)
        normalized = distance / screen_diag if screen_diag else 0.0
        duration = max(base_duration * (0.5 + normalized * 3.2), 0.035)
        return min(duration, 1.8)

    def _generate_mouse_path(self, start: Tuple[int, int], end: Tuple[int, int], segments: int) -> List[Tuple[int, int]]:
        """Generate a curved path between two points to mimic human motion."""
        if segments <= 0:
            return []

        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        jitter = self._curve_jitter

        control_x = mid_x + random.uniform(-jitter, jitter)
        control_y = mid_y + random.uniform(-jitter, jitter)

        path: List[Tuple[int, int]] = []
        for index in range(1, segments + 1):
            t = index / (segments + 1)
            one_minus = 1 - t
            x = int(round(one_minus * one_minus * start[0] + 2 * one_minus * t * control_x + t * t * end[0]))
            y = int(round(one_minus * one_minus * start[1] + 2 * one_minus * t * control_y + t * t * end[1]))
            path.append((x, y))

        return path
        
    def take_screenshot(self, region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """Take a screenshot of the screen or a specific region."""
        return self.screen_utils.take_screenshot(region)
    
    def save_screenshot(self, filename: Optional[str] = None) -> str:
        """Take and save a screenshot."""
        return self.screen_utils.save_screenshot(filename)

    def capture_focus_region(
        self,
        center: Tuple[int, int],
        size: Optional[int] = None,
    ) -> Image.Image:
        """Capture a zoomed-in region around a coordinate for diagnostics."""
        self.screen_utils.set_screen_size(self.screen_size)
        return self.screen_utils.capture_focus_region(center, size)

    def crop_focus_region(
        self,
        image: Image.Image,
        center: Tuple[int, int],
        size: Optional[int] = None,
    ) -> Image.Image:
        """Crop a focus region from an existing screenshot."""
        self.screen_utils.set_screen_size(self.screen_size)
        return self.screen_utils.crop_focus_region(image, center, size)

    def save_focus_region(
        self,
        center: Tuple[int, int],
        size: Optional[int] = None,
        *,
        prefix: str = "focus",
        image: Optional[Image.Image] = None,
    ) -> Optional[str]:
        """Persist a focus-region capture to disk and return its path."""
        self.screen_utils.set_screen_size(self.screen_size)
        return self.screen_utils.save_focus_region(
            center,
            size,
            prefix=prefix,
            image=image,
        )
    
    def find_image_on_screen(self, template_path: str, confidence: float = 0.8) -> Optional[Tuple[int, int]]:
        """Find an image on the screen using template matching."""
        try:
            location = pyautogui.locateOnScreen(template_path, confidence=confidence)
            if location:
                center = pyautogui.center(location)
                logger.debug(f"Found image at: {center}")
                return center
            return None
        except Exception as e:
            logger.debug(f"Image not found: {e}")
            return None
    
    def _get_ocr_engine(self) -> Optional[Any]:
        """Return the OCR engine, reinitializing if needed."""

        if self._ocr_engine is None:
            self._ocr_engine = get_ocr_engine()
            if self._ocr_engine:
                logger.info("OCR engine initialized on-demand")
        return self._ocr_engine

    def find_text_positions(
        self,
        text: str,
        *,
        case_sensitive: bool = False,
        exact_match: bool = False,
        min_confidence: float = 70.0,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find occurrences of text on screen and return their coordinates."""

        engine = self._get_ocr_engine()
        if not engine:
            logger.warning("find_text_positions called but OCR engine is unavailable")
            return []

        try:
            screenshot = self.take_screenshot()
        except Exception as exc:
            logger.error(f"Unable to capture screenshot for OCR: {exc}")
            return []

        matches = engine.find_text(
            screenshot,
            text,
            case_sensitive=case_sensitive,
            exact_match=exact_match,
            min_confidence=min_confidence,
        )

        results: List[Dict[str, Any]] = []
        for match in matches:
            if not isinstance(match, OCRResult) or not match.center:
                continue

            entry = {
                "text": match.text,
                "x": match.center[0],
                "y": match.center[1],
                "confidence": match.confidence,
                "bounding_box": match.bounding_box,
            }
            results.append(entry)

        if max_results is not None and max_results >= 0:
            results = results[:max_results]

        if results:
            logger.debug(
                "Found %d match(es) for '%s': %s",
                len(results),
                text,
                [r["bounding_box"] for r in results],
            )
        else:
            logger.debug("No OCR matches for '%s'", text)

        return results

    def find_text_on_screen(
        self,
        text: str,
        *,
        case_sensitive: bool = False,
        exact_match: bool = False,
        min_confidence: float = 70.0,
    ) -> Optional[Tuple[int, int]]:
        """Return the first matching text position as (x, y) coordinates."""

        matches = self.find_text_positions(
            text,
            case_sensitive=case_sensitive,
            exact_match=exact_match,
            min_confidence=min_confidence,
            max_results=1,
        )

        if matches:
            return matches[0]["x"], matches[0]["y"]
        return None
    
    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = 'left', clicks: int = 1) -> bool:
        """Click at specified coordinates or current position."""
        try:
            if x is not None and y is not None:
                pyautogui.click(x, y, button=button, clicks=clicks)
                logger.debug(f"Clicked at ({x}, {y}) with {button} button")
            else:
                pyautogui.click(button=button, clicks=clicks)
                logger.debug(f"Clicked at current position with {button} button")
            return True
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return False
    
    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Double-click at specified coordinates."""
        return self.click(x, y, clicks=2)
    
    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Right-click at specified coordinates."""
        return self.click(x, y, button='right')
    
    def move_mouse_precise(
        self,
        x: int,
        y: int,
        *,
        tolerance: Optional[int] = None,
        max_attempts: Optional[int] = None,
        base_duration: Optional[float] = None,
        path_segments: Optional[int] = None,
    ) -> MouseMoveTelemetry:
        """Move the mouse towards a target with adaptive corrections."""

        tolerance = tolerance if tolerance is not None else self._default_tolerance
        max_attempts = max_attempts if max_attempts is not None else self._max_attempts
        base_duration = base_duration if base_duration is not None else self._base_duration
        path_segments = path_segments if path_segments is not None else self._path_segments

        target = (int(x), int(y))
        attempts = 0
        path_trace: List[MouseTrajectoryPoint] = []
        corrections: List[Dict[str, Any]] = []

        while attempts < max_attempts:
            attempts += 1
            start_pos = self.get_mouse_position()
            current_pos = start_pos
            logger.debug(
                f"Mouse move attempt {attempts}/{max_attempts} → target {target} (current: {start_pos})"
            )

            try:
                tween = getattr(pyautogui, "easeInOutQuad", None)
            except AttributeError:
                tween = None

            waypoints = self._generate_mouse_path(start_pos, target, path_segments)
            for waypoint in [*waypoints, target]:
                duration = self._compute_segment_duration(current_pos, waypoint, base_duration)
                try:
                    if tween:
                        pyautogui.moveTo(waypoint[0], waypoint[1], duration=duration, tween=tween)
                    else:
                        pyautogui.moveTo(waypoint[0], waypoint[1], duration=duration)
                except Exception as exc:
                    logger.error(f"Mouse move failure during path traversal: {exc}")
                    return MouseMoveTelemetry(
                        success=False,
                        attempts=attempts,
                        target=target,
                        final_position=self.get_mouse_position(),
                        residual_offset=(target[0] - current_pos[0], target[1] - current_pos[1]),
                        tolerance=tolerance,
                        path=path_trace,
                        corrections_applied=corrections,
                    )

                current_pos = waypoint
                path_trace.append(
                    MouseTrajectoryPoint(time.time(), waypoint[0], waypoint[1], duration)
                )

            final_pos = self.get_mouse_position()
            offset = (target[0] - final_pos[0], target[1] - final_pos[1])

            if abs(offset[0]) <= tolerance and abs(offset[1]) <= tolerance:
                logger.debug(f"Mouse arrived within tolerance {tolerance}px at {final_pos}")
                return MouseMoveTelemetry(
                    success=True,
                    attempts=attempts,
                    target=target,
                    final_position=final_pos,
                    residual_offset=offset,
                    tolerance=tolerance,
                    path=path_trace,
                    corrections_applied=corrections,
                )

            # Apply micro correction relative to residual offset
            logger.debug(f"Residual offset detected {offset} – applying micro correction")
            correction_duration = max(self._micro_correction, base_duration * 0.4)

            try:
                if tween:
                    pyautogui.moveRel(offset[0], offset[1], duration=correction_duration, tween=tween)
                else:
                    pyautogui.moveRel(offset[0], offset[1], duration=correction_duration)
            except Exception as exc:
                logger.error(f"Micro correction failed: {exc}")
                break

            corrected_pos = self.get_mouse_position()
            corrected_offset = (target[0] - corrected_pos[0], target[1] - corrected_pos[1])
            corrections.append(
                {
                    "attempt": attempts,
                    "initial_offset": offset,
                    "post_correction_offset": corrected_offset,
                    "duration": correction_duration,
                    "timestamp": time.time(),
                }
            )
            path_trace.append(
                MouseTrajectoryPoint(time.time(), corrected_pos[0], corrected_pos[1], correction_duration)
            )

            if abs(corrected_offset[0]) <= tolerance and abs(corrected_offset[1]) <= tolerance:
                logger.debug(
                    f"Micro correction succeeded – final position {corrected_pos} within tolerance"
                )
                return MouseMoveTelemetry(
                    success=True,
                    attempts=attempts,
                    target=target,
                    final_position=corrected_pos,
                    residual_offset=corrected_offset,
                    tolerance=tolerance,
                    path=path_trace,
                    corrections_applied=corrections,
                )

            # Reduce duration gradually for successive attempts to avoid oscillation
            base_duration = max(base_duration * 0.65, self._micro_correction)

        logger.warning(
            f"Unable to position mouse within tolerance after {attempts} attempts; "
            f"final position {corrected_pos if 'corrected_pos' in locals() else final_pos}"  # type: ignore[name-defined]
        )

        last_pos = self.get_mouse_position()
        final_offset = (target[0] - last_pos[0], target[1] - last_pos[1])
        return MouseMoveTelemetry(
            success=False,
            attempts=attempts,
            target=target,
            final_position=last_pos,
            residual_offset=final_offset,
            tolerance=tolerance,
            path=path_trace,
            corrections_applied=corrections,
        )

    def move_mouse(
        self,
        x: int,
        y: int,
        duration: float = 0.5,
        *,
        tolerance: Optional[int] = None,
        max_attempts: Optional[int] = None,
        return_telemetry: bool = False,
    ) -> bool | MouseMoveTelemetry:
        """Move mouse to specified coordinates with adaptive correction."""

        telemetry = self.move_mouse_precise(
            x,
            y,
            tolerance=tolerance,
            max_attempts=max_attempts,
            base_duration=duration,
        )

        if return_telemetry:
            return telemetry

        return telemetry.success
    
    def move_to(
        self,
        x: int,
        y: int,
        duration: float = 0.5,
        *,
        tolerance: Optional[int] = None,
        max_attempts: Optional[int] = None,
        return_telemetry: bool = False,
    ) -> bool | MouseMoveTelemetry:
        """Alias for move_mouse with telemetry support."""

        return self.move_mouse(
            x,
            y,
            duration,
            tolerance=tolerance,
            max_attempts=max_attempts,
            return_telemetry=return_telemetry,
        )
    
    def get_mouse_position(self) -> Tuple[int, int]:
        """Get current mouse position."""
        return pyautogui.position()
    
    def move_mouse_fine(self, direction: str, amount: int = 1) -> bool:
        """
        Move mouse one pixel at a time in the specified direction.
        This is used for AI-guided fine targeting where the model sees the screen
        and directs the cursor pixel-by-pixel to the exact target.
        
        Args:
            direction: One of 'up', 'down', 'left', 'right'
            amount: Number of pixels to move (default 1)
            
        Returns:
            bool: True if movement succeeded, False otherwise
        """
        direction = direction.lower().strip()
        x_offset, y_offset = 0, 0
        
        if direction == 'up':
            y_offset = -amount
        elif direction == 'down':
            y_offset = amount
        elif direction == 'left':
            x_offset = -amount
        elif direction == 'right':
            x_offset = amount
        else:
            logger.warning(f"Invalid direction for fine mouse movement: '{direction}'. Use: up, down, left, right")
            return False
        
        try:
            # Get current position
            current_x, current_y = self.get_mouse_position()
            new_x = current_x + x_offset
            new_y = current_y + y_offset
            
            # Clamp to screen bounds
            screen_w, screen_h = self.screen_size
            new_x = max(0, min(new_x, screen_w - 1))
            new_y = max(0, min(new_y, screen_h - 1))
            
            # Move instantly (no duration for fine movements)
            pyautogui.moveTo(new_x, new_y, duration=0)
            
            logger.debug(f"Fine moved mouse {direction} by {amount}px: ({current_x},{current_y}) → ({new_x},{new_y})")
            return True
            
        except Exception as e:
            logger.error(f"Fine mouse movement failed: {e}")
            return False
    
    def type_text(self, text: str, interval: float = 0.05) -> bool:
        """Type text at current cursor position."""
        try:
            pyautogui.write(text, interval=interval)
            logger.debug(f"Typed text: {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Type text failed: {e}")
            return False
    
    def press_key(self, key: str, presses: int = 1) -> bool:
        """Press a keyboard key."""
        try:
            pyautogui.press(key, presses=presses)
            logger.debug(f"Pressed key: {key}")
            return True
        except Exception as e:
            logger.error(f"Key press failed: {e}")
            return False
    
    def hotkey(self, *keys) -> bool:
        """Press a combination of keys."""
        try:
            pyautogui.hotkey(*keys)
            logger.debug(f"Pressed hotkey: {'+'.join(keys)}")
            return True
        except Exception as e:
            logger.error(f"Hotkey failed: {e}")
            return False
    
    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Scroll up (positive) or down (negative)."""
        try:
            if x and y:
                pyautogui.moveTo(x, y)
            pyautogui.scroll(clicks)
            logger.debug(f"Scrolled {clicks} clicks")
            return True
        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            return False
    
    def open_application(self, app_path: str) -> bool:
        """Open an application by path or name with deterministic fallbacks."""

        query = app_path.strip()
        if not query:
            logger.warning("open_application called with empty path")
            return False

        try:
            self.hotkey("win", "r")
            time.sleep(0.5)
            self.type_text(query)
            time.sleep(0.3)
            self.press_key("enter")
            time.sleep(2.0)
            logger.info(f"Requested application launch via Win+R: {query}")
        except Exception as exc:
            logger.error(f"Primary application launch attempt failed: {exc}")

        # If the application already launched (or was running), focus it
        if self.is_application_running(query):
            logger.info(f"Application '{query}' appears to be running; focusing existing window")
            if self.focus_window(query):
                return True

        # Deterministic fallback: try to focus known window candidates even if process check failed
        if self._focus_from_candidates(query, allow_ai=False):
            logger.info(f"Focused existing window matching '{query}' after launch attempt")
            return True

        # Allow AI assistance as last resort to avoid repeated guessing
        if self._focus_from_candidates(query, allow_ai=True):
            logger.info(f"AI-assisted fallback found window for '{query}' after launch attempt")
            return True

        logger.warning(f"Unable to confirm launch of application '{query}'")
        return False
    
    def get_active_window_title(self) -> Optional[str]:
        """Get the title of the currently active window."""

        return self.window_manager.get_active_window_title()

    def _normalize_title(self, title: Optional[str]) -> str:
        """Proxy to the window manager title normaliser."""

        return self.window_manager._normalize_title(title)

    def _titles_match(self, candidate: str, target: str) -> bool:
        """Proxy to the window manager title matcher."""

        return self.window_manager._titles_match(candidate, target)

    def _verify_focus(self, target_title: str, *, allow_partial: bool = True) -> bool:
        """Proxy to the window manager focus verification."""

        return self.window_manager._verify_focus(target_title, allow_partial=allow_partial)

    def _focus_window_handle(self, hwnd: int, *, expected_title: Optional[str] = None) -> bool:
        """Proxy to the window manager handle focus helper."""

        return self.window_manager._focus_window_handle(hwnd, expected_title=expected_title)

    def _focus_pywinauto_window(self, window: Any, *, expected_title: str) -> bool:
        """Proxy to the window manager pywinauto focus helper."""

        return self.window_manager._focus_pywinauto_window(window, expected_title=expected_title)

    def focus_window(self, title_pattern: str) -> bool:
        """Focus a window using deterministic and AI-assisted strategies."""

        return self.window_manager.focus_window(title_pattern)

    def _focus_direct(self, title_pattern: str) -> bool:
        """Proxy to the window manager direct focus helper."""

        return self.window_manager._focus_direct(title_pattern)

    def _focus_from_candidates(self, title_pattern: str, *, allow_ai: bool) -> bool:
        """Proxy to the window manager candidate selection logic."""

        return self.window_manager.focus_from_candidates(title_pattern, allow_ai=allow_ai)

    def _enumerate_focus_candidates(self) -> List[Dict[str, Any]]:
        """Proxy to the window manager candidate enumeration."""

        return self.window_manager._enumerate_focus_candidates()

    def _deterministic_window_choice(
        self,
        target_pattern: str,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Proxy to the window manager deterministic candidate selection."""

        return self.window_manager._deterministic_window_choice(target_pattern, candidates)

    def _select_window_with_ai(
        self,
        target_pattern: str,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Proxy to the window manager AI candidate selector."""

        return self.window_manager._select_window_with_ai(target_pattern, candidates)

    def _ai_identify_window(self, target_pattern: str) -> bool:
        """Backward-compatible entry point for AI window identification."""

        return self.window_manager.ai_identify_window(target_pattern)

    def get_all_open_windows(self) -> List[Dict[str, Any]]:
        """Expose window enumeration from the window manager."""

        return self.window_manager.get_all_open_windows()

    def _is_system_window(self, title: str) -> bool:
        """Proxy to the window manager system window detector."""

        return self.window_manager._is_system_window(title)

    def get_running_processes(self) -> List[str]:
        """Expose process enumeration from the window manager."""

        return self.window_manager.get_running_processes()

    def is_application_running(self, app_name: str) -> bool:
        """Check if an application is running via the window manager."""

        return self.window_manager.is_application_running(app_name)
    
    def wait(self, seconds: float) -> None:
        """Wait for specified seconds."""
        logger.debug(f"Waiting {seconds} seconds...")
        time.sleep(seconds)
    
    def get_pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        """Get RGB color of pixel at coordinates."""
        screenshot = self.take_screenshot()
        pixel = screenshot.getpixel((x, y))
        if isinstance(pixel, tuple) and len(pixel) >= 3:
            return (int(pixel[0]), int(pixel[1]), int(pixel[2]))
        return (0, 0, 0)  # Default black if error
    
    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 1.0) -> bool:
        """Drag from start to end coordinates."""
        try:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.dragTo(end_x, end_y, duration=duration)
            logger.debug(f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})")
            return True
        except Exception as e:
            logger.error(f"Drag failed: {e}")
            return False
    
    def find_window_by_title(self, title: str) -> Optional[Any]:
        """Find a window by its title."""
        try:
            app = Application(backend="uia").connect(title_re=f".*{title}.*", timeout=5)
            return app.top_window()
        except:
            return None
    
    def get_clipboard_text(self) -> Optional[str]:
        """Get text from clipboard."""
        try:
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            text = win32clipboard.GetClipboardData(win32con.CF_TEXT)
            win32clipboard.CloseClipboard()
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text) if text else None
        except:
            return None
    
    def set_clipboard_text(self, text: str) -> bool:
        """Set clipboard text."""
        try:
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_TEXT, text.encode('utf-8'))
            win32clipboard.CloseClipboard()
            return True
        except:
            return False
