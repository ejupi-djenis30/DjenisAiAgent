"""Behavioral tests for privileged and platform-bound action tools.

The suite never launches a process, opens a real file, or controls the desktop.
It verifies that permission checks run before those boundaries and that approved
operations pass only the expected, shell-free arguments to the platform API.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.action import tools as tools_module


@pytest.fixture(autouse=True)
def operator_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from an explicit, privileged operator configuration."""

    monkeypatch.setattr(tools_module.config, "permission_tier", "system")
    monkeypatch.setattr(tools_module.config, "confirm_dangerous_actions", True)
    monkeypatch.setattr(tools_module.config, "allowed_paths", (str(Path.cwd()),))
    monkeypatch.setattr(tools_module.config, "allowed_applications", ("approved.exe",))
    monkeypatch.setattr(tools_module.config, "allowed_shell_commands", (sys.executable,))


@pytest.mark.parametrize(
    ("tier", "confirmed", "message"),
    [
        ("observe", True, "requires permission tier 'system'"),
        ("system", False, "Dangerous tools are disabled"),
    ],
)
def test_shell_permission_and_confirmation_fail_closed_before_process_execution(
    monkeypatch: pytest.MonkeyPatch,
    tier: str,
    confirmed: bool,
    message: str,
) -> None:
    runner = MagicMock(side_effect=AssertionError("process execution must remain unreachable"))
    monkeypatch.setattr(tools_module.config, "permission_tier", tier)
    monkeypatch.setattr(tools_module.config, "confirm_dangerous_actions", confirmed)
    monkeypatch.setattr(tools_module.subprocess, "run", runner)

    payload = json.loads(tools_module.run_shell_command(f'"{sys.executable}" --version'))

    assert payload["stdout"] == ""
    assert payload["return_code"] == -1
    assert message in payload["stderr"]
    runner.assert_not_called()


def test_shell_allowlist_denial_precedes_process_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = MagicMock(side_effect=AssertionError("an unlisted executable must never run"))
    monkeypatch.setattr(tools_module.config, "allowed_shell_commands", ("approved.exe",))
    monkeypatch.setattr(tools_module.subprocess, "run", runner)

    payload = json.loads(tools_module.run_shell_command("untrusted.exe --version"))

    assert payload["return_code"] == -1
    assert "not allowlisted" in payload["stderr"]
    runner.assert_not_called()


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("", "cannot be empty"),
        ("x" * 513, "safe length limit"),
        ("Get-ChildItem\nGet-Process", "Multiline"),
        ("Get-ChildItem > inventory.txt", "redirection"),
        ("Remove-Item inventory.txt", "Destructive"),
        ("Set-Content inventory.txt value", "write operations"),
        ("Start-Process calculator.exe", "Process and machine control"),
        ("git push origin main", "Mutating git"),
        ("Invoke-Expression $payload", "Dynamic shell evaluation"),
    ],
)
def test_shell_validation_rejects_unsafe_command_shapes(command: str, message: str) -> None:
    assert message in (tools_module._validate_shell_command(command) or "")


