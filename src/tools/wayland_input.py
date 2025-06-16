import time
from typing import List
from evdev import UInput, ecodes as e, AbsInfo

from src.abstractions.input_controller import InputController

class WaylandInputController(InputController):

    KEY_MAP = {
        ' ': e.KEY_SPACE, 'a': e.KEY_A, 'b': e.KEY_B, 'c': e.KEY_C, 'd': e.KEY_D, 'e': e.KEY_E,
        'f': e.KEY_F, 'g': e.KEY_G, 'h': e.KEY_H, 'i': e.KEY_I, 'j': e.KEY_J, 'k': e.KEY_K,
        'l': e.KEY_L, 'm': e.KEY_M, 'n': e.KEY_N, 'o': e.KEY_O, 'p': e.KEY_P, 'q': e.KEY_Q,
        'r': e.KEY_R, 's': e.KEY_S, 't': e.KEY_T, 'u': e.KEY_U, 'v': e.KEY_V, 'w': e.KEY_W,
        'x': e.KEY_X, 'y': e.KEY_Y, 'z': e.KEY_Z, '1': e.KEY_1, '2': e.KEY_2, '3': e.KEY_3,
        '4': e.KEY_4, '5': e.KEY_5, '6': e.KEY_6, '7': e.KEY_7, '8': e.KEY_8, '9': e.KEY_9,
        '0': e.KEY_0, '.': e.KEY_DOT, '/': e.KEY_SLASH, '-': e.KEY_MINUS, '=': e.KEY_EQUAL,
        'enter': e.KEY_ENTER, 'esc': e.KEY_ESC, 'tab': e.KEY_TAB,
        'ctrl': e.KEY_LEFTCTRL, 'alt': e.KEY_LEFTALT, 'shift': e.KEY_LEFTSHIFT,
        'up': e.KEY_UP, 'down': e.KEY_DOWN, 'left': e.KEY_LEFT, 'right': e.KEY_RIGHT,
    }

    def __init__(self, width=1920, height=1080):
        capabilities = {
            e.EV_KEY: self.KEY_MAP.values(),
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(value=0, min=0, max=width, fuzz=0, flat=0, resolution=0)),
                (e.ABS_Y, AbsInfo(value=0, min=0, max=height, fuzz=0, flat=0, resolution=0)),
            ],
        }
        try:
            self.ui = UInput(capabilities, name="djenis-ai-agent-virtual-input", version=0x1)
        except PermissionError:
            raise PermissionError("Could not create virtual input device. You must run as root or be a member of the 'input' group.")

    def __del__(self):
        if hasattr(self, 'ui'):
            self.ui.close()

    def _press_key(self, key_code):
        self.ui.write(e.EV_KEY, key_code, 1)
        self.ui.syn()

    def _release_key(self, key_code):
        self.ui.write(e.EV_KEY, key_code, 0)
        self.ui.syn()

    def mouse_move(self, x: int, y: int) -> str:
        self.ui.write(e.EV_ABS, e.ABS_X, x)
        self.ui.write(e.EV_ABS, e.ABS_Y, y)
        self.ui.syn()
        return f"Mouse moved to (x={x}, y={y})."

    def mouse_click(self, x: int, y: int, button: str = 'left') -> str:
        print(f"--- Executing Wayland Input: Click at (x={x}, y={y}) ---")
        self.mouse_move(x, y)
        btn_code = e.BTN_LEFT if button.lower() == 'left' else e.BTN_RIGHT
        self._press_key(btn_code)
        time.sleep(0.05)
        self._release_key(btn_code)
        return f"Click successfully executed at coordinates (x={x}, y={y})."

    def type_text(self, text: str) -> str:
        print(f"--- Executing Wayland Input: Typing text '{text}' ---")
        for char in text:
            key_code = self.KEY_MAP.get(char.lower())
            if key_code:
                self._press_key(key_code)
                time.sleep(0.01)
                self._release_key(key_code)
                time.sleep(0.02)
        return "Text successfully typed."

    def press_hotkey(self, keys: List[str]) -> str:
        print(f"--- Executing Wayland Input: Pressing hotkey '{'+'.join(keys)}' ---")
        key_codes = [self.KEY_MAP.get(key.lower()) for key in keys]

        for code in key_codes:
            if code:
                self._press_key(code)
                time.sleep(0.05)

        for code in reversed(key_codes):
            if code:
                self._release_key(code)
                time.sleep(0.05)

        return f"Hotkey '{'+'.join(keys)}' successfully pressed."
