import pyautogui
import base64
import io

def analyze_screen() -> str | None:
    """
    Takes a screenshot of the entire screen and returns it as a Base64 encoded string.
    """
    print("--- Analyzing the screen... ---")
    try:
        screenshot = pyautogui.screenshot()

        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        base64_string = base64.b64encode(image_bytes).decode('utf-8')

        return base64_string

    except Exception as e:
        print(f"Error during screen analysis: {e}")
        return None
