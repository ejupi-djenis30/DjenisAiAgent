from typing import Optional, Union
from PIL import Image
import pyautogui
import base64
import io

def analyze_screen(return_pil: bool = False) -> Union[str, Image.Image, None]:
    try:
        screenshot = pyautogui.screenshot()
        if not screenshot:
            return None

        if return_pil:
            return screenshot

        processed_img = screenshot.convert("L")
        processed_img.thumbnail((1280, 720), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        processed_img.save(buffer, format="JPEG", quality=85, optimize=True)
        image_bytes = buffer.getvalue()

        base64_string = base64.b64encode(image_bytes).decode('utf-8')
        return base64_string

    except Exception as e:
        print(f"Error during screen analysis: {e}")
        return None
