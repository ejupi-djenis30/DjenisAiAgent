"""UI Automation engine for Windows."""

import difflib
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

import psutil
import pyautogui
import pywinauto
from PIL import Image, ImageGrab
from pywinauto import Application
from pywinauto.findwindows import ElementNotFoundError

from src.config.config import config
from src.utils.logger import setup_logger
from src.utils.ocr import get_ocr_engine, OCRResult

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
        self._ocr_engine = get_ocr_engine()
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
    
    @staticmethod
    def _normalize_title(title: Optional[str]) -> str:
        """Return a normalized window title for matching."""

        return (title or "").strip()

    def _titles_match(self, candidate: str, target: str) -> bool:
        """Check whether two window titles refer to the same window."""

        candidate_norm = self._normalize_title(candidate).lower()
        target_norm = self._normalize_title(target).lower()

        if not candidate_norm or not target_norm:
            return False

        return target_norm in candidate_norm or candidate_norm in target_norm

    def _verify_focus(self, target_title: str, *, allow_partial: bool = True) -> bool:
        """Verify whether the active window matches the requested title."""

        active_title = self.get_active_window_title()
        if not active_title:
            return False

        if allow_partial:
            return self._titles_match(active_title, target_title)

        return (
            self._normalize_title(active_title).lower()
            == self._normalize_title(target_title).lower()
        )

    def _focus_window_handle(self, hwnd: int, *, expected_title: Optional[str] = None) -> bool:
        """Focus a window by handle and optionally verify the resulting title."""

        try:
            import win32gui
            import win32con

            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.4)

            if expected_title and not self._verify_focus(expected_title):
                logger.debug(
                    "Post-focus verification failed for handle %s (expected '%s')",
                    hwnd,
                    expected_title,
                )
                return False

            return True
        except Exception as exc:
            logger.debug(f"Failed to focus window handle {hwnd}: {exc}")
            return False

    def _focus_pywinauto_window(self, window: Any, *, expected_title: str) -> bool:
        """Focus a pywinauto window with verification."""

        try:
            window.set_focus()
            time.sleep(0.3)
        except Exception as exc:
            logger.debug(f"Pywinauto focus failed: {exc}")
            return False

        if not self._verify_focus(expected_title):
            logger.debug(
                "Focused window did not match expectation (expected '%s')",
                expected_title,
            )
            return False

        return True

    def focus_window(self, title_pattern: str) -> bool:
        """Focus a window using deterministic fallbacks before AI assistance."""

        target = self._normalize_title(title_pattern)
        if not target:
            logger.warning("focus_window called with empty title pattern")
            return False

        if self._verify_focus(target):
            current = self.get_active_window_title()
            logger.info(
                "Window '%s' already has focus; skipping focus request for '%s'",
                current,
                target,
            )
            return True

        logger.info(f"Attempting to focus window: {target}")

        try:
            if self._focus_direct(target):
                return True

            logger.info("Direct focus failed; enumerating open windows for deterministic selection")
            if self._focus_from_candidates(target, allow_ai=True):
                return True

            logger.warning(f"Window not found: {target}")
            return False
        except Exception as exc:
            logger.error(f"Failed to focus window '{target}': {exc}")
            return False

    def _focus_direct(self, title_pattern: str) -> bool:
        """Attempt direct focus methods (exact match, regex, process, Win32)."""

        process_map = {
            "calculator": "calculatorapp.exe",
            "calc": "calculatorapp.exe",
            "notepad": "notepad.exe",
            "paint": "mspaint.exe",
            "edge": "msedge.exe",
            "chrome": "chrome.exe",
            "firefox": "firefox.exe",
        }

        # Exact title match
        try:
            app = Application(backend="uia").connect(title=title_pattern, timeout=2)
            top_window = app.top_window()
            if self._focus_pywinauto_window(top_window, expected_title=title_pattern):
                logger.info(f"Focused window (exact match): {title_pattern}")
                return True
        except Exception:
            pass

        # Regex/partial title match
        try:
            app = Application(backend="uia").connect(title_re=f".*{title_pattern}.*", timeout=3)
            windows = app.windows()
            visible_windows = [win for win in windows if getattr(win, "is_visible", lambda: True)()]
            candidates = visible_windows or windows

            for win in candidates:
                window_title = self._normalize_title(getattr(win, "window_text", lambda: "")()) or title_pattern
                if self._focus_pywinauto_window(win, expected_title=window_title):
                    logger.info(f"Focused window (regex match): {window_title}")
                    return True
        except Exception:
            pass

        # Process-based lookup for known applications
        lower_title = title_pattern.lower()
        for app_name, process_name in process_map.items():
            if app_name in lower_title:
                try:
                    app = Application(backend="uia").connect(process=process_name, timeout=2)
                    windows = app.windows()
                    for win in windows:
                        if not getattr(win, "is_visible", lambda: True)() and len(windows) > 1:
                            continue

                        window_title = self._normalize_title(getattr(win, "window_text", lambda: "")()) or title_pattern
                        if self._focus_pywinauto_window(win, expected_title=window_title):
                            logger.info(f"Focused window by process ({process_name}): {window_title}")
                            return True
                except Exception as exc:
                    logger.debug(f"Process focus attempt failed for {process_name}: {exc}")

        # Win32 fallback enumeration
        try:
            import win32gui

            matches: List[Tuple[int, str]] = []

            def callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if self._titles_match(title, title_pattern):
                        windows.append((hwnd, title))
                return True

            win32gui.EnumWindows(callback, matches)

            if matches:
                hwnd, title = matches[0]
                if self._focus_window_handle(hwnd, expected_title=title):
                    logger.info(f"Focused window via Win32: {title}")
                    return True
        except Exception as exc:
            logger.debug(f"Win32 focus attempt failed: {exc}")

        return False

    def _enumerate_focus_candidates(self) -> List[Dict[str, Any]]:
        """Return user-visible window candidates for fallback selection."""

        windows = self.get_all_open_windows()
        return [
            window
            for window in windows
            if window.get("title") and not self._is_system_window(window.get("title", ""))
        ]

    def _deterministic_window_choice(
        self,
        target_pattern: str,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Return a deterministic best-match window when possible."""

        if not candidates:
            return None

        target_norm = self._normalize_title(target_pattern).lower()
        if not target_norm:
            return None

        # Prefer process-name matching when the target looks like an executable
        if target_norm.endswith(".exe"):
            process_matches = [
                candidate
                for candidate in candidates
                if (candidate.get("process_name") or "").lower() == target_norm
            ]

            if len(process_matches) == 1:
                logger.debug(
                    "Deterministic process match for '%s': %s",
                    target_pattern,
                    process_matches[0].get("title"),
                )
                return process_matches[0]

            if process_matches:
                logger.debug(
                    "Multiple process matches for '%s'; selecting largest visible window",
                    target_pattern,
                )
                return max(
                    process_matches,
                    key=lambda candidate: (candidate.get("width", 0) * candidate.get("height", 0)),
                )

        # Direct substring matches (target in title)
        substring_matches = [
            candidate
            for candidate in candidates
            if target_norm in self._normalize_title(candidate.get("title")).lower()
        ]

        if len(substring_matches) == 1:
            return substring_matches[0]

        # Inverse substring matches (title fully contained in target)
        inverse_matches = [
            candidate
            for candidate in candidates
            if self._normalize_title(candidate.get("title")).lower() in target_norm
        ]

        if len(inverse_matches) == 1:
            return inverse_matches[0]

        # Process name match
        process_matches = [
            candidate
            for candidate in candidates
            if target_norm in (candidate.get("process_name") or "").lower()
        ]

        if len(process_matches) == 1:
            return process_matches[0]

        # Fuzzy matching using difflib
        titles = [candidate.get("title", "") for candidate in candidates]
        close_matches = difflib.get_close_matches(target_pattern, titles, n=2, cutoff=0.82)

        if len(close_matches) == 1:
            chosen_title = close_matches[0]
            return next(candidate for candidate in candidates if candidate.get("title") == chosen_title)

        if len(substring_matches) > 1:
            best = max(
                substring_matches,
                key=lambda candidate: difflib.SequenceMatcher(
                    None,
                    target_norm,
                    self._normalize_title(candidate.get("title")).lower(),
                ).ratio(),
            )
            return best

        if close_matches:
            chosen_title = close_matches[0]
            return next(candidate for candidate in candidates if candidate.get("title") == chosen_title)

        return None

    def _select_window_with_ai(
        self,
        target_pattern: str,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Ask the language model to choose a window from the candidate list."""

        try:
            from src.core.gemini_client import EnhancedGeminiClient
            from src.core.prompts import prompt_builder
        except Exception as exc:
            logger.debug(f"AI-assisted selection unavailable: {exc}")
            return None

        if not candidates:
            return None

        prompt = prompt_builder.build_window_selection_prompt(target_pattern, candidates)

        try:
            client = EnhancedGeminiClient()
            response_text = client.generate_text(prompt, max_tokens=8)
            selection = int(response_text.strip())
        except Exception as exc:
            logger.debug(f"AI window selection failed: {exc}")
            return None

        if selection <= 0 or selection > len(candidates):
            logger.debug(f"AI returned invalid selection index: {selection}")
            return None

        return candidates[selection - 1]

    def _focus_from_candidates(self, title_pattern: str, *, allow_ai: bool) -> bool:
        """Focus a window using deterministic and optional AI selection."""

        candidates = self._enumerate_focus_candidates()
        if not candidates:
            logger.debug("No window candidates available for fallback focus")
            return False

        logger.debug(
            "Enumerated %d candidate windows for '%s'",
            len(candidates),
            title_pattern,
        )
        for index, candidate in enumerate(candidates[:5], start=1):
            logger.debug(
                "  %d. %s (process=%s, size=%dx%d)",
                index,
                candidate.get("title"),
                candidate.get("process_name"),
                candidate.get("width", 0),
                candidate.get("height", 0),
            )

        deterministic = self._deterministic_window_choice(title_pattern, candidates)
        if deterministic:
            hwnd = deterministic.get("hwnd")
            if hwnd:
                logger.info(
                    "Deterministic fallback selected window '%s' (%s)",
                    deterministic.get("title"),
                    deterministic.get("process_name") or "unknown process",
                )
                if self._focus_window_handle(
                    hwnd,
                    expected_title=deterministic.get("title"),
                ):
                    return True
            else:
                logger.debug(
                    "Deterministic candidate '%s' lacks window handle; skipping",
                    deterministic.get("title"),
                )

        if allow_ai:
            selected = self._select_window_with_ai(title_pattern, candidates)
            if selected:
                hwnd = selected.get("hwnd")
                if hwnd and self._focus_window_handle(
                    hwnd,
                    expected_title=selected.get("title"),
                ):
                    logger.info(
                        "AI-assisted selection focused window '%s' (%s)",
                        selected.get("title"),
                        selected.get("process_name") or "unknown process",
                    )
                    return True
                if not hwnd:
                    logger.debug(
                        "AI-selected window '%s' has no handle; skipping",
                        selected.get("title"),
                    )

        return False

    def _ai_identify_window(self, target_pattern: str) -> bool:
        """Backward-compatible entry point for AI window identification."""

        logger.info("Attempting AI-assisted window identification fallback")
        return self._focus_from_candidates(target_pattern, allow_ai=True)
    
    def get_all_open_windows(self) -> List[Dict[str, Any]]:
        """Get metadata about all visible top-level windows."""

        windows: List[Dict[str, Any]] = []

        try:
            import win32gui
            import win32process

            def callback(hwnd, window_list):
                if not win32gui.IsWindowVisible(hwnd):
                    return True

                title = win32gui.GetWindowText(hwnd)
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                width = max(0, right - left)
                height = max(0, bottom - top)

                process_name = ""
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid:
                        process = psutil.Process(pid)
                        process_name = process.name()
                except Exception:
                    process_name = ""

                window_list.append(
                    {
                        "title": title,
                        "hwnd": hwnd,
                        "x": left,
                        "y": top,
                        "width": width,
                        "height": height,
                        "process_name": process_name,
                    }
                )
                return True

            win32gui.EnumWindows(callback, windows)
            return windows

        except ImportError:
            try:
                import pygetwindow as gw

                for window in gw.getAllWindows():
                    title = window.title
                    if not title:
                        continue
                    windows.append(
                        {
                            "title": title,
                            "hwnd": getattr(window, "_hWnd", 0),
                            "x": window.left,
                            "y": window.top,
                            "width": window.width,
                            "height": window.height,
                            "process_name": "",
                        }
                    )

                return windows
            except Exception:
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