def test_shell_invocation_is_an_exact_argument_vector_with_bounded_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        captured["arguments"] = arguments
        captured["kwargs"] = kwargs
        kwargs["stdout"].write(b"approved output")
        kwargs["stderr"].write(b"diagnostic")
        return subprocess.CompletedProcess(arguments, 7)

    monkeypatch.setattr(tools_module.subprocess, "run", fake_run)

    payload = json.loads(tools_module.run_shell_command(f'"{sys.executable}" -c "print(123)"'))

    assert Path(captured["arguments"][0]).resolve(strict=True) == Path(sys.executable).resolve(
        strict=True
    )
    assert captured["arguments"][1:] == ["-c", "print(123)"]
    assert "shell" not in captured["kwargs"]
    assert captured["kwargs"]["timeout"] == tools_module.config.shell_timeout
    assert payload == {
        "stdout": "approved output",
        "stderr": "diagnostic",
        "return_code": 7,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def test_shell_reports_missing_executable_without_invoking_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = MagicMock(side_effect=AssertionError("missing executable must not run"))
    monkeypatch.setattr(tools_module.config, "allowed_shell_commands", ("missing-tool.exe",))
    monkeypatch.setattr(tools_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(tools_module.subprocess, "run", runner)

    payload = json.loads(tools_module.run_shell_command("missing-tool.exe --version"))

    assert payload["return_code"] == -1
    assert payload["stderr"] == "The allowlisted executable was not found."
    runner.assert_not_called()


def test_shell_timeout_and_unexpected_errors_are_returned_as_bounded_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tools_module.subprocess,
        "run",
        MagicMock(side_effect=subprocess.TimeoutExpired(sys.executable, timeout=3)),
    )
    timeout_payload = json.loads(tools_module.run_shell_command(f'"{sys.executable}" --version'))
    assert timeout_payload["return_code"] == -1
    assert "timed out" in timeout_payload["stderr"]

    monkeypatch.setattr(
        tools_module,
        "split_command_arguments",
        MagicMock(side_effect=RuntimeError("parser unavailable")),
    )
    error_payload = json.loads(tools_module.run_shell_command(f'"{sys.executable}" --version'))
    assert error_payload["return_code"] == -1
    assert error_payload["stderr"] == "Error: An unexpected error occurred: parser unavailable"


def test_application_launch_requires_tier_confirmation_and_exact_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    popen = MagicMock(side_effect=AssertionError("denied application must never start"))
    monkeypatch.setattr(tools_module.subprocess, "Popen", popen)

    monkeypatch.setattr(tools_module.config, "permission_tier", "interact")
    assert "requires permission tier 'system'" in tools_module.start_application("approved.exe")

    monkeypatch.setattr(tools_module.config, "permission_tier", "system")
    monkeypatch.setattr(tools_module.config, "confirm_dangerous_actions", False)
    assert "Dangerous tools are disabled" in tools_module.start_application("approved.exe")

    monkeypatch.setattr(tools_module.config, "confirm_dangerous_actions", True)
    assert "not allowlisted" in tools_module.start_application("untrusted.exe")
    popen.assert_not_called()


def test_approved_application_launch_passes_one_literal_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    popen = MagicMock()
    monkeypatch.setattr(tools_module.subprocess, "Popen", popen)

    result = tools_module.start_application("approved.exe")

    assert "Start command issued" in result
    popen.assert_called_once()
    arguments, options = popen.call_args
    assert arguments == (["approved.exe"],)
    assert options["close_fds"] is True
    assert isinstance(options["creationflags"], int)


def test_application_launch_reports_platform_and_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tools_module.subprocess,
        "Popen",
        MagicMock(side_effect=FileNotFoundError),
    )
    assert "not found in system PATH" in tools_module.start_application("approved.exe")

    monkeypatch.setattr(
        tools_module.subprocess,
        "Popen",
        MagicMock(side_effect=OSError("platform rejected launch")),
    )
    assert "platform rejected launch" in tools_module.start_application("approved.exe")


def test_file_open_is_confined_and_requires_dangerous_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener = MagicMock(side_effect=AssertionError("denied file must not open"))
    monkeypatch.setattr(os, "startfile", opener, raising=False)

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / "approved"
        root.mkdir()
        target = root / "brief.txt"
        target.write_text("brief", encoding="utf-8")
        outside = Path(folder) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        monkeypatch.setattr(tools_module.config, "allowed_paths", (str(root),))

        assert "outside allowed roots" in tools_module.open_file(str(outside))
        monkeypatch.setattr(tools_module.config, "confirm_dangerous_actions", False)
        assert "Dangerous tools are disabled" in tools_module.open_file(str(target))

    opener.assert_not_called()


def test_file_open_reports_missing_file_and_non_windows_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        monkeypatch.setattr(tools_module.config, "allowed_paths", (str(root),))
        assert "does not exist" in tools_module.open_file(str(root / "missing.txt"))

        target = root / "brief.txt"
        target.write_text("brief", encoding="utf-8")
        monkeypatch.delattr(os, "startfile", raising=False)
        assert "only supported on Windows" in tools_module.open_file(str(target))


def test_url_open_rejects_observe_tier_and_credentialed_urls_without_browser_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import webbrowser

    opener = MagicMock(side_effect=AssertionError("unsafe URL must never open"))
    monkeypatch.setattr(webbrowser, "open", opener)

    monkeypatch.setattr(tools_module.config, "permission_tier", "observe")
    assert "requires permission tier 'interact'" in tools_module.open_url("https://example.com")

    monkeypatch.setattr(tools_module.config, "permission_tier", "interact")
    assert "Only absolute http" in tools_module.open_url("https://user:secret@example.com")
    assert "Only absolute http" in tools_module.open_url("file:///etc/passwd")
    opener.assert_not_called()


