"""Unit tests for src/perception/screen_capture.py.

Only tests pure-Python functions that do NOT need a live Windows desktop
(snapshot_to_text, build_control_snapshot helpers, _safe_str, etc.)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.perception.screen_capture import (
    _safe_str,
    snapshot_to_text,
)


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
