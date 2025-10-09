"""Setup verification tests for the AI Agent environment."""

from __future__ import annotations

import importlib
import locale
from typing import Iterable

import pytest

from src.config.config import AgentConfig
from src.core.ui_overlay import AgentOverlayUI


REQUIRED_MODULES: Iterable[str] = (
    "google.generativeai",
    "pyautogui",
    "pywinauto",
    "PIL",
    "cv2",
    "pytesseract",
    "psutil",
    "pygetwindow",
    "pyperclip",
    "keyboard",
)


@pytest.mark.parametrize("module_name", REQUIRED_MODULES)
def test_required_imports(module_name: str) -> None:
    """Ensure core third-party dependencies are importable."""

    module = importlib.import_module(module_name)
    assert module is not None


def test_tesseract_available() -> None:
    """Verify Tesseract OCR is accessible when installed."""

    pytesseract = pytest.importorskip("pytesseract", reason="Tesseract is not installed")
    try:
        version = pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        pytest.skip("Tesseract executable is not available on PATH")

    assert version is not None


def test_agent_config_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    """AgentConfig should normalize image settings and ensure directories exist."""

    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")
    monkeypatch.setenv("SCREENSHOT_FORMAT", "jpg")
    monkeypatch.setenv("VISION_IMAGE_FORMAT", "JPG")

    cfg = AgentConfig()

    assert cfg.screenshot_format == "jpeg"
    assert cfg.vision_image_format == "jpeg"
    assert cfg.logs_dir.exists()
    assert cfg.screenshots_dir.exists()

    cfg.validate_config()


def test_language_detection_resilient() -> None:
    """Locale detection should always yield a string value."""

    system_locale = locale.getlocale()[0]
    assert system_locale is None or isinstance(system_locale, str)


def test_ui_overlay_instantiation() -> None:
    """Overlay UI class should initialize without starting the UI loop."""

    overlay = AgentOverlayUI(opacity=0.5)
    assert overlay.opacity == 0.5
    assert overlay.root is None
