from abc import ABC, abstractmethod
from PIL.Image import Image
import io

class ScreenCapture(ABC):

    @abstractmethod
    def capture(self, region: tuple[int, int, int, int] | None = None) -> Image:
        pass

    def preprocess(self, img: Image) -> bytes:
        processed_img = img.convert("L")
        processed_img.thumbnail((1280, 720), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        processed_img.save(buffer, format="JPEG", quality=85, optimize=True)

        return buffer.getvalue()
