"""Unit tests for deterministic focus strategy."""

from typing import List, Dict, Any

import pytest

from src.automation.ui_automation import UIAutomationEngine


@pytest.fixture(autouse=True)
def _stub_pyautogui(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent real pyautogui calls during tests."""

    monkeypatch.setattr("src.automation.ui_automation.pyautogui.size", lambda: (1920, 1080))
    monkeypatch.setattr("src.automation.ui_automation.pyautogui.moveTo", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.automation.ui_automation.pyautogui.dragTo", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.automation.ui_automation.pyautogui.locateOnScreen", lambda *args, **kwargs: None)


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> UIAutomationEngine:
    """Return a UIAutomationEngine with minimal dependencies stubbed."""

    monkeypatch.setattr("src.automation.ui_automation.get_ocr_engine", lambda: None)
    return UIAutomationEngine()


def test_focus_window_skips_when_already_focused(engine: UIAutomationEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure focus_window exits early if the target already has focus."""

    monkeypatch.setattr(engine, "_verify_focus", lambda target, allow_partial=True: True)
    monkeypatch.setattr(engine, "get_active_window_title", lambda: "New tab - Microsoft Edge")

    called: List[str] = []

    def fail(*args, **kwargs):  # pragma: no cover - should not be invoked
        called.append("called")
        return False

    monkeypatch.setattr(engine, "_focus_direct", fail)
    monkeypatch.setattr(engine, "_focus_from_candidates", fail)

    assert engine.focus_window("Edge") is True
    assert not called


def test_deterministic_window_choice_prefers_substring(engine: UIAutomationEngine) -> None:
    """Verify deterministic matcher prefers exact substring matches."""

    candidates: List[Dict[str, Any]] = [
        {"title": "New tab - Microsoft Edge", "hwnd": 1, "process_name": "msedge.exe", "width": 800, "height": 600},
        {"title": "Calculator", "hwnd": 2, "process_name": "calculatorapp.exe", "width": 400, "height": 300},
    ]

    match = engine._deterministic_window_choice("Edge", candidates)
    assert match is not None
    assert match["title"] == "New tab - Microsoft Edge"


def test_focus_from_candidates_uses_deterministic(engine: UIAutomationEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure fallback focuses deterministic candidate before invoking AI."""

    candidate = {"title": "Visual Studio Code", "hwnd": 1234, "process_name": "Code.exe", "width": 1200, "height": 800}

    monkeypatch.setattr(engine, "_enumerate_focus_candidates", lambda: [candidate])
    monkeypatch.setattr(engine, "_deterministic_window_choice", lambda target, cands: candidate)
    monkeypatch.setattr(engine, "_select_window_with_ai", lambda target, cands: None)

    focused: List[int] = []

    def fake_focus(hwnd: int, *, expected_title: str | None = None) -> bool:
        focused.append(hwnd)
        return True

    monkeypatch.setattr(engine, "_focus_window_handle", fake_focus)

    assert engine._focus_from_candidates("Visual Studio Code", allow_ai=True) is True
    assert focused == [candidate["hwnd"]]
