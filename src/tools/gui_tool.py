import pyautogui
from typing import List

class X11InputController:
    def __init__(self):
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1

    def mouse_move(self, x: int, y: int) -> str:
        try:
            pyautogui.moveTo(x, y)
            return f"Mouse moved to (x={x}, y={y})."
        except Exception as e:
            return f"Error moving mouse: {e}"

    def mouse_click(self, x: int, y: int, button: str = 'left') -> str:
        print(f"--- Executing X11 Input: Click at (x={x}, y={y}) ---")
        try:
            if not isinstance(x, int) or not isinstance(y, int):
                return "Error: x and y coordinates must be integers."

            screen_width, screen_height = pyautogui.size()
            if not (0 <= x < screen_width and 0 <= y < screen_height):
                return f"Error: coordinates (x={x}, y={y}) are outside the screen bounds ({screen_width}x{screen_height})."

            pyautogui.click(x=x, y=y, button=button)
            return f"Click successfully executed at coordinates (x={x}, y={y})."
        except Exception as e:
            return f"An unexpected error occurred during the click: {e}"

    def type_text(self, text: str) -> str:
        print(f"--- Executing X11 Input: Typing text '{text}' ---")
        try:
            if not isinstance(text, str):
                return "Error: the provided input is not a text string."

            pyautogui.write(text, interval=0.05)
            return "Text successfully typed."
        except Exception as e:
            return f"An unexpected error occurred while typing: {e}"

    def press_hotkey(self, keys: List[str]) -> str:
        print(f"--- Executing X11 Input: Pressing hotkey '{'+'.join(keys)}' ---")
        try:
            pyautogui.hotkey(*keys)
            return f"Hotkey '{'+'.join(keys)}' successfully pressed."
        except Exception as e:
            return f"An unexpected error occurred while pressing hotkey: {e}"