def test_url_open_reports_browser_error_without_exposing_a_credentialed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", MagicMock(side_effect=OSError("browser unavailable")))

    result = tools_module.open_url("https://example.com/path")

    assert "browser unavailable" in result
    assert "https://example.com/path" in result


def test_screenshot_save_is_confined_and_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screenshot = SimpleNamespace(width=1280, height=720, save=MagicMock())
    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(screenshot=lambda: screenshot))

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / "approved"
        root.mkdir()
        outside = Path(folder) / "outside.png"
        monkeypatch.setattr(tools_module.config, "allowed_paths", (str(root),))

        assert "outside allowed roots" in tools_module.take_screenshot(str(outside))
        monkeypatch.setattr(tools_module.config, "confirm_dangerous_actions", False)
        assert "Dangerous tools are disabled" in tools_module.take_screenshot(
            str(root / "safe.png")
        )

    screenshot.save.assert_not_called()
    assert "no file was written" in tools_module.take_screenshot()


def test_filesystem_read_and_write_stay_inside_operator_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / "approved"
        root.mkdir()
        outside = Path(folder) / "outside.txt"
        outside.write_text("private", encoding="utf-8")
        monkeypatch.setattr(tools_module.config, "allowed_paths", (str(root),))

        assert "outside allowed roots" in tools_module.list_files(str(Path(folder)))
        assert "outside allowed roots" in tools_module.read_file(str(outside))
        assert "outside allowed roots" in tools_module.write_file(str(outside), "overwrite")
        assert outside.read_text(encoding="utf-8") == "private"


def test_write_file_requires_dangerous_confirmation_before_creating_parents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        target = root / "new" / "record.txt"
        monkeypatch.setattr(tools_module.config, "allowed_paths", (str(root),))
        monkeypatch.setattr(tools_module.config, "confirm_dangerous_actions", False)

        result = tools_module.write_file(str(target), "record")

        assert "Dangerous tools are disabled" in result
        assert not target.parent.exists()


def test_filesystem_tools_cover_directory_and_decode_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        empty = root / "empty"
        empty.mkdir()
        text = root / "legacy.txt"
        text.write_bytes("città".encode("latin-1"))
        monkeypatch.setattr(tools_module.config, "allowed_paths", (str(root),))

        assert "is not a directory" in tools_module.list_files(str(text))
        assert "is empty" in tools_module.list_files(str(empty))
        assert "città" in tools_module.read_file(str(text))


def test_active_window_uses_backend_fallback_and_returns_none_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = SimpleNamespace(window_text=lambda: "Approved window")
    attempted: list[str] = []

    class FakeApplication:
        def __init__(self, *, backend: str) -> None:
            self.backend = backend
            attempted.append(backend)

        def connect(self, **_kwargs: object) -> None:
            if self.backend == "uia":
                raise RuntimeError("UIA unavailable")

        def top_window(self) -> object:
            return window

    monkeypatch.setattr(tools_module, "Application", FakeApplication)
    assert tools_module._get_active_window() is window
    assert attempted == ["uia", "win32"]

    class FailingApplication:
        def __init__(self, *, backend: str) -> None:
            self.backend = backend

        def connect(self, **_kwargs: object) -> None:
            raise RuntimeError(f"{self.backend} unavailable")

    monkeypatch.setattr(tools_module, "Application", FailingApplication)
    assert tools_module._get_active_window() is None


def test_element_lookup_creates_locator_from_current_window_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = SimpleNamespace(window_text=lambda: "Editor")
    snapshot = [
        {
            "index": 2,
            "title": "Save draft",
            "name": "Save draft",
            "auto_id": "save",
            "control_type": "Button",
            "class_name": "Button",
            "depth": 1,
        },
        {
            "index": 3,
            "title": "Save as",
            "name": "Save as",
            "auto_id": "save-as",
            "control_type": "Button",
            "class_name": "Button",
            "depth": 2,
        },
    ]
    monkeypatch.setattr(tools_module, "_get_active_window", lambda: window)
    monkeypatch.setattr(tools_module, "get_latest_ui_snapshot", lambda: [])
    monkeypatch.setattr(tools_module, "_execute_with_timeout", lambda *args, **kwargs: snapshot)

    result = tools_module.element_id("Save", control_type="Button")

    assert "Locator created: element:" in result
    assert "Suggested alternative: index=#3" in result
    token = result.split(" ->", maxsplit=1)[0].removeprefix("Locator created: ")
    assert token in tools_module._LOCATOR_CACHE

    assert "No element with index #99" in tools_module.element_id("#99")


