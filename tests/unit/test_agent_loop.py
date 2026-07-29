"""Unit tests for src/orchestration/agent_loop.py."""

from __future__ import annotations

import asyncio
import json
from threading import Event

import pytest

from src.orchestration import agent_loop as loop_module

pytest.importorskip("pyautogui")
pytest.importorskip("pywinauto")


class _FunctionCall:
    def __init__(self, name: str, args: dict[str, object]) -> None:
        self.name = name
        self.args = args


class _AuditCollector:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def record_event(self, event_type: str, **payload: object) -> None:
        self.events.append((event_type, dict(payload)))


@pytest.fixture(autouse=True)
def fast_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loop_module.config, "max_loop_turns", 3)
    monkeypatch.setattr(loop_module.config, "max_repeated_actions", 2)
    monkeypatch.setattr(loop_module.config, "completion_evidence_min_chars", 12)
    monkeypatch.setattr(loop_module.config, "tool_argument_max_chars", 1024)
    monkeypatch.setattr(loop_module.config, "permission_tier", "interact")
    monkeypatch.setattr(loop_module.config, "supports_native_desktop", lambda: True)
    monkeypatch.setattr(loop_module.time, "sleep", lambda _seconds: None)


class TestHelpers:
    def test_is_function_call_detects_supported_shape(self) -> None:
        response = _FunctionCall("click", {"element_id": "123"})

        assert loop_module._is_function_call(response) is True
        assert loop_module._is_function_call(object()) is False

    def test_imprecise_coordinate_mouse_protocol_is_not_exposed(self) -> None:
        tools = loop_module._build_available_tools()

        assert "move_mouse" not in tools
        assert "verify_mouse_position" not in tools
        assert "confirm_mouse_position" not in tools

    def test_task_timed_out_uses_wall_clock_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loop_module.config, "task_timeout", 10)
        monkeypatch.setattr(loop_module.time, "monotonic", lambda: 25.0)

        assert loop_module._task_timed_out(0.0) is True

    @pytest.mark.parametrize(
        ("result", "marker"),
        [
            ("SUCCESS: saved", "✅"),
            ("BLOCKED: permission", "⛔"),
            ("CANCELLED: operator", "⚠️"),
            ("FAILED: exhausted", "❌"),
        ],
    )
    def test_terminal_status_marker_matches_outcome(self, result: str, marker: str) -> None:
        assert loop_module._result_status_message(result).startswith(marker)

    def test_run_agent_loop_delegates_to_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            loop_module,
            "_execute_agent_task",
            lambda command, status_callback=None, cancel_event=None: f"ran:{command}",
        )

        assert loop_module.run_agent_loop("hello") == "ran:hello"

    def test_run_agent_loop_rejects_oversized_cli_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(loop_module.config, "command_max_chars", 4)

        assert loop_module.run_agent_loop("12345").startswith("FAILED")

    def test_tool_registry_obeys_permission_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loop_module.config, "permission_tier", "observe")

        observe_tools = loop_module._build_available_tools()

        assert "read_file" in observe_tools
        assert "click" not in observe_tools
        assert "run_shell_command" not in observe_tools

        monkeypatch.setattr(loop_module.config, "permission_tier", "system")
        system_tools = loop_module._build_available_tools()
        assert "click" in system_tools
        assert "run_shell_command" in system_tools

    def test_remote_runtime_exposes_dom_tools_without_desktop_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(loop_module.config, "permission_tier", "interact")
        monkeypatch.setattr(loop_module.config, "supports_native_desktop", lambda: False)
        monkeypatch.setattr(loop_module.config, "uses_remote_selenium", lambda: True)

        tools = loop_module._build_available_tools()

        assert "browser_find_and_click" in tools
        assert "browser_navigate" in tools
        assert "open_url" not in tools
        assert "click" not in tools
        assert "take_screenshot" not in tools


