"""Deterministic end-to-end contract for the browser-only agent runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

import pytest

from src.action import browser_tools
from src.audit import AuditLogger
from src.orchestration import agent_loop


@dataclass(frozen=True)
class _ScriptedFunctionCall:
    name: str
    args: dict[str, object]


class _RecordingElement:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def click(self) -> None:
        self.calls.append("click")

    def clear(self) -> None:
        self.calls.append("clear")

    def send_keys(self, value: object) -> None:
        self.calls.append(("send_keys", value))


class _ImmediateWait:
    def __init__(self, _driver: object, _timeout: float, element: _RecordingElement) -> None:
        self._element = element

    def until(self, _condition: object) -> _RecordingElement:
        return self._element


class _FakeChromeOptions:
    pass


class _FakeWebDriverModule:
    def __init__(self, driver: object) -> None:
        self._driver = driver
        self.remote_calls: list[tuple[str, object]] = []

    def ChromeOptions(self) -> _FakeChromeOptions:
        return _FakeChromeOptions()

    def Remote(
        self,
        *,
        command_executor: str,
        options: object,
    ) -> object:
        self.remote_calls.append((command_executor, options))
        return self._driver


def test_remote_browser_task_crosses_policy_action_feedback_and_audit_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise one complete remote-Selenium ReAct task without external services."""

    private_command = "Search the private account record command-81f726"
    private_query = "customer-record-query-59d2"
    private_text = "Bearer private-tool-value-4e1d5cc07b2a"
    enter_key = "<RETURN>"
    audit_directory = TemporaryDirectory(prefix="djenis-agent-audit-")
    audit_path = Path(audit_directory.name) / "agent-audit.jsonl"
    audit_max_bytes = 16 * 1024
    element = _RecordingElement()
    driver = SimpleNamespace(
        title="Scripted remote browser",
        switch_to=SimpleNamespace(active_element=element),
    )
    webdriver = _FakeWebDriverModule(driver)
    reasoning_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(agent_loop.config, "permission_tier", "interact")
    monkeypatch.setattr(agent_loop.config, "max_loop_turns", 2)
    monkeypatch.setattr(agent_loop.config, "observation_max_chars", 128)
    monkeypatch.setattr(agent_loop.config, "selenium_remote_url", "http://selenium.test/wd/hub")
    monkeypatch.setattr(agent_loop.config, "supports_native_desktop", lambda: False)
    monkeypatch.setattr(agent_loop.config, "uses_remote_selenium", lambda: True)
    monkeypatch.setattr(
        agent_loop,
        "get_multimodal_context",
        lambda: (object(), "remote browser DOM snapshot"),
    )
    monkeypatch.setattr(
        agent_loop,
        "audit_logger",
        AuditLogger(
            enabled=True,
            file_path=str(audit_path),
            max_bytes=audit_max_bytes,
        ),
    )

    monkeypatch.setattr(browser_tools, "SELENIUM_AVAILABLE", True)
    monkeypatch.setattr(browser_tools, "_driver", None)
    monkeypatch.setattr(browser_tools, "webdriver", webdriver)
    monkeypatch.setattr(browser_tools, "WebDriverException", RuntimeError)
    monkeypatch.setattr(
        browser_tools,
        "By",
        SimpleNamespace(NAME="name", ID="id", XPATH="xpath"),
    )
    monkeypatch.setattr(
        browser_tools,
        "EC",
        SimpleNamespace(element_to_be_clickable=lambda locator: locator),
    )
    monkeypatch.setattr(browser_tools, "Keys", SimpleNamespace(RETURN=enter_key))
    monkeypatch.setattr(
        browser_tools,
        "WebDriverWait",
        lambda selected_driver, timeout: _ImmediateWait(
            selected_driver,
            timeout,
            element,
        ),
    )

    scripted_calls = iter(
        (
            _ScriptedFunctionCall(
                "browser_find_and_type",
                {
                    "query": private_query,
                    "text": private_text,
                    "press_enter": True,
                },
            ),
            _ScriptedFunctionCall("finish_task", {"summary": "browser form submitted"}),
        )
    )

    def scripted_llm_decision(**request: Any) -> _ScriptedFunctionCall:
        reasoning_calls.append(
            {
                "history": list(request["history"]),
                "tool_names": {tool.__name__ for tool in request["available_tools"]},
            }
        )
        return next(scripted_calls)

    monkeypatch.setattr(agent_loop, "decide_next_action", scripted_llm_decision)

    result = agent_loop._execute_agent_task(
        private_command,
        status_callback=lambda _message: None,
    )

    assert result == "SUCCESS: Task completed"
    assert len(reasoning_calls) == 2
    assert "browser_find_and_type" in reasoning_calls[0]["tool_names"]
    assert "run_shell_command" not in reasoning_calls[0]["tool_names"]
    assert "take_screenshot" not in reasoning_calls[0]["tool_names"]
    assert len(webdriver.remote_calls) == 1
    assert webdriver.remote_calls[0][0] == "http://selenium.test/wd/hub"
    assert isinstance(webdriver.remote_calls[0][1], _FakeChromeOptions)
    assert element.calls == [
        "click",
        "clear",
        ("send_keys", private_text),
        ("send_keys", enter_key),
    ]
    assert any(
        entry == "OBSERVATION: Pressed Enter in the active browser element."
        for entry in reasoning_calls[1]["history"]
    )
    assert private_text not in "\n".join(reasoning_calls[1]["history"])

    audit_lines = audit_path.read_text(encoding="utf-8").splitlines()
    audit_events = [json.loads(line) for line in audit_lines]

    assert [event["event_type"] for event in audit_events] == [
        "task_started",
        "turn_started",
        "tool_dispatched",
        "tool_result",
        "turn_started",
        "tool_dispatched",
        "task_completed",
        "task_succeeded",
    ]
    assert audit_path.stat().st_size <= audit_max_bytes
    assert all(len(line.encode("utf-8")) <= audit_max_bytes for line in audit_lines)

    serialized_audit = audit_path.read_text(encoding="utf-8")
    for private_value in (private_command, private_query, private_text):
        assert private_value not in serialized_audit

    browser_dispatch = audit_events[2]["payload"]
    assert browser_dispatch["tool_name"] == "browser_find_and_type"
    assert browser_dispatch["tool_arg_names"] == ["press_enter", "query", "text"]
    assert browser_dispatch["tool_arg_lengths"] == {
        "press_enter": len(str(True)),
        "query": len(private_query),
        "text": len(private_text),
    }
    audit_directory.cleanup()
