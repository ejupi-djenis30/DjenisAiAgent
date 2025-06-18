import subprocess
import shutil
import io
import os
from PIL import Image
from typing import Optional

from src.abstractions.screen_capture import ScreenCapture

class WaylandScreenCapture(ScreenCapture):
    def __init__(self):
        self.use_grim = self._check_grim()
        if not self.use_grim:
            # As per the documentation, grim is the primary implemented method.
            # A D-Bus implementation would be an alternative, not a replacement.
            raise EnvironmentError("The 'grim' command is not found. Please install it to use screen capture on Wayland.")
        print("--- Wayland Capture Initialized using 'grim' backend ---")

    def _check_grim(self) -> bool:
        return shutil.which("grim") is not None

    def capture(self, region: Optional[tuple[int, int, int, int]] = None) -> Image.Image:
        print("--- Capturing screen via grim ---")
        try:
            command = ["grim"]
            if region:
                x, y, width, height = region
                geometry = f"{x},{y} {width}x{height}"
                command.extend(["-g", geometry, "-"])
            else:
                command.append("-")

            # The portal needs a valid DISPLAY and XDG_RUNTIME_DIR
            env = os.environ.copy()
            if 'DISPLAY' not in env:
                env['DISPLAY'] = ':0'
            if 'XDG_RUNTIME_DIR' not in env:
                 # Attempt to find a sensible default if not set
                user_id = os.getuid()
                runtime_dir = f"/run/user/{user_id}"
                if os.path.isdir(runtime_dir):
                    env['XDG_RUNTIME_DIR'] = runtime_dir

            result = subprocess.run(
                command,
                capture_output=True,
                check=True,
                env=env,
                timeout=10
            )

            image_bytes = result.stdout
            if not image_bytes:
                raise RuntimeError("grim command executed but produced no output.")

            img = Image.open(io.BytesIO(image_bytes))
            return img

        except FileNotFoundError:
            raise EnvironmentError("The 'grim' command is not installed or not in the system's PATH.")
        except subprocess.TimeoutExpired:
            raise RuntimeError("The 'grim' command timed out after 10 seconds.")
        except subprocess.CalledProcessError as e:
            error_message = f"The 'grim' command failed with exit code {e.returncode}.\n"
            error_message += f"Stderr: {e.stderr.decode('utf-8', 'ignore')}"
            raise RuntimeError(error_message)
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred during Wayland screen capture: {e}")
