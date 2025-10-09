"""UI Automation engine for Windows."""

import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

import cv2
import numpy as np
import psutil
import pyautogui
import pywinauto
import pytesseract
from PIL import Image, ImageGrab
from pywinauto import Application
from pywinauto.findwindows import ElementNotFoundError

from src.config.config import config
from src.utils.logger import setup_logger

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - fallback for older Pillow
    RESAMPLE_LANCZOS = getattr(Image, "LANCZOS", 1)  # type: ignore[attr-defined]

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
        
    @staticmethod
    def _resize_image(
        image: Image.Image,
        *,
        scale: float,
        max_width: int,
        max_height: int,
    ) -> Image.Image:
        """Resize image according to scale and max dimensions while preserving aspect ratio."""

        width, height = image.size
        if width <= 0 or height <= 0:
            return image

        ratio = 1.0
        if scale < 1.0:
            ratio = min(ratio, max(scale, 0.01))

        if max_width > 0 and width > max_width:
            ratio = min(ratio, max_width / width)

        if max_height > 0 and height > max_height:
            ratio = min(ratio, max_height / height)

        if ratio >= 1.0:
            return image

        new_size = (
            max(1, int(round(width * ratio))),
            max(1, int(round(height * ratio))),
        )

        if new_size == image.size:
            return image

        return image.resize(new_size, RESAMPLE_LANCZOS)

    def _prepare_image_for_storage(
        self,
        image: Image.Image,
        *,
        format_override: Optional[str] = None,
        scale_override: Optional[float] = None,
        max_width_override: Optional[int] = None,
        max_height_override: Optional[int] = None,
    ) -> Tuple[Image.Image, str, Dict[str, Any]]:
        """Return optimized copy of image, target format, and save kwargs."""

        format_name = (format_override or config.screenshot_format or "").strip().lower()
        if format_name == "jpg":
            format_name = "jpeg"
        if format_name not in {"png", "jpeg", "webp"}:
            format_name = config.screenshot_format

        scale = config.screenshot_scale if scale_override is None else max(0.01, scale_override)
        max_width = config.screenshot_max_width if max_width_override is None else max(0, max_width_override)
        max_height = config.screenshot_max_height if max_height_override is None else max(0, max_height_override)

        optimized = image.copy()
        optimized = self._resize_image(optimized, scale=scale, max_width=max_width, max_height=max_height)

        save_kwargs: Dict[str, Any] = {}

        if format_name in {"jpeg", "webp"}:
            if optimized.mode not in ("RGB", "L"):
                optimized = optimized.convert("RGB")

            quality = config.screenshot_quality
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True

            if format_name == "webp":
                save_kwargs.setdefault("method", 6)
        else:  # PNG
            # Map 1-100 quality into PNG compress level (0-9, lower is faster)
            quality = config.screenshot_quality
            compress_level = max(0, min(9, int(round((100 - quality) / 10))))
            save_kwargs["compress_level"] = compress_level
            save_kwargs["optimize"] = True

        return optimized, format_name, save_kwargs

    def take_screenshot(self, region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """Take a screenshot of the screen or a specific region."""
        try:
            if region:
                screenshot = ImageGrab.grab(bbox=region)
            else:
                screenshot = ImageGrab.grab()
            return screenshot
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            raise
    
    def save_screenshot(self, filename: Optional[str] = None) -> str:
        """Take and save a screenshot."""
        screenshot = self.take_screenshot()
        ext_hint: Optional[str] = None
        if filename:
            ext_hint = Path(filename).suffix.lower().lstrip(".") or None

        optimized, format_name, save_kwargs = self._prepare_image_for_storage(
            screenshot,
            format_override=ext_hint,
        )

        if filename is None:
            filename = f"screenshot_{int(time.time())}.{format_name}"
        else:
            path_candidate = Path(filename)
            if not path_candidate.suffix:
                filename = f"{filename}.{format_name}"

        filepath = (config.screenshots_dir / filename).resolve()
        filepath.parent.mkdir(parents=True, exist_ok=True)

        optimized.save(filepath, format=format_name.upper(), **save_kwargs)
        logger.debug(
            f"Screenshot saved: {filepath} ({format_name.upper()} {optimized.width}x{optimized.height})"
        )
        return str(filepath)

    def _normalize_bbox(self, left: int, top: int, right: int, bottom: int) -> Tuple[int, int, int, int]:
        """Clamp a bounding box within the visible screen area."""

        screen_width, screen_height = self.screen_size
        left = max(0, min(left, screen_width - 1))
        top = max(0, min(top, screen_height - 1))
        right = max(left + 1, min(right, screen_width))
        bottom = max(top + 1, min(bottom, screen_height))
        return int(left), int(top), int(right), int(bottom)

    def _focus_bbox(self, center: Tuple[int, int], size: Optional[int] = None) -> Tuple[int, int, int, int]:
        """Compute the bounding box for a focus region around a coordinate."""

        size = size or config.screen_focus_size
        half = max(size // 2, 8)
        left = center[0] - half
        top = center[1] - half
        right = center[0] + half
        bottom = center[1] + half
        return self._normalize_bbox(left, top, right, bottom)

    def capture_focus_region(
        self,
        center: Tuple[int, int],
        size: Optional[int] = None,
    ) -> Image.Image:
        """Capture a zoomed-in region around a coordinate for diagnostics."""

        bbox = self._focus_bbox(center, size)
        try:
            focus_image = ImageGrab.grab(bbox=bbox)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.error(f"Failed to capture focus region {bbox}: {exc}")
            raise

        target_size = size or config.screen_focus_size
        if focus_image.width != target_size or focus_image.height != target_size:
            focus_image = focus_image.resize((target_size, target_size), RESAMPLE_LANCZOS)

        return focus_image

    def crop_focus_region(
        self,
        image: Image.Image,
        center: Tuple[int, int],
        size: Optional[int] = None,
    ) -> Image.Image:
        """Crop a focus region from an existing screenshot."""

        bbox = self._focus_bbox(center, size)
        cropped = image.crop(bbox)
        target_size = size or config.screen_focus_size
        if cropped.width != target_size or cropped.height != target_size:
            cropped = cropped.resize((target_size, target_size), RESAMPLE_LANCZOS)
        return cropped

    def save_focus_region(
        self,
        center: Tuple[int, int],
        size: Optional[int] = None,
        *,
        prefix: str = "focus",
        image: Optional[Image.Image] = None,
    ) -> Optional[str]:
        """Persist a focus-region capture to disk and return its path."""

        try:
            focus_image = image or self.capture_focus_region(center, size)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.debug(f"Focus capture skipped due to error: {exc}")
            return None

        focus_dir = config.screenshots_dir / "focus"
        focus_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)

        optimized, format_name, save_kwargs = self._prepare_image_for_storage(
            focus_image,
            format_override=None,
            scale_override=1.0,
            max_width_override=0,
            max_height_override=0,
        )
        filename = f"{prefix}_{timestamp}.{format_name}"
        filepath = (focus_dir / filename).resolve()

        try:
            optimized.save(filepath, format=format_name.upper(), **save_kwargs)
            logger.debug(f"Focus region saved: {filepath} ({format_name.upper()} {optimized.width}x{optimized.height})")
            return str(filepath)
        except Exception as exc:
            logger.debug(f"Failed to save focus region: {exc}")
            return None
    
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
    
    def find_text_on_screen(self, text: str) -> Optional[Tuple[int, int]]:
        """Find text on screen using OCR."""
        try:
            screenshot = self.take_screenshot()
            # Convert to OpenCV format
            screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # Perform OCR
            data = pytesseract.image_to_data(screenshot_cv, output_type=pytesseract.Output.DICT)
            
            # Search for text
            for i, word in enumerate(data['text']):
                if text.lower() in word.lower():
                    x = data['left'][i] + data['width'][i] // 2
                    y = data['top'][i] + data['height'][i] // 2
                    logger.debug(f"Found text '{text}' at: ({x}, {y})")
                    return (x, y)
            
            return None
        except Exception as e:
            logger.error(f"OCR error: {e}")
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
        """Open an application by path or name."""
        try:
            # Try using Windows Run dialog
            self.hotkey('win', 'r')
            time.sleep(0.5)
            self.type_text(app_path)
            time.sleep(0.3)
            self.press_key('enter')
            time.sleep(2)
            logger.info(f"Opened application: {app_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to open application: {e}")
            return False
    
    def get_active_window_title(self) -> Optional[str]:
        """Get the title of the currently active window."""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            return title
        except:
            # Fallback method
            try:
                app = Application(backend="uia").connect(active_only=True)
                title = app.top_window().window_text()
                return title
            except:
                return None
    
    def focus_window(self, title_pattern: str) -> bool:
        """Focus a window by title pattern.
        
        If title is a known application name (like 'calculator', 'notepad'), 
        it will also try to find windows by process name.
        """
        try:
            # Map common app names to process names
            process_map = {
                'calculator': 'calculatorapp.exe',
                'calc': 'calculatorapp.exe',
                'notepad': 'notepad.exe',
                'paint': 'mspaint.exe',
                'edge': 'msedge.exe',
                'chrome': 'chrome.exe',
                'firefox': 'firefox.exe'
            }
            
            # Try exact match first
            try:
                app = Application(backend="uia").connect(title=title_pattern, timeout=2)
                app.top_window().set_focus()
                logger.info(f"Focused window (exact match): {title_pattern}")
                return True
            except:
                pass
            
            # Try regex match with most recently created
            try:
                app = Application(backend="uia").connect(title_re=f".*{title_pattern}.*", timeout=3)
                windows = app.windows()
                
                if len(windows) == 1:
                    windows[0].set_focus()
                    logger.info(f"Focused window (regex match): {title_pattern}")
                    return True
                elif len(windows) > 1:
                    # Focus the first visible window
                    for win in windows:
                        if win.is_visible():
                            win.set_focus()
                            logger.info(f"Focused visible window from {len(windows)} matches: {title_pattern}")
                            return True
                    # If no visible, just focus first
                    windows[0].set_focus()
                    logger.info(f"Focused first of {len(windows)} windows: {title_pattern}")
                    return True
            except:
                pass
            
            # Try process name if title matches a known app
            lower_title = title_pattern.lower()
            if any(app_name in lower_title for app_name in process_map.keys()):
                for app_name, process_name in process_map.items():
                    if app_name in lower_title:
                        try:
                            app = Application(backend="uia").connect(process=process_name, timeout=2)
                            windows = app.windows()
                            if windows:
                                # Focus first visible window
                                for win in windows:
                                    if win.is_visible():
                                        win.set_focus()
                                        logger.info(f"Focused window by process: {process_name}")
                                        return True
                                # If no visible, focus first
                                windows[0].set_focus()
                                logger.info(f"Focused first window by process: {process_name}")
                                return True
                        except Exception as e:
                            logger.debug(f"Process focus attempt failed for {process_name}: {e}")
                            continue
            
            # Try using Win32 API as fallback
            try:
                import win32gui
                import win32con
                
                def callback(hwnd, windows):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if title_pattern.lower() in title.lower():
                            windows.append((hwnd, title))
                    return True
                
                windows = []
                win32gui.EnumWindows(callback, windows)
                
                if windows:
                    hwnd = windows[0][0]
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    logger.info(f"Focused window via Win32: {windows[0][1]}")
                    return True
            except Exception as e:
                logger.debug(f"Win32 focus attempt failed: {e}")
            
            # FINAL FALLBACK: Use AI to identify correct window from all open windows
            logger.info(f"Attempting AI-powered window identification for: {title_pattern}")
            ai_result = self._ai_identify_window(title_pattern)
            if ai_result:
                return ai_result
            
            logger.warning(f"Window not found: {title_pattern}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to focus window: {e}")
            return False
    
    def _ai_identify_window(self, target_pattern: str) -> bool:
        """Use AI to identify the correct window from all open windows.
        
        Args:
            target_pattern: The window title pattern we're looking for
            
        Returns:
            True if a window was identified and focused, False otherwise
        """
        try:
            # Get all open windows
            all_windows = self.get_all_open_windows()
            
            if not all_windows:
                logger.debug("No open windows found for AI identification")
                return False
            
            # Filter out empty titles and system windows
            candidate_windows = [
                (title, hwnd) for title, hwnd in all_windows 
                if title and len(title) > 0 and not self._is_system_window(title)
            ]
            
            if not candidate_windows:
                logger.debug("No candidate windows after filtering")
                return False
            
            logger.info(f"Found {len(candidate_windows)} candidate windows")
            logger.debug(f"Candidates: {[title for title, _ in candidate_windows[:10]]}")
            
            # Try to identify using Gemini AI
            try:
                from src.core.gemini_client import EnhancedGeminiClient
                import config
                
                gemini = EnhancedGeminiClient()
                
                # Create a prompt for AI to identify the correct window
                window_list = "\n".join([f"{i+1}. {title}" for i, (title, _) in enumerate(candidate_windows[:20])])
                
                prompt = f"""You are helping identify which window title matches the user's request.

TARGET: The user wants to focus a window matching: "{target_pattern}"

AVAILABLE WINDOWS (currently open):
{window_list}

TASK: Identify which window number (1-{min(20, len(candidate_windows))}) best matches the target.
Consider:
- Exact matches (highest priority)
- Partial matches
- Application name matches (e.g., "Calculator" matches "Rechner", "Calculadora", "Calculatrice")
- Language variations (EN/DE/ES/FR/IT/etc.)

RESPONSE FORMAT (JSON):
{{
    "match_found": true/false,
    "window_number": <number 1-{min(20, len(candidate_windows))} or null>,
    "confidence": "high/medium/low",
    "reasoning": "brief explanation"
}}

If no good match exists, set match_found to false.
"""
                
                response = gemini.model.generate_content(prompt)
                result_text = response.text.strip()
                
                # Parse JSON response
                import json
                import re
                
                # Extract JSON from response (might be wrapped in markdown)
                json_match = re.search(r'\{[\s\S]*\}', result_text)
                if json_match:
                    result = json.loads(json_match.group())
                    
                    if result.get('match_found') and result.get('window_number'):
                        window_idx = result['window_number'] - 1
                        
                        if 0 <= window_idx < len(candidate_windows):
                            title, hwnd = candidate_windows[window_idx]
                            confidence = result.get('confidence', 'unknown')
                            reasoning = result.get('reasoning', 'No reason provided')
                            
                            logger.info(f"AI identified window: '{title}' (confidence: {confidence})")
                            logger.info(f"Reasoning: {reasoning}")
                            
                            # Focus the identified window
                            try:
                                import win32gui
                                import win32con
                                
                                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                                win32gui.SetForegroundWindow(hwnd)
                                logger.info(f"✅ Successfully focused AI-identified window: {title}")
                                return True
                                
                            except Exception as e:
                                logger.error(f"Failed to focus AI-identified window: {e}")
                                return False
                        else:
                            logger.warning(f"AI returned invalid window number: {result['window_number']}")
                    else:
                        logger.info(f"AI could not identify matching window: {result.get('reasoning', 'No match found')}")
                        
            except ImportError:
                logger.debug("Gemini client not available for AI window identification")
            except Exception as e:
                logger.debug(f"AI window identification failed: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Error in AI window identification: {e}")
            return False
    
    def get_all_open_windows(self) -> List[tuple]:
        """Get all open windows with their titles and handles.
        
        Returns:
            List of tuples (title, hwnd)
        """
        try:
            import win32gui
            
            windows = []
            
            def callback(hwnd, window_list):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    window_list.append((title, hwnd))
                return True
            
            win32gui.EnumWindows(callback, windows)
            return windows
            
        except ImportError:
            # Fallback to pygetwindow
            try:
                import pygetwindow as gw
                all_titles = gw.getAllTitles()
                return [(title, 0) for title in all_titles if title]
            except:
                logger.warning("Could not enumerate windows (win32gui not available)")
                return []
    
    def _is_system_window(self, title: str) -> bool:
        """Check if a window title is a system window that should be ignored.
        
        Args:
            title: Window title to check
            
        Returns:
            True if it's a system window, False otherwise
        """
        # System window patterns to ignore
        system_patterns = [
            'Program Manager',
            'Microsoft Text Input Application',
            'Windows Input Experience',
            'MSCTFIME UI',
            'Default IME',
            'Task Switching',
            '',  # Empty titles
        ]
        
        title_lower = title.lower()
        
        # Exact matches
        if title in system_patterns:
            return True
        
        # Pattern matches
        system_keywords = ['ime ui', 'input experience', 'progman', 'dde server']
        return any(keyword in title_lower for keyword in system_keywords)
    
    def get_running_processes(self) -> List[str]:
        """Get list of running process names."""
        return [proc.name() for proc in psutil.process_iter(['name'])]
    
    def is_application_running(self, app_name: str) -> bool:
        """Check if an application is running."""
        processes = self.get_running_processes()
        return any(app_name.lower() in proc.lower() for proc in processes)
    
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
