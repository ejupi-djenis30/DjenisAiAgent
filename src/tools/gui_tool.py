import pyautogui
from .base_tool import BaseTool

class ClickTool(BaseTool):
    @property
    def name(self) -> str:
        return "click_at_coordinates"

    @property
    def description(self) -> str:
        return "Executes a mouse click at a specific screen coordinate (x, y). Arguments: 'x: int', 'y: int'."

    def execute(self, x: int, y: int) -> str:
        print(f"--- Executing GUI Tool: Click at (x={x}, y={y}) ---")
        try:
            # Input validation
            if not isinstance(x, int) or not isinstance(y, int):
                return "Error: x and y coordinates must be integers."

            screen_width, screen_height = pyautogui.size()
            if not (0 <= x < screen_width and 0 <= y < screen_height):
                return f"Error: coordinates (x={x}, y={y}) are outside the screen bounds ({screen_width}x{screen_height})."

            pyautogui.click(x=x, y=y)
            return f"Click successfully executed at coordinates (x={x}, y={y})."

        except Exception as e:
            return f"An unexpected error occurred during the click: {e}"

class TypeTool(BaseTool):
    @property
    def name(self) -> str:
        return "type_text_into_active_window"

    @property
    def description(self) -> str:
        return "Types the provided text into the currently active window, simulating keyboard input. Argument: 'text: str'."

    def execute(self, text: str) -> str:
        print(f"--- Executing GUI Tool: Typing text '{text}' ---")
        try:
            if not isinstance(text, str):
                return "Error: the provided input is not a text string."

            pyautogui.write(text, interval=0.05)
            return "Text successfully typed."

        except Exception as e:
            return f"An unexpected error occurred while typing: {e}"