def test_element_lookup_browser_fallback_and_timeout_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = SimpleNamespace(window_text=lambda: "Browser")
    monkeypatch.setattr(tools_module, "_get_active_window", lambda: window)
    monkeypatch.setattr(tools_module, "get_latest_ui_snapshot", lambda: [])
    monkeypatch.setattr(tools_module, "_execute_with_timeout", lambda *args, **kwargs: [])
    monkeypatch.setattr(tools_module, "_is_browser_window", lambda _window: True)
    monkeypatch.setattr(tools_module.browser_tools, "is_browser_available", lambda: True)
    monkeypatch.setattr(
        tools_module.browser_tools,
        "browser_find_and_click",
        lambda _query: "✅ Browser target clicked",
    )
    assert "[Browser Mode]" in tools_module.element_id("Continue")

    monkeypatch.setattr(
        tools_module.browser_tools,
        "browser_find_and_click",
        lambda _query: "target unavailable",
    )
    monkeypatch.setattr(
        tools_module.browser_tools,
        "get_browser_setup_hint",
        lambda: "attach a supported browser",
    )
    assert "attach a supported browser" in tools_module.element_id("Continue")


def test_fast_element_lookup_uses_native_control_then_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = SimpleNamespace(
        name="Continue",
        automation_id="continue",
        control_type="Button",
        class_name="Button",
    )
    found = SimpleNamespace(exists=lambda timeout: timeout == 2, element_info=info)
    window = SimpleNamespace(child_window=lambda **_criteria: found)
    monkeypatch.setattr(tools_module, "_get_active_window", lambda: window)

    result = tools_module.element_id_fast("Continue", control_type="Button")
    assert "Locator created: element:" in result

    missing = SimpleNamespace(exists=lambda timeout: False)
    monkeypatch.setattr(
        tools_module,
        "_get_active_window",
        lambda: SimpleNamespace(child_window=lambda **_criteria: missing),
    )
    monkeypatch.setattr(tools_module, "element_id", lambda *args, **kwargs: "snapshot fallback")
    assert tools_module.element_id_fast("Missing") == "snapshot fallback"


def test_element_actions_use_resolved_wrappers_and_report_missing_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = object()
    wrapper = MagicMock()
    wrapper.window_text.return_value = "Current value"
    metadata = {"title": "Name", "control_type": "Edit"}
    monkeypatch.setattr(tools_module, "_get_active_window", lambda: window)
    monkeypatch.setattr(tools_module, "_resolve_control", lambda *_args: (wrapper, metadata))
    monkeypatch.setattr(tools_module, "_prepare_wrapper", lambda control: control)

    assert "Clicked element 'Name' successfully" in tools_module.click("element:name")
    assert "Typed 5 characters" in tools_module.type_text("element:name", "Ada 1")
    assert "Current value" in tools_module.get_text("element:name")
    assert "Double-clicked element 'Name'" in tools_module.double_click("element:name")
    assert "Right-clicked element 'Name'" in tools_module.right_click("element:name")
    wrapper.click_input.assert_called_once()
    wrapper.type_keys.assert_called_once_with("Ada 1", with_spaces=True)
    wrapper.double_click_input.assert_called_once()
    wrapper.right_click_input.assert_called_once()

    monkeypatch.setattr(
        tools_module,
        "_resolve_control",
        lambda *_args: (None, {"error": "stale locator"}),
    )
    monkeypatch.setattr(tools_module, "_is_browser_window", lambda _window: False)
    assert "stale locator" in tools_module.click("element:stale")
    assert "stale locator" in tools_module.type_text("element:stale", "text")
    assert "stale locator" in tools_module.get_text("element:stale")


