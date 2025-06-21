import os
import base64
import io
from PIL import Image

from src.abstractions.screen_capture import ScreenCapture
from src.abstractions.input_controller import InputController

class X11ScreenCaptureAdapter(ScreenCapture):
    def capture(self, region: tuple[int, int, int, int] | None = None) -> Image.Image | None:
        from src.perception import screen_analyzer
        try:
            return screen_analyzer.analyze_screen(return_pil=True)
        except Exception as e:
            print(f"Error in X11 Capture Adapter: {e}")
            return None

    def capture_and_process(self) -> str | None:
        try:
            screenshot_pil = self.capture()
            if screenshot_pil:
                processed_bytes = self.preprocess(screenshot_pil)
                return base64.b64encode(processed_bytes).decode('utf-8')
            return None
        except Exception as e:
            print(f"Error processing X11 capture: {e}")
            return None

class WaylandScreenCaptureAdapter(ScreenCapture):
    def __init__(self):
        from src.perception.wayland_capture import WaylandScreenCapture as WaylandCaptureBackend
        try:
            self.backend = WaylandCaptureBackend()
        except EnvironmentError as e:
            print(f"Wayland Capture Backend Error: {e}")
            raise

    def capture(self, region: tuple[int, int, int, int] | None = None) -> Image.Image | None:
        try:
            return self.backend.capture(region)
        except Exception as e:
            print(f"Error in Wayland Capture Adapter: {e}")
            return None

    def capture_and_process(self) -> str | None:
        try:
            screenshot_pil = self.capture()
            if screenshot_pil:
                processed_bytes = self.preprocess(screenshot_pil)
                return base64.b64encode(processed_bytes).decode('utf-8')
            return None
        except Exception as e:
            print(f"Error processing Wayland capture: {e}")
            return None

class DisplayAdapter:
    def __init__(self):
        self.session_type = self._get_session_type()
        self._initialize_controllers()
        print(f"--- Display Adapter Initialized for {self.session_type.upper()} session ---")

    def _get_session_type(self) -> str:
        session_type = os.environ.get("XDG_SESSION_TYPE", "x11").lower()
        if "wayland" in session_type:
            return "wayland"
        return "x11"

    def _initialize_controllers(self):
        if self.session_type == "wayland":
            from src.tools.wayland_input import WaylandInputController as WaylandInputBackend
            self.input: InputController = WaylandInputBackend()
            self.screen: ScreenCapture = WaylandScreenCaptureAdapter()
        else:
            from src.tools.gui_tool import X11InputController
            self.input: InputController = X11InputController()
            self.screen: ScreenCapture = X11ScreenCaptureAdapter()
