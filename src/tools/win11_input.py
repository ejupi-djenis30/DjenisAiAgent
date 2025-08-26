import time
from typing import Tuple, Union, List, Optional

try:
    import pyautogui
    import keyboard
    import win32api
    import win32con
except ImportError:
    print("Warning: Required libraries for input control not installed. Please install: pyautogui, keyboard, pywin32")

class Win11InputTool:
    """
    Tool for simulating user input on Windows 11 systems.
    Provides methods to simulate keyboard and mouse actions.
    """
    def __init__(self, safety_delay: float = 0.1):
        """
        Initialize the Windows 11 input tool.
        
        Args:
            safety_delay: Delay in seconds between actions to prevent system overload
        """
        self.safety_delay = safety_delay
        # Configure PyAutoGUI safety settings
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = safety_delay
    
    def simulate_key_press(self, key: str, duration: float = 0.1):
        """
        Simulates pressing a key or key combination.
        
        Args:
            key: The key to press (e.g., 'a', 'ctrl', 'alt+f4')
            duration: How long to hold the key down
        """
        try:
            # Handle key combinations (e.g., 'alt+tab')
            if '+' in key:
                pyautogui.hotkey(*key.split('+'))
            else:
                pyautogui.keyDown(key)
                time.sleep(duration)
                pyautogui.keyUp(key)
            
            time.sleep(self.safety_delay)
            return True
        except Exception as e:
            print(f"Error simulating key press: {str(e)}")
            return False
    
    def simulate_mouse_click(self, 
                            x: int, 
                            y: int, 
                            button: str = 'left', 
                            clicks: int = 1, 
                            interval: float = 0.25):
        """
        Simulates mouse click at the specified coordinates.
        
        Args:
            x: X coordinate to click
            y: Y coordinate to click
            button: Mouse button to use ('left', 'right', or 'middle')
            clicks: Number of clicks to perform
            interval: Time between clicks
        """
        try:
            # First move to the position
            self.simulate_mouse_move(x, y)
            
            # Then perform the click
            pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval)
            
            time.sleep(self.safety_delay)
            return True
        except Exception as e:
            print(f"Error simulating mouse click: {str(e)}")
            return False
    
    def simulate_mouse_move(self, x: int, y: int, duration: float = 0.5):
        """
        Simulates mouse movement to the specified coordinates.
        
        Args:
            x: X coordinate to move to
            y: Y coordinate to move to
            duration: Time in seconds the movement should take
        """
        try:
            # Use pyautogui for smooth mouse movement
            pyautogui.moveTo(x, y, duration=duration)
            
            time.sleep(self.safety_delay)
            return True
        except Exception as e:
            print(f"Error simulating mouse movement: {str(e)}")
            return False
    
    def type_text(self, text: str, interval: float = 0.05):
        """
        Simulates typing text at the current cursor position.
        
        Args:
            text: Text to type
            interval: Time between keypresses
        """
        try:
            pyautogui.typewrite(text, interval=interval)
            
            time.sleep(self.safety_delay)
            return True
        except Exception as e:
            print(f"Error typing text: {str(e)}")
            return False
    
    def scroll(self, amount: int, x: Optional[int] = None, y: Optional[int] = None):
        """
        Simulates scrolling at the current or specified position.
        Positive values scroll up, negative values scroll down.
        
        Args:
            amount: Amount to scroll (positive = up, negative = down)
            x: Optional X coordinate for scroll position
            y: Optional Y coordinate for scroll position
        """
        try:
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)
            
            pyautogui.scroll(amount)
            
            time.sleep(self.safety_delay)
            return True
        except Exception as e:
            print(f"Error scrolling: {str(e)}")
            return False
    
    def drag_and_drop(self, 
                     start_x: int, 
                     start_y: int, 
                     end_x: int, 
                     end_y: int, 
                     button: str = 'left', 
                     duration: float = 0.5):
        """
        Simulates drag and drop operation from start coordinates to end coordinates.
        
        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate
            button: Mouse button to use for dragging
            duration: How long the drag operation should take
        """
        try:
            # First move to start position
            self.simulate_mouse_move(start_x, start_y)
            
            # Perform drag operation
            pyautogui.dragTo(end_x, end_y, duration=duration, button=button)
            
            time.sleep(self.safety_delay)
            return True
        except Exception as e:
            print(f"Error performing drag and drop: {str(e)}")
            return False
            
    def press_and_hold(self, key: str, duration: float = 1.0):
        """
        Presses and holds a key for a specified duration.
        
        Args:
            key: The key to hold down
            duration: How long to hold the key in seconds
        """
        try:
            pyautogui.keyDown(key)
            time.sleep(duration)
            pyautogui.keyUp(key)
            
            time.sleep(self.safety_delay)
            return True
        except Exception as e:
            print(f"Error pressing and holding key: {str(e)}")
            # Make sure to release the key even if there's an error
            try:
                pyautogui.keyUp(key)
            except:
                pass
            return False