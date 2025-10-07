"""UI Automation engine for Windows."""

import time
import pyautogui
import pywinauto
from pywinauto import Application
from pywinauto.findwindows import ElementNotFoundError
from PIL import Image, ImageGrab
import cv2
import numpy as np
from typing import Optional, Tuple, List, Dict, Any
import pytesseract
import psutil

from logger import setup_logger
from config import config

logger = setup_logger("UIAutomation")

# Configure PyAutoGUI
pyautogui.FAILSAFE = True  # Move mouse to corner to abort
pyautogui.PAUSE = config.action_delay


class UIAutomationEngine:
    """Engine for performing UI automation on Windows."""
    
    def __init__(self):
        """Initialize the UI automation engine."""
        self.screen_size = pyautogui.size()
        logger.info(f"Initialized UI automation engine. Screen size: {self.screen_size}")
        
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
        if filename is None:
            filepath = config.screenshots_dir / f"screenshot_{int(time.time())}.png"
        else:
            filepath = config.screenshots_dir / filename
        screenshot.save(filepath)
        logger.debug(f"Screenshot saved: {filepath}")
        return str(filepath)
    
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
    
    def move_mouse(self, x: int, y: int, duration: float = 0.5) -> bool:
        """Move mouse to specified coordinates."""
        try:
            pyautogui.moveTo(x, y, duration=duration)
            logger.debug(f"Moved mouse to ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"Mouse move failed: {e}")
            return False
    
    def move_to(self, x: int, y: int, duration: float = 0.5) -> bool:
        """Alias for move_mouse."""
        return self.move_mouse(x, y, duration)
    
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
            
            logger.warning(f"Window not found: {title_pattern}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to focus window: {e}")
            return False
    
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
