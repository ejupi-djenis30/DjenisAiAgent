from abc import ABC, abstractmethod
from typing import List

class InputController(ABC):

    @abstractmethod
    def mouse_move(self, x: int, y: int) -> str:
        pass

    @abstractmethod
    def mouse_click(self, x: int, y: int, button: str = 'left') -> str:
        pass

    @abstractmethod
    def type_text(self, text: str) -> str:
        pass

    @abstractmethod
    def press_hotkey(self, keys: List[str]) -> str:
        pass
