"""Utility helpers for screen capture and processing."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageGrab

from src.config.config import config
from src.utils.logger import setup_logger

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - fallback for older Pillow
    RESAMPLE_LANCZOS = getattr(Image, "LANCZOS", 1)  # type: ignore[attr-defined]


class ScreenUtils:
    """Screen capture helpers shared across automation components."""

    def __init__(self, *, screen_size: Tuple[int, int], logger=None) -> None:
        self._screen_size = screen_size
        self._logger = logger or setup_logger("ScreenUtils")

    def set_screen_size(self, screen_size: Tuple[int, int]) -> None:
        """Update cached screen size information."""

        self._screen_size = screen_size

    @staticmethod
    def _resize_image(
        image: Image.Image,
        *,
        scale: float,
        max_width: int,
        max_height: int,
    ) -> Image.Image:
        """Resize image according to scale and max dimensions while preserving aspect ratio."""

        width, height = image.size
        if width <= 0 or height <= 0:
            return image

        ratio = 1.0
        if scale < 1.0:
            ratio = min(ratio, max(scale, 0.01))

        if max_width > 0 and width > max_width:
            ratio = min(ratio, max_width / width)

        if max_height > 0 and height > max_height:
            ratio = min(ratio, max_height / height)

        if ratio >= 1.0:
            return image

        new_size = (
            max(1, int(round(width * ratio))),
            max(1, int(round(height * ratio))),
        )

        if new_size == image.size:
            return image

        return image.resize(new_size, RESAMPLE_LANCZOS)

    def _prepare_image_for_storage(
        self,
        image: Image.Image,
        *,
        format_override: Optional[str] = None,
        scale_override: Optional[float] = None,
        max_width_override: Optional[int] = None,
        max_height_override: Optional[int] = None,
    ) -> Tuple[Image.Image, str, Dict[str, Any]]:
        """Return optimized copy of image, target format, and save kwargs."""

        format_name = (format_override or config.screenshot_format or "").strip().lower()
        if format_name == "jpg":
            format_name = "jpeg"
        if format_name not in {"png", "jpeg", "webp"}:
            format_name = config.screenshot_format

        scale = config.screenshot_scale if scale_override is None else max(0.01, scale_override)
        max_width = config.screenshot_max_width if max_width_override is None else max(0, max_width_override)
        max_height = config.screenshot_max_height if max_height_override is None else max(0, max_height_override)

        optimized = image.copy()
        optimized = self._resize_image(optimized, scale=scale, max_width=max_width, max_height=max_height)

        save_kwargs: Dict[str, Any] = {}

        if format_name in {"jpeg", "webp"}:
            if optimized.mode not in ("RGB", "L"):
                optimized = optimized.convert("RGB")

            quality = config.screenshot_quality
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True

            if format_name == "webp":
                save_kwargs.setdefault("method", 6)
        else:  # PNG
            quality = config.screenshot_quality
            compress_level = max(0, min(9, int(round((100 - quality) / 10))))
            save_kwargs["compress_level"] = compress_level
            save_kwargs["optimize"] = True

        return optimized, format_name, save_kwargs

    def take_screenshot(self, region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """Take a screenshot of the screen or a specific region."""
        try:
            if region:
                screenshot = ImageGrab.grab(bbox=region)
            else:
                screenshot = ImageGrab.grab()
            return screenshot
        except Exception as exc:  # pragma: no cover - dependency on OS/hardware
            self._logger.error(f"Failed to take screenshot: {exc}")
            raise

    def save_screenshot(self, filename: Optional[str] = None) -> str:
        """Take and save a screenshot, returning the saved path."""

        screenshot = self.take_screenshot()
        ext_hint: Optional[str] = None
        if filename:
            ext_hint = Path(filename).suffix.lower().lstrip(".") or None

        optimized, format_name, save_kwargs = self._prepare_image_for_storage(
            screenshot,
            format_override=ext_hint,
        )

        if filename is None:
            filename = f"screenshot_{int(time.time())}.{format_name}"
        else:
            path_candidate = Path(filename)
            if not path_candidate.suffix:
                filename = f"{filename}.{format_name}"

        filepath = (config.screenshots_dir / filename).resolve()
        filepath.parent.mkdir(parents=True, exist_ok=True)

        optimized.save(filepath, format=format_name.upper(), **save_kwargs)
        self._logger.debug(
            f"Screenshot saved: {filepath} ({format_name.upper()} {optimized.width}x{optimized.height})"
        )
        return str(filepath)

    def _normalize_bbox(self, left: int, top: int, right: int, bottom: int) -> Tuple[int, int, int, int]:
        """Clamp a bounding box within the visible screen area."""

        screen_width, screen_height = self._screen_size
        left = max(0, min(left, screen_width - 1))
        top = max(0, min(top, screen_height - 1))
        right = max(left + 1, min(right, screen_width))
        bottom = max(top + 1, min(bottom, screen_height))
        return int(left), int(top), int(right), int(bottom)

    def _focus_bbox(self, center: Tuple[int, int], size: Optional[int] = None) -> Tuple[int, int, int, int]:
        """Compute the bounding box for a focus region around a coordinate."""

        size = size or config.screen_focus_size
        half = max(size // 2, 8)
        left = center[0] - half
        top = center[1] - half
        right = center[0] + half
        bottom = center[1] + half
        return self._normalize_bbox(left, top, right, bottom)

    def capture_focus_region(
        self,
        center: Tuple[int, int],
        size: Optional[int] = None,
    ) -> Image.Image:
        """Capture a zoomed-in region around a coordinate for diagnostics."""

        bbox = self._focus_bbox(center, size)
        try:
            focus_image = ImageGrab.grab(bbox=bbox)
        except Exception as exc:  # pragma: no cover - dependency on OS/hardware
            self._logger.error(f"Failed to capture focus region {bbox}: {exc}")
            raise

        target_size = size or config.screen_focus_size
        if focus_image.width != target_size or focus_image.height != target_size:
            focus_image = focus_image.resize((target_size, target_size), RESAMPLE_LANCZOS)

        return focus_image

    def crop_focus_region(
        self,
        image: Image.Image,
        center: Tuple[int, int],
        size: Optional[int] = None,
    ) -> Image.Image:
        """Crop a focus region from an existing screenshot."""

        bbox = self._focus_bbox(center, size)
        cropped = image.crop(bbox)
        target_size = size or config.screen_focus_size
        if cropped.width != target_size or cropped.height != target_size:
            cropped = cropped.resize((target_size, target_size), RESAMPLE_LANCZOS)
        return cropped

    def save_focus_region(
        self,
        center: Tuple[int, int],
        size: Optional[int] = None,
        *,
        prefix: str = "focus",
        image: Optional[Image.Image] = None,
    ) -> Optional[str]:
        """Persist a focus-region capture to disk and return its path."""

        try:
            focus_image = image or self.capture_focus_region(center, size)
        except Exception as exc:  # pragma: no cover - dependency on OS/hardware
            self._logger.debug(f"Focus capture skipped due to error: {exc}")
            return None

        focus_dir = config.screenshots_dir / "focus"
        focus_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)

        optimized, format_name, save_kwargs = self._prepare_image_for_storage(
            focus_image,
            format_override=None,
            scale_override=1.0,
            max_width_override=0,
            max_height_override=0,
        )
        filename = f"{prefix}_{timestamp}.{format_name}"
        filepath = (focus_dir / filename).resolve()

        try:
            optimized.save(filepath, format=format_name.upper(), **save_kwargs)
            self._logger.debug(
                f"Focus region saved: {filepath} ({format_name.upper()} {optimized.width}x{optimized.height})"
            )
            return str(filepath)
        except Exception as exc:
            self._logger.debug(f"Failed to save focus region: {exc}")
            return None
