"""Unit tests for src/orchestration/agent_loop.py."""

from __future__ import annotations

import asyncio
from threading import Event

import pytest

pytest.importorskip("pyautogui")
pytest.importorskip("pywinauto")

from src.orchestration import agent_loop as loop_module


class _FunctionCall:
    def __init__(self, name: str, args: dict[str, object]) -> None:
        self.name = name
        self.args = args


@pytest.fixture(autouse=True)
def fast_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loop_module.config, "max_loop_turns", 3)
    monkeypatch.setattr(loop_module.config, "max_mouse_positioning_attempts", 2)
    monkeypatch.setattr(loop_module.time, "sleep", lambda _seconds: None)


class TestHelpers:
    def test_is_function_call_detects_supported_shape(self) -> None:
        response = _FunctionCall("click", {"element_id": "123"})

        assert loop_module._is_function_call(response) is True
        assert loop_module._is_function_call(object()) is False

    def test_mouse_positioning_tool_detection(self) -> None:
        assert loop_module._is_mouse_positioning_tool("move_mouse") is True
        assert loop_module._is_mouse_positioning_tool("click") is False

    def test_run_agent_loop_delegates_to_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loop_module, "_execute_agent_task", lambda command, status_callback=None, cancel_event=None: f"ran:{command}")

        assert loop_module.run_agent_loop("hello") == "ran:hello"


class TestExecuteAgentTask:
    def test_cancellation_before_first_turn_returns_cancelled(self) -> None:
        event = Event()
        event.set()

        result = loop_module._execute_agent_task("cmd", cancel_event=event)

        assert result.startswith("CANCELLATO")
        assert event.is_set() is False

    def test_finish_task_returns_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logs: list[str] = []
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall("finish_task", {"summary": "done"}),
        )

        result = loop_module._execute_agent_task("cmd", status_callback=logs.append)

        assert result == "SUCCESSO: Task completato"
        assert any("TASK COMPLETATO" in entry for entry in logs)

    def test_invalid_reasoning_response_eventually_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))
        monkeypatch.setattr(loop_module, "decide_next_action", lambda **kwargs: "solo testo")

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FALLITO")

    def test_perception_error_is_recorded_and_task_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (_ for _ in ()).throw(RuntimeError("screen failed")))

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FALLITO")

    def test_unknown_tool_generates_failure_observation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall("missing_tool", {}),
        )

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FALLITO")

    def test_tool_argument_type_error_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))
        monkeypatch.setattr(loop_module.action_tools, "click", lambda element_id: "clicked")
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall("click", {"wrong": "arg"}),
        )

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FALLITO")

    def test_mouse_positioning_branch_is_exercised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        responses = iter(
            [
                _FunctionCall("move_mouse", {"x": 1, "y": 2}),
                _FunctionCall("confirm_mouse_position", {}),
                _FunctionCall("finish_task", {"summary": "ok"}),
            ]
        )
        logs: list[str] = []

        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))
        monkeypatch.setattr(loop_module.action_tools, "move_mouse", lambda x, y: "moved")
        monkeypatch.setattr(loop_module.action_tools, "confirm_mouse_position", lambda: "confirmed")
        monkeypatch.setattr(loop_module, "decide_next_action", lambda **kwargs: next(responses))

        result = loop_module._execute_agent_task("cmd", status_callback=logs.append)

        assert result == "SUCCESSO: Task completato"
        assert any("MINI-LOOP MOUSE" in entry for entry in logs)


@pytest.mark.asyncio
async def test_async_agent_loop_processes_command_and_reports_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_queue: asyncio.Queue[str] = asyncio.Queue()
    status_queue: asyncio.Queue[str] = asyncio.Queue()
    cancel_event = Event()

    monkeypatch.setattr(loop_module, "_execute_agent_task", lambda command, callback, event: "SUCCESSO: Task completato")

    task = asyncio.create_task(loop_module.agent_loop(command_queue, status_queue, cancel_event))

    initial_message = await asyncio.wait_for(status_queue.get(), timeout=1)
    status_queue.task_done()

    await command_queue.put("do something")
    await asyncio.wait_for(command_queue.join(), timeout=2)
    await asyncio.sleep(0.05)

    drained_messages: list[str] = [initial_message]
    while not status_queue.empty():
        drained_messages.append(await status_queue.get())
        status_queue.task_done()

    task.cancel()
    await task

    assert any("Received command" in message for message in drained_messages)
    assert any("Ready for next command" in message for message in drained_messages)