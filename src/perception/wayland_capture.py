import subprocess
import tempfile
import os
from typing import Optional
from PIL import Image

from src.abstractions.screen_capture import ScreenCapture

class WaylandScreenCapture(ScreenCapture):
    def __init__(self):
        print("--- Wayland Capture Initialized using 'gnome-screenshot' backend ---")

    def capture(self, region: Optional[tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
        print("--- Capturing screen via gnome-screenshot ---")
        if region:
            print("Warning: Region capture is not implemented for this backend. Capturing full screen.")

        try:
            # Create a temporary file to save the screenshot
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
                temp_file_path = tmpfile.name

            # Command to take a screenshot and save it to the temp file
            command = ["gnome-screenshot", "-f", temp_file_path]

            # Execute the command
            subprocess.run(command, check=True, timeout=10)

            if not os.path.exists(temp_file_path):
                print("Error: gnome-screenshot ran but the output file was not created.")
                return None

            # Open the image from the temp file
            with Image.open(temp_file_path) as img:
                # We need a copy in memory because the original file will be deleted.
                img_copy = img.copy()

            return img_copy

        except FileNotFoundError:
            print("Error: 'gnome-screenshot' command not found. Please ensure it is installed.")
            return None
        except subprocess.TimeoutExpired:
            print("Error: 'gnome-screenshot' command timed out.")
            return None
        except subprocess.CalledProcessError as e:
            print(f"Error: 'gnome-screenshot' failed with exit code {e.returncode}.")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during capture: {e}")
            return None
        finally:
            # Clean up the temporary file
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
