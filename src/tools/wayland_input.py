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
        'x': e.KEY_X, 'y': e.KEY_Y, 'z': e.KEY_Z,
        '1': e.KEY_1, '2': e.KEY_2, '3': e.KEY_3, '4': e.KEY_4, '5': e.KEY_5,
        '6': e.KEY_6, '7': e.KEY_7, '8': e.KEY_8, '9': e.KEY_9, '0': e.KEY_0,
        '`': e.KEY_GRAVE, '-': e.KEY_MINUS, '=': e.KEY_EQUAL,
        '[': e.KEY_LEFTBRACE, ']': e.KEY_RIGHTBRACE, '\\': e.KEY_BACKSLASH,
        ';': e.KEY_SEMICOLON, "'": e.KEY_APOSTROPHE, ',': e.KEY_COMMA,
        '.': e.KEY_DOT, '/': e.KEY_SLASH,
        'enter': e.KEY_ENTER, 'esc': e.KEY_ESC, 'tab': e.KEY_TAB, 'backspace': e.KEY_BACKSPACE,
        'ctrl': e.KEY_LEFTCTRL, 'alt': e.KEY_LEFTALT, 'shift': e.KEY_LEFTSHIFT,
        'up': e.KEY_UP, 'down': e.KEY_DOWN, 'left': e.KEY_LEFT, 'right': e.KEY_RIGHT,
    }

    SHIFT_KEY_MAP = {
        '~': '`', '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6',
        '&': '7', '*': '8', '(': '9', ')': '0', '_': '-', '+': '=', '{': '[',
        '}': ']', '|': '\\', ':': ';', '"': "'", '<': ',', '>': '.', '?': '/',
    }

    def __init__(self, width=1920, height=1080):
        key_codes = list(self.KEY_MAP.values()) + [e.BTN_LEFT, e.BTN_RIGHT]
        capabilities = {
            e.EV_KEY: list(set(key_codes)),
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

    def _release_key(self, key_code):
        self.ui.write(e.EV_KEY, key_code, 0)

    def _tap_key(self, key_code, with_shift=False):
        if with_shift:
            self._press_key(e.KEY_LEFTSHIFT)
            self.ui.syn()
            time.sleep(0.02)

        self._press_key(key_code)
        self.ui.syn()
        time.sleep(0.01)
        self._release_key(key_code)
        self.ui.syn()
        time.sleep(0.01)

        if with_shift:
            self._release_key(e.KEY_LEFTSHIFT)
            self.ui.syn()
            time.sleep(0.02)

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
        self.ui.syn()
        time.sleep(0.05)
        self._release_key(btn_code)
        self.ui.syn()
        return f"Click successfully executed at coordinates (x={x}, y={y})."

    def type_text(self, text: str) -> str:
        print(f"--- Executing Wayland Input: Typing text '{text}' ---")
        for char in text:
            needs_shift = char.isupper() or char in self.SHIFT_KEY_MAP
            char_for_map = self.SHIFT_KEY_MAP.get(char, char.lower())
            key_code = self.KEY_MAP.get(char_for_map)

            if key_code:
                self._tap_key(key_code, with_shift=needs_shift)
            else:
                print(f"Warning: Character '{char}' not found in key map, skipping.")
        return "Text successfully typed."

    def press_hotkey(self, keys: List[str]) -> str:
        print(f"--- Executing Wayland Input: Pressing hotkey '{'+'.join(keys)}' ---")
        key_codes = [self.KEY_MAP.get(key.lower()) for key in keys if key.lower() in self.KEY_MAP]

        if len(key_codes) != len(keys):
            return "Error: One or more keys in the hotkey combination were not found."

        for code in key_codes:
            self._press_key(code)
            time.sleep(0.05)

        self.ui.syn()
        time.sleep(0.05)

        for code in reversed(key_codes):
            self._release_key(code)
            time.sleep(0.05)

        self.ui.syn()

        return f"Hotkey '{'+'.join(keys)}' successfully pressed."
