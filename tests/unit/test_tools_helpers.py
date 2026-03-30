"""Focused unit tests for pure/helper logic in src/action/tools.py."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.action import tools as tools_module

pytest.importorskip("pyautogui")
pytest.importorskip("pywinauto")


class _Info:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _Control:
    def __init__(self, *, title: str = "", info: object | None = None) -> None:
        self._title = title
        self.element_info = info

    def window_text(self) -> str:
        return self._title


@pytest.fixture(autouse=True)
def clear_locator_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_module, "_LOCATOR_CACHE", OrderedDict())


class TestBasicHelpers:
    def test_execute_with_timeout_returns_result(self) -> None:
        assert tools_module._execute_with_timeout(lambda: "ok", timeout=0.2) == "ok"

    def test_execute_with_timeout_returns_default_on_timeout(self) -> None:
        result = tools_module._execute_with_timeout(
            lambda: time.sleep(0.05), timeout=0.01, default="fallback"
        )

        assert result == "fallback"

    def test_normalize_and_safe_attr(self) -> None:
        sample = SimpleNamespace(name=lambda: "  Hello ")

        assert tools_module._normalize("  HeLLo ") == "hello"
        assert tools_module._normalize(None) == ""
        assert tools_module._safe_attr(sample, "name") == "Hello"
        assert tools_module._safe_attr(sample, "missing") == ""

    def test_browser_window_detection(self) -> None:
        chrome_window = SimpleNamespace(window_text=lambda: "Google Chrome")

        assert tools_module._is_browser_window(chrome_window) is True
        assert (
            tools_module._is_browser_window(SimpleNamespace(window_text=lambda: "Notepad")) is False
        )

    def test_augment_metadata_adds_missing_fields(self) -> None:
        info = _Info(
            name="Save", automation_id="save-btn", control_type="Button", class_name="Button"
        )
        control = _Control(title="Save", info=info)

        metadata = tools_module._augment_metadata({"selector": "save-btn"}, control)

        assert metadata["title"] == "Save"
        assert metadata["name"] == "Save"
        assert metadata["auto_id"] == "save-btn"

    def test_store_locator_evicts_oldest_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tools_module.config, "locator_cache_size", 1)

        first_token, _ = tools_module._store_locator({"selector": "first"})
        second_token, metadata = tools_module._store_locator({"selector": "second"})

        assert first_token not in tools_module._LOCATOR_CACHE
        assert second_token in tools_module._LOCATOR_CACHE
        assert metadata["selector"] == "second"


class TestLocatorResolution:
    def test_resolve_cached_control_returns_live_wrapper(self) -> None:
        wrapper = SimpleNamespace(element_info=object())
        tools_module._LOCATOR_CACHE["element:1"] = {
            "wrapper": wrapper,
            "metadata": {"selector": "save"},
        }

        resolved = tools_module._resolve_cached_control(SimpleNamespace(), "element:1")

        assert resolved == (wrapper, {"selector": "save"})

    def test_resolve_cached_control_uses_search_hints(self) -> None:
        wrapper = SimpleNamespace(element_info=object())
        spec = MagicMock()
        spec.wrapper_object.return_value = wrapper
        window = MagicMock()
        window.child_window.return_value = spec
        tools_module._LOCATOR_CACHE["element:1"] = {
            "wrapper": None,
            "metadata": {"search_hints": {"title": "Save"}, "selector": "Save"},
        }

        resolved_wrapper, resolved_metadata = tools_module._resolve_cached_control(
            window, "element:1"
        ) or (None, {})

        assert resolved_wrapper is wrapper
        assert resolved_metadata["selector"] == "Save"
        spec.wait.assert_called_once()

    def test_resolve_cached_control_uses_selector_fallback(self) -> None:
        wrapper = SimpleNamespace(element_info=object())
        spec = MagicMock()
        spec.wrapper_object.return_value = wrapper
        window = MagicMock()
        window.child_window.side_effect = tools_module.ElementNotFoundError("missing")
        window.__getitem__.return_value = spec
        tools_module._LOCATOR_CACHE["element:1"] = {
            "wrapper": None,
            "metadata": {"search_hints": {"title": "Save"}, "selector": "Save"},
        }

        resolved_wrapper, resolved_metadata = tools_module._resolve_cached_control(
            window, "element:1"
        ) or (None, {})

        assert resolved_wrapper is wrapper
        assert resolved_metadata["selector"] == "Save"

    def test_resolve_control_returns_direct_lookup_error_metadata(self) -> None:
        window = MagicMock()
        window.__getitem__.side_effect = tools_module.ElementNotFoundError("missing")

        control, metadata = tools_module._resolve_control(window, "missing")

        assert control is None
        assert metadata == {"error": "missing", "selector": "missing"}

    def test_prepare_wrapper_falls_back_when_wrapper_object_missing(self) -> None:
        control = MagicMock()
        del control.wrapper_object

        assert tools_module._prepare_wrapper(control) is control


class TestScoringAndFormatting:
    def test_describe_score_and_format_helpers(self) -> None:
        entry = {
            "title": "Save",
            "name": "Save",
            "auto_id": "save-btn",
            "control_type": "Button",
            "class_name": "Button",
            "selector": "Save",
            "depth": 1,
        }

        assert tools_module._describe_target(entry) == "elemento 'Save'"
        assert tools_module._score_candidate(entry, "save", "button", "", exact=False) > 0
        assert tools_module._score_candidate(entry, "save", "edit", "", exact=False) == -1.0
        assert 'title="Save"' in tools_module._format_metadata(entry)

    def test_build_suggestions_handles_empty_and_non_empty_snapshots(self) -> None:
        snapshot = [{"index": 1, "title": "Save", "name": "", "auto_id": ""}]

        assert "#1 Save" in tools_module._build_suggestions(snapshot)
        assert "Suggerimento" in tools_module._build_suggestions([])


class TestCommandAndClipboard:
    def test_run_shell_command_returns_json_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        completed = subprocess.CompletedProcess(
            args=["powershell"], returncode=0, stdout="hello\n", stderr=""
        )
        monkeypatch.setattr(tools_module.subprocess, "run", lambda *args, **kwargs: completed)

        payload = json.loads(tools_module.run_shell_command("Get-ChildItem"))

        assert payload["stdout"] == "hello"
        assert payload["return_code"] == 0

    def test_run_shell_command_blocks_mutating_commands(self) -> None:
        payload = json.loads(tools_module.run_shell_command("Remove-Item test.txt"))

        assert payload["return_code"] == -1
        assert "blocked" in payload["stderr"].lower()

    def test_run_shell_command_blocks_redirection(self) -> None:
        payload = json.loads(tools_module.run_shell_command("Get-ChildItem > out.txt"))

        assert payload["return_code"] == -1
        assert "redirection" in payload["stderr"].lower()

    def test_run_shell_command_handles_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            tools_module.subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(cmd="pwsh", timeout=1)
            ),
        )

        payload = json.loads(tools_module.run_shell_command("Get-ChildItem"))

        assert payload["return_code"] == -1
        assert "timed out" in payload["stderr"].lower()

    def test_read_clipboard_truncates_oversized_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_pyperclip = SimpleNamespace(paste=lambda: "x" * 120)
        monkeypatch.setitem(sys.modules, "pyperclip", fake_pyperclip)
        monkeypatch.setattr(tools_module.config, "clipboard_max_bytes", 40)

        result = tools_module.read_clipboard()

        assert result.startswith("Clipboard content: ")
        assert len(result) < 120

    def test_read_clipboard_reports_empty_clipboard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_pyperclip = SimpleNamespace(paste=lambda: "")
        monkeypatch.setitem(sys.modules, "pyperclip", fake_pyperclip)

        assert "Clipboard is empty" in tools_module.read_clipboard()

    def test_browser_search_validates_window_and_browser_dependencies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tools_module, "_get_active_window", lambda: None)
        assert "Nessuna finestra attiva" in tools_module.browser_search("search", "term")

        monkeypatch.setattr(tools_module, "_get_active_window", lambda: SimpleNamespace())
        monkeypatch.setattr(tools_module, "_is_browser_window", lambda window: False)
        assert "solo all'interno di un browser" in tools_module.browser_search("search", "term")

        monkeypatch.setattr(tools_module, "_is_browser_window", lambda window: True)
        monkeypatch.setattr(tools_module.browser_tools, "is_browser_available", lambda: False)
        assert "Selenium non disponibile" in tools_module.browser_search("search", "term")

    def test_browser_search_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tools_module, "_get_active_window", lambda: SimpleNamespace())
        monkeypatch.setattr(tools_module, "_is_browser_window", lambda window: True)
        monkeypatch.setattr(tools_module.browser_tools, "is_browser_available", lambda: True)
        monkeypatch.setattr(
            tools_module.browser_tools,
            "browser_find_and_type",
            lambda query, search_term, press_enter: f"typed {query} {search_term} {press_enter}",
        )

        assert tools_module.browser_search("search", "term") == "typed search term True"

    def test_browser_runtime_status_reports_remote_selenium_limits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tools_module.browser_tools, "is_browser_available", lambda: True)
        monkeypatch.setattr(tools_module.config, "runtime_mode", "docker")
        monkeypatch.setattr(tools_module.config, "browser_connection_mode", "remote-selenium")
        monkeypatch.setattr(tools_module.config, "supports_native_desktop", lambda: False)
        monkeypatch.setattr(tools_module.config, "supports_real_browser_media", lambda: False)
        monkeypatch.setattr(tools_module.config, "uses_remote_selenium", lambda: True)

        result = tools_module.browser_runtime_status()

        assert "remote-selenium" in result
        assert "Real browser media/share support: no" in result
        assert "does not support host window/tab sharing" in result

    def test_browser_media_capability_allows_native_windows_media(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tools_module.config, "supports_real_browser_media", lambda: True)
        monkeypatch.setattr(tools_module.config, "uses_remote_selenium", lambda: False)

        result = tools_module.browser_media_capability("tab_share")

        assert "supported" in result
        assert "window_or_tab_share" in result

    def test_browser_media_capability_blocks_remote_selenium_media(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tools_module.config, "supports_real_browser_media", lambda: False)
        monkeypatch.setattr(tools_module.config, "uses_remote_selenium", lambda: True)

        result = tools_module.browser_media_capability("webcam")

        assert "not supported" in result
        assert "Docker/browser-remote mode" in result

    def test_browser_media_capability_validates_input(self) -> None:
        result = tools_module.browser_media_capability("unknown")

        assert "Unsupported media_type" in result

    def test_copy_and_paste_clipboard_shortcuts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded: list[tuple[str, str]] = []
        fake_pyautogui = SimpleNamespace(hotkey=lambda *keys: recorded.append(tuple(keys)))
        monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)

        assert "Ctrl+C" in tools_module.copy_to_clipboard()
        assert "Ctrl+V" in tools_module.paste_from_clipboard()
        assert recorded == [("ctrl", "c"), ("ctrl", "v")]

    def test_set_clipboard_text_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        copied: list[str] = []
        fake_pyperclip = SimpleNamespace(copy=lambda text: copied.append(text))
        monkeypatch.setitem(sys.modules, "pyperclip", fake_pyperclip)

        result = tools_module.set_clipboard_text("hello world")

        assert copied == ["hello world"]
        assert "hello world" in result

    def test_start_application_success_and_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        popen_calls: list[str] = []

        def fake_popen(app_name: str, **kwargs: object) -> None:
            popen_calls.append(app_name)

        monkeypatch.setattr(tools_module.subprocess, "Popen", fake_popen)

        result = tools_module.start_application("notepad.exe")

        assert "Start command issued" in result
        assert popen_calls == ["notepad.exe"]

        def fake_missing(app_name: str, **kwargs: object) -> None:
            raise FileNotFoundError()

        monkeypatch.setattr(tools_module.subprocess, "Popen", fake_missing)
        assert "not found" in tools_module.start_application("missing.exe")

    def test_open_file_and_open_url(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.PathLike
    ) -> None:
        import os

        file_path = tmp_path / "demo.txt"
        file_path.write_text("demo", encoding="utf-8")
        opened_files: list[str] = []
        opened_urls: list[str] = []

        monkeypatch.setattr(os, "startfile", lambda path: opened_files.append(path))
        fake_webbrowser = SimpleNamespace(open=lambda url: opened_urls.append(url))
        monkeypatch.setitem(sys.modules, "webbrowser", fake_webbrowser)

        assert "non esiste" in tools_module.open_file(str(tmp_path / "missing.txt"))
        assert "aperto con successo" in tools_module.open_file(str(file_path))
        assert opened_files == [str(file_path)]

        assert "aperto nel browser" in tools_module.open_url("https://example.com")
        assert opened_urls == ["https://example.com"]

    def test_take_screenshot_with_explicit_and_default_paths(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.PathLike
    ) -> None:
        class FakeScreenshot:
            def __init__(self) -> None:
                self.saved_paths: list[str] = []

            def save(self, path: str) -> None:
                self.saved_paths.append(path)

        fake_screenshot = FakeScreenshot()
        fake_pyautogui = SimpleNamespace(screenshot=lambda: fake_screenshot)
        monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)
        monkeypatch.chdir(tmp_path)

        explicit = str(tmp_path / "shot.png")
        assert explicit in tools_module.take_screenshot(explicit)
        default_result = tools_module.take_screenshot()

        assert fake_screenshot.saved_paths[0] == explicit
        assert fake_screenshot.saved_paths[1].startswith("screenshot_")
        assert "screenshot_" in default_result


class TestFilesystemUtilities:
    def test_list_files_reports_missing_and_directory_contents(
        self, tmp_path: pytest.PathLike
    ) -> None:
        temp_dir = tmp_path / "files"
        temp_dir.mkdir()
        (temp_dir / "nested").mkdir()
        (temp_dir / "demo.txt").write_text("hello", encoding="utf-8")

        assert "does not exist" in tools_module.list_files(str(temp_dir / "missing"))

        result = tools_module.list_files(str(temp_dir))

        assert "[DIR]  nested" in result
        assert "[FILE] demo.txt" in result

    def test_read_file_handles_missing_directory_large_and_encoded_files(
        self, tmp_path: pytest.PathLike
    ) -> None:
        temp_dir = tmp_path / "read"
        temp_dir.mkdir()
        text_file = temp_dir / "latin1.txt"
        text_file.write_bytes("citta\xe0".encode("latin-1"))
        large_file = temp_dir / "large.txt"
        large_file.write_bytes(b"x" * (6 * 1024 * 1024))

        assert "does not exist" in tools_module.read_file(str(temp_dir / "missing.txt"))
        assert "is not a file" in tools_module.read_file(str(temp_dir))
        assert "too large" in tools_module.read_file(str(large_file))

        result = tools_module.read_file(str(text_file))

        assert "Content of 'latin1.txt'" in result
        assert "citta" in result

    def test_write_file_creates_parent_directories(self, tmp_path: pytest.PathLike) -> None:
        target = tmp_path / "write" / "nested" / "demo.txt"

        result = tools_module.write_file(str(target), "hello")

        assert target.read_text(encoding="utf-8") == "hello"
        assert "Successfully wrote" in result