class TestExecuteAgentTask:
    def test_cancellation_before_first_turn_returns_cancelled(self) -> None:
        event = Event()
        event.set()

        result = loop_module._execute_agent_task("cmd", cancel_event=event)

        assert result.startswith("CANCELLED")
        assert event.is_set() is False

    def test_grounded_initial_state_can_finish_successfully(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logs: list[str] = []
        audit = _AuditCollector()
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(
            loop_module,
            "get_multimodal_context",
            lambda: (object(), "Window: Editor | Status: Ready"),
        )
        monkeypatch.setattr(loop_module, "audit_logger", audit)
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall(
                "finish_task",
                {
                    "outcome": "completed",
                    "summary": "Editor is ready",
                    "evidence": 'Current UI label reads "Status: Ready".',
                },
            ),
        )

        result = loop_module._execute_agent_task("cmd", status_callback=logs.append)

        assert result == "SUCCESS: Editor is ready"
        assert any("TASK COMPLETED" in entry for entry in logs)
        assert [event[0] for event in audit.events].count("task_completed") == 1
        assert [event[0] for event in audit.events].count("task_succeeded") == 1

    def test_blocker_is_not_reported_as_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module.config, "permission_tier", "observe")
        monkeypatch.setattr(
            loop_module, "get_multimodal_context", lambda: (object(), "Protected settings")
        )
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall(
                "finish_task",
                {
                    "outcome": "blocked",
                    "summary": "The configured tier excludes this action",
                    "evidence": "Permission tier observe does not expose the click tool.",
                },
            ),
        )

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("BLOCKED:")
        assert "SUCCESS" not in result

    def test_generic_completion_evidence_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        audit = _AuditCollector()
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module, "audit_logger", audit)
        monkeypatch.setattr(
            loop_module, "get_multimodal_context", lambda: (object(), "Window: Editor")
        )
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall(
                "finish_task",
                {"outcome": "completed", "summary": "done", "evidence": "task completed"},
            ),
        )

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FAILED")
        assert "completion_rejected" in [event[0] for event in audit.events]
        assert "task_succeeded" not in [event[0] for event in audit.events]

    def test_audit_logs_verified_tool_dispatch_and_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audit = _AuditCollector()
        contexts = iter(
            [
                (object(), "Window: Editor | Button: Save"),
                (object(), "Window: Editor | Status: Changes saved"),
            ]
        )
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 2)
        monkeypatch.setattr(loop_module, "audit_logger", audit)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: next(contexts))
        monkeypatch.setattr(loop_module.action_tools, "click", lambda element_id: "Clicked Save.")
        responses = iter(
            [
                _FunctionCall("click", {"element_id": "button-1"}),
                _FunctionCall(
                    "finish_task",
                    {
                        "outcome": "completed",
                        "summary": "Document saved",
                        "evidence": 'Current UI label reads "Status: Changes saved".',
                    },
                ),
            ]
        )
        monkeypatch.setattr(loop_module, "decide_next_action", lambda **kwargs: next(responses))

        result = loop_module._execute_agent_task("cmd")

        assert result == "SUCCESS: Document saved"
        event_names = [event[0] for event in audit.events]
        assert "tool_dispatched" in event_names
        assert "tool_result" in event_names
        assert "task_completed" in event_names
        assert "task_succeeded" in event_names

    def test_audit_events_do_not_persist_arbitrary_tool_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audit = _AuditCollector()
        confidential = "customer-private-value-that-is-not-a-token"
        contexts = iter(
            [
                (object(), "Window: Editor | Button: Save"),
                (object(), "Window: Editor | Status: Saved"),
            ]
        )
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 2)
        monkeypatch.setattr(loop_module, "audit_logger", audit)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: next(contexts))
        monkeypatch.setattr(loop_module.action_tools, "click", lambda element_id: confidential)
        responses = iter(
            [
                _FunctionCall("click", {"element_id": confidential}),
                _FunctionCall(
                    "finish_task",
                    {
                        "outcome": "completed",
                        "summary": "Document saved",
                        "evidence": 'Current UI label reads "Status: Saved".',
                    },
                ),
            ]
        )
        monkeypatch.setattr(loop_module, "decide_next_action", lambda **kwargs: next(responses))

        assert loop_module._execute_agent_task("cmd") == "SUCCESS: Document saved"
        assert confidential not in str(audit.events)

    def test_invalid_reasoning_response_eventually_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def invalid_response(**kwargs: object) -> str:
            nonlocal calls
            calls += 1
            return "text only"

        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))
        monkeypatch.setattr(loop_module, "decide_next_action", invalid_response)

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FAILED")
        assert calls == 1

    def test_terminal_reasoning_error_does_not_multiply_retry_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def unavailable_runtime(**kwargs: object) -> loop_module.ReasoningFailure:
            nonlocal calls
            calls += 1
            return loop_module.ReasoningFailure(
                code="local_runtime_unavailable",
                message="The local model runtime is unavailable.",
                terminal=True,
            )

        monkeypatch.setattr(loop_module.config, "max_loop_turns", 10)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))
        monkeypatch.setattr(loop_module, "decide_next_action", unavailable_runtime)

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FAILED: The reasoning service")
        assert calls == 1

    def test_perception_error_is_recorded_and_task_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(
            loop_module,
            "get_multimodal_context",
            lambda: (_ for _ in ()).throw(RuntimeError("screen failed")),
        )

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FAILED")

    def test_task_timeout_stops_execution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clock = iter([0.0, 0.0, 10.0])
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 3)
        monkeypatch.setattr(loop_module.config, "task_timeout", 5)
        monkeypatch.setattr(loop_module.time, "monotonic", lambda: next(clock))
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FAILED: Task timed out")

    def test_unknown_tool_generates_failure_observation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall("missing_tool", {}),
        )

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FAILED")

    def test_tool_argument_contract_is_enforced_before_dispatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def typed_click(element_id: str) -> str:
            calls.append(element_id)
            return "clicked"

        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "ui-tree"))
        monkeypatch.setattr(loop_module.action_tools, "click", typed_click)
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall("click", {"wrong": "arg"}),
        )

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FAILED")
        assert calls == []

    def test_structured_tool_failure_is_classified_before_observation_truncation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audit = _AuditCollector()

        def failed_command(command: str) -> str:
            del command
            return json.dumps(
                {
                    "stdout": "x" * 2_000,
                    "stderr": "command failed",
                    "return_code": 1,
                }
            )

        monkeypatch.setattr(loop_module.config, "permission_tier", "system")
        monkeypatch.setattr(loop_module.config, "max_loop_turns", 1)
        monkeypatch.setattr(loop_module.config, "observation_max_chars", 80)
        monkeypatch.setattr(loop_module, "audit_logger", audit)
        monkeypatch.setattr(loop_module, "get_multimodal_context", lambda: (object(), "Terminal"))
        monkeypatch.setattr(loop_module.action_tools, "run_shell_command", failed_command)
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall(
                "run_shell_command",
                {"command": "approved.exe"},
            ),
        )

        result = loop_module._execute_agent_task("run approved diagnostic")

        assert result.startswith("FAILED")
        tool_results = [payload for event, payload in audit.events if event == "tool_result"]
        assert tool_results[0]["observation_is_error"] is True

    def test_repeated_action_against_unchanged_state_is_bounded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def typed_click(element_id: str) -> str:
            calls.append(element_id)
            return "Browser element clicked successfully."

        monkeypatch.setattr(loop_module.config, "max_loop_turns", 3)
        monkeypatch.setattr(loop_module.config, "max_repeated_actions", 2)
        monkeypatch.setattr(
            loop_module,
            "get_multimodal_context",
            lambda: (object(), "Window: Editor | Button: Save"),
        )
        monkeypatch.setattr(loop_module.action_tools, "click", typed_click)
        monkeypatch.setattr(
            loop_module,
            "decide_next_action",
            lambda **kwargs: _FunctionCall("click", {"element_id": "save"}),
        )

        result = loop_module._execute_agent_task("cmd")

        assert result.startswith("FAILED")
        assert calls == ["save", "save"]

    def test_unchanged_mutation_can_be_verified_with_read_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        responses = iter(
            [
                _FunctionCall("click", {"element_id": "save"}),
                _FunctionCall(
                    "finish_task",
                    {
                        "outcome": "completed",
                        "summary": "Document saved",
                        "evidence": "Clicked Save successfully.",
                    },
                ),
                _FunctionCall("get_text", {"element_id": "status"}),
                _FunctionCall(
                    "finish_task",
                    {
                        "outcome": "completed",
                        "summary": "Document saved",
                        "evidence": "Status text reads: Document saved",
                    },
                ),
            ]
        )

        monkeypatch.setattr(loop_module.config, "max_loop_turns", 4)
        monkeypatch.setattr(
            loop_module,
            "get_multimodal_context",
            lambda: (object(), "Window: Editor | Button: Save"),
        )
        monkeypatch.setattr(loop_module.action_tools, "click", lambda element_id: "Clicked Save.")
        monkeypatch.setattr(
            loop_module.action_tools,
            "get_text",
            lambda element_id: "Status text reads: Document saved",
        )
        monkeypatch.setattr(loop_module, "decide_next_action", lambda **kwargs: next(responses))

        result = loop_module._execute_agent_task("cmd")

        assert result == "SUCCESS: Document saved"


@pytest.mark.asyncio
async def test_async_agent_loop_processes_command_and_reports_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_queue: asyncio.Queue[str] = asyncio.Queue()
    status_queue: asyncio.Queue[str] = asyncio.Queue()
    cancel_event = Event()

    monkeypatch.setattr(
        loop_module,
        "_execute_agent_task",
        lambda command, callback, event: "SUCCESS: Task completed",
    )

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

    assert any("Received an operator command" in message for message in drained_messages)
    assert any("Ready for next command" in message for message in drained_messages)