def test_keyboard_and_pointer_contracts_validate_inputs_and_exact_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, object]] = []
    fake_pyautogui = SimpleNamespace(
        scroll=lambda amount: events.append(("scroll", amount)),
        hscroll=lambda amount: events.append(("hscroll", amount)),
        press=lambda key: events.append(("press", key)),
        write=lambda text, interval: events.append(("write", (text, interval))),
        hotkey=lambda *keys: events.append(("hotkey", keys)),
        moveTo=lambda x, y, duration: events.append(("move", (x, y, duration))),
        position=lambda: (14, 28),
    )
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)
    monkeypatch.setattr(tools_module.time, "sleep", lambda _seconds: None)

    assert "Invalid direction" in tools_module.scroll("diagonal")
    assert "Scrolled up" in tools_module.scroll("up", 2)
    assert "Scrolled left" in tools_module.scroll("left", 3)
    assert "Invalid key" in tools_module.press_key_repeat("letter-a", 2)
    assert "Invalid times" in tools_module.press_key_repeat("enter", 0)
    assert "Successfully pressed key" in tools_module.press_key_repeat("enter", 2)
    assert "No keys provided" in tools_module.hotkey("+")
    assert "pressed successfully" in tools_module.hotkey("ctrl+shift+p")
    assert "Mouse moved" in tools_module.move_mouse(10, 20)
    assert "Invalid coordinates" in tools_module.move_mouse("x", 20)  # type: ignore[arg-type]
    assert "Current position is (14, 28)" in tools_module.verify_mouse_position()
    assert "CONFIRMED at (14, 28)" in tools_module.confirm_mouse_position()

    assert ("scroll", 2) in events
    assert ("hscroll", -3) in events
    assert events.count(("press", "enter")) == 2
    assert ("hotkey", ("ctrl", "shift", "p")) in events


def test_generic_key_sequence_distinguishes_special_keys_from_literal_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str]] = []
    fake_pyautogui = SimpleNamespace(
        press=lambda key: events.append(("press", key)),
        write=lambda text, interval: events.append(("write", text)),
    )

    class NoDesktopApplication:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def connect(self, **_kwargs: object) -> None:
            raise RuntimeError("desktop unavailable")

    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)
    monkeypatch.setattr(tools_module, "Application", NoDesktopApplication)
    monkeypatch.setattr(tools_module.time, "sleep", lambda _seconds: None)

    assert "No keys provided" in tools_module.press_keys([])
    assert "Successfully pressed key sequence" in tools_module.press_keys(["hello", "enter"])
    assert events == [("write", "hello"), ("press", "enter")]


def test_calculator_key_sequence_uses_accessible_buttons_not_keyboard_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clicked: list[str] = []

    class Button:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        def click_input(self) -> None:
            clicked.append(self.selector)

    class CalculatorWindow:
        def window_text(self) -> str:
            return "Calculator"

        def child_window(self, *, title_re: str, control_type: str) -> Button:
            assert control_type == "Button"
            return Button(title_re)

    class CalculatorApplication:
        def __init__(self, **_kwargs: object) -> None:
            self.window = CalculatorWindow()

        def connect(self, **_kwargs: object) -> CalculatorApplication:
            return self

        def top_window(self) -> CalculatorWindow:
            return self.window

    keyboard = SimpleNamespace(
        press=MagicMock(side_effect=AssertionError("calculator must use UI buttons")),
        write=MagicMock(side_effect=AssertionError("calculator must use UI buttons")),
    )
    monkeypatch.setitem(sys.modules, "pyautogui", keyboard)
    monkeypatch.setattr(tools_module, "Application", CalculatorApplication)
    monkeypatch.setattr(tools_module.time, "sleep", lambda _seconds: None)

    result = tools_module.press_keys(["12", "+", "="])

    assert result == "✅ Calculator input successful: 12+="
    assert len(clicked) == 4
    keyboard.press.assert_not_called()
    keyboard.write.assert_not_called()


def test_window_operations_report_platform_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = SimpleNamespace(maximize=MagicMock(), close=MagicMock())
    monkeypatch.setattr(tools_module, "_get_active_window", lambda: window)
    assert tools_module.maximize_window() == "Maximized the active window."
    assert tools_module.close_window() == "Closed the active window."
    window.maximize.assert_called_once()
    window.close.assert_called_once()

    monkeypatch.setattr(tools_module, "_get_active_window", lambda: None)
    assert "Could not access" in tools_module.maximize_window()
    assert "Could not access" in tools_module.close_window()


def test_wait_seconds_enforces_the_bounded_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeper = MagicMock()
    monkeypatch.setattr("time.sleep", sleeper)

    assert "between 1 and 30" in tools_module.wait_seconds(0)
    assert tools_module.wait_seconds(2) == "Waited 2 seconds."
    sleeper.assert_called_once_with(2)
