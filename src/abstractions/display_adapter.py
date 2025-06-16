import os

from src.tools.gui_tool import X11InputController
from src.perception.screen_analyzer import analyze_screen

class X11ScreenCapture:
    def capture_and_process(self) -> str | None:
        return analyze_screen()

class WaylandInputController:
    def __init__(self):
        raise NotImplementedError("The Wayland input controller backend is not yet implemented.")

class WaylandScreenCapture:
    def capture_and_process(self) -> str | None:
        raise NotImplementedError("The Wayland screen capture backend is not yet implemented.")

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
            self.input_controller = WaylandInputController()
            self.screen_capture_controller = WaylandScreenCapture()
        else:
            self.input_controller = X11InputController()
            self.screen_capture_controller = X11ScreenCapture()

    @property
    def screen(self):
        return self.screen_capture_controller

    @property
    def input(self):
        return self.input_controller
