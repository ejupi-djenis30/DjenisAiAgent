"""Unit tests for src/perception/screen_capture.py.

Only tests pure-Python functions that do NOT need a live Windows desktop
(snapshot_to_text, build_control_snapshot helpers, _safe_str, etc.)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.perception.screen_capture import (
    ScreenCapture,
    _downscale_for_perception,
    _get_active_window,
    _safe_str,
    build_control_snapshot,
    capture_ui_tree,
    get_latest_ui_snapshot,
    get_multimodal_context,
    refresh_ui_snapshot,
    snapshot_to_text,
)

pytest.importorskip("pyautogui")
pytest.importorskip("pywinauto")

# ---------------------------------------------------------------------------
# _safe_str
# ---------------------------------------------------------------------------


class TestSafeStr:
    def test_none_returns_empty(self) -> None:
        assert _safe_str(None) == ""

    def test_string_is_stripped(self) -> None:
        assert _safe_str("  hello  ") == "hello"

    def test_integer_is_converted(self) -> None:
        assert _safe_str(42) == "42"

    def test_empty_string_stays_empty(self) -> None:
        assert _safe_str("") == ""

    def test_whitespace_only_returns_empty(self) -> None:
        assert _safe_str("   ") == ""

    def test_downscale_for_perception_resizes_image(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from PIL import Image

        monkeypatch.setattr("src.perception.screen_capture.config.perception_downscale", 0.5)
        image = Image.new("RGB", (100, 80), "white")

        resized = _downscale_for_perception(image)

        assert resized.size == (50, 40)


# ---------------------------------------------------------------------------
# snapshot_to_text
# ---------------------------------------------------------------------------


class TestSnapshotToText:
    def test_empty_snapshot_returns_no_active_window_message(self) -> None:
        result = snapshot_to_text([])
        assert "Nessuna finestra attiva" in result

    def test_single_entry_renders_correctly(self) -> None:
        snapshot = [
            {
                "index": 1,
                "depth": 0,
                "control_type": "Window",
                "friendly_class": "Window",
                "class_name": "",
                "title": "Notepad",
                "name": "Notepad",
                "auto_id": "",
                "control_id": None,
                "selector": "Notepad",
            }
        ]
        text = snapshot_to_text(snapshot)
        assert "[1]" in text
        assert "Notepad" in text

    def test_depth_indentation(self) -> None:
        snapshot = [
            {
                "index": 1,
                "depth": 0,
                "control_type": "Window",
                "friendly_class": "",
                "class_name": "",
                "title": "App",
                "name": "",
                "auto_id": "",
                "control_id": None,
                "selector": "App",
            },
            {
                "index": 2,
                "depth": 2,
                "control_type": "Button",
                "friendly_class": "",
                "class_name": "",
                "title": "OK",
                "name": "",
                "auto_id": "",
                "control_id": None,
                "selector": "OK",
            },
        ]
        text = snapshot_to_text(snapshot)
        lines = text.splitlines()
        # Depth-0 line starts at column 0 (no indentation)
        assert lines[0].startswith("[1]")
        # Depth-2 line should be indented with 4 spaces (2 * "  ")
        assert lines[1].startswith("    [2]")

    def test_auto_id_is_included(self) -> None:
        snapshot = [
            {
                "index": 1,
                "depth": 0,
                "control_type": "Edit",
                "friendly_class": "",
                "class_name": "",
                "title": "",
                "name": "Search",
                "auto_id": "SearchBox",
                "control_id": None,
                "selector": "SearchBox",
            }
        ]
        text = snapshot_to_text(snapshot)
        assert "SearchBox" in text

    def test_duplicate_name_and_title_not_repeated(self) -> None:
        """If name == title, it should appear only once."""
        snapshot = [
            {
                "index": 1,
                "depth": 0,
                "control_type": "Button",
                "friendly_class": "",
                "class_name": "",
                "title": "Save",
                "name": "Save",
                "auto_id": "",
                "control_id": None,
                "selector": "Save",
            }
        ]
        text = snapshot_to_text(snapshot)
        # "Save" should appear, but not duplicated in the same entry line
        line = text.splitlines()[0]
        assert line.count("Save") == 1

    def test_control_type_fallback_to_friendly_class(self) -> None:
        snapshot = [
            {
                "index": 1,
                "depth": 0,
                "control_type": "",
                "friendly_class": "Edit",
                "class_name": "",
                "title": "Input",
                "name": "",
                "auto_id": "",
                "control_id": None,
                "selector": "Input",
            }
        ]
        text = snapshot_to_text(snapshot)
        assert "Edit" in text

    def test_multiple_entries_produce_correct_line_count(self) -> None:
        snapshot = [
            {
                "index": i,
                "depth": 0,
                "control_type": "Control",
                "friendly_class": "",
                "class_name": "",
                "title": f"Item {i}",
                "name": "",
                "auto_id": "",
                "control_id": None,
                "selector": f"Item {i}",
            }
            for i in range(1, 6)
        ]
        text = snapshot_to_text(snapshot)
        assert len(text.splitlines()) == 5


class _FakeWrapper:
    def __init__(self, title: str, children: list[Any] | None = None) -> None:
        self._title = title
        self._children = children or []
        self.element_info = MagicMock(
            name=title,
            automation_id=f"{title}-id",
            control_type="Button",
            class_name="Button",
            control_id=7,
            handle=123,
        )

    def window_text(self) -> str:
        return self._title

    def children(self) -> list[Any]:
        return self._children

    def friendly_class_name(self) -> str:
        return "Button"


class TestSnapshotBuilders:
    def test_build_control_snapshot_walks_children(self) -> None:
        child = _FakeWrapper("Child")
        root = _FakeWrapper("Root", [child])

        snapshot = build_control_snapshot(root, max_depth=2, include_wrappers=True)

        assert len(snapshot) == 2
        assert snapshot[0]["wrapper"] is root
        assert snapshot[1]["depth"] == 1

    def test_capture_and_refresh_snapshot_cache_results(self) -> None:
        root = _FakeWrapper("Root")

        rendered = capture_ui_tree(root)
        refreshed = refresh_ui_snapshot(root)

        assert "Root" in rendered
        assert refreshed == get_latest_ui_snapshot()

    def test_get_multimodal_context_uses_uia_backend_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        screenshot = MagicMock()
        root = _FakeWrapper("Root")

        monkeypatch.setattr(
            "src.perception.screen_capture.pyautogui.screenshot", lambda: screenshot
        )
        monkeypatch.setattr(
            "src.perception.screen_capture._get_active_window", lambda backend: root
        )

        image, ui_tree = get_multimodal_context()

        assert image is screenshot
        assert "Root" in ui_tree

    def test_get_multimodal_context_reports_fallback_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.perception.screen_capture.pyautogui.screenshot", lambda: MagicMock()
        )

        def fail_backend(backend: str):
            raise RuntimeError(f"{backend} failed")

        monkeypatch.setattr("src.perception.screen_capture._get_active_window", fail_backend)

        _, ui_tree = get_multimodal_context()

        assert "Dettagli" in ui_tree
        assert "UIA" in ui_tree
        assert "Win32" in ui_tree

    def test_get_active_window_returns_first_window(self, monkeypatch: pytest.MonkeyPatch) -> None:
        desktop = MagicMock()
        desktop.windows.return_value = ["window-1"]
        monkeypatch.setattr("src.perception.screen_capture.Desktop", lambda backend: desktop)

        assert _get_active_window("uia") == "window-1"

    def test_screen_capture_wrapper_methods_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        screen_capture = ScreenCapture()
        screenshot = MagicMock()
        monkeypatch.setattr(
            "src.perception.screen_capture.get_multimodal_context", lambda: (screenshot, "tree")
        )
        monkeypatch.setattr(
            "src.perception.screen_capture.pyautogui.screenshot", lambda: screenshot
        )

        assert screen_capture.get_context() == (screenshot, "tree")
        assert screen_capture.capture_screen() is screenshot
        assert screen_capture.prepare_for_gemini(screenshot) is screenshot
