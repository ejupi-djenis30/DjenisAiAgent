import subprocess
import shutil
import io
from PIL import Image

from src.abstractions.screen_capture import ScreenCapture

class WaylandScreenCapture(ScreenCapture):
    def __init__(self):
        if not shutil.which("grim"):
            raise EnvironmentError("The 'grim' command is not found. Please install it to use screen capture on Wayland.")

    def capture(self, region: tuple[int, int, int, int] | None = None) -> Image:
        try:
            command = ["grim"]
            if region:
                x, y, width, height = region
                geometry = f"{x},{y} {width}x{height}"
                command.extend(["-g", geometry, "-"])
            else:
                command.append("-")

            result = subprocess.run(command, capture_output=True, check=True)

            image_bytes = result.stdout
            img = Image.open(io.BytesIO(image_bytes))

            return img

        except FileNotFoundError:
            raise EnvironmentError("The 'grim' command is not installed or not in the system's PATH.")
        except subprocess.CalledProcessError as e:
            error_message = f"The 'grim' command failed with exit code {e.returncode}.\n"
            error_message += f"Stderr: {e.stderr.decode('utf-8')}"
            raise RuntimeError(error_message)
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred during Wayland screen capture: {e}")
