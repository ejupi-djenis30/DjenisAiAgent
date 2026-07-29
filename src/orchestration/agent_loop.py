"""
Agent Loop Module

This module contains the main orchestration loop that coordinates perception,
reasoning, and action execution using the ReAct (Reason+Act) paradigm.

The agent loop now operates in two modes:
1. Async mode: Consumes commands from asyncio.Queue and sends status updates
2. Sync mode: Traditional synchronous execution for CLI compatibility
"""

import asyncio
import functools
import logging
import time
from collections.abc import Callable, Mapping
from threading import Event
from typing import Any, Protocol, TypeGuard, cast
from uuid import uuid4

from src.action import tools as action_tools
from src.audit import audit_logger
from src.config import config
from src.orchestration.execution_guard import (
    ExecutionGuard,
    observation_is_error,
    validate_tool_arguments,
)
from src.perception.screen_capture import get_multimodal_context
from src.reasoning.local_llm import (
    SYSTEM_PROMPT_FINGERPRINT,
    ReasoningFailure,
    decide_next_action,
)
from src.redaction import bounded_text, safe_preview

logger = logging.getLogger(__name__)

_CONTENT_ARGUMENT_NAMES = frozenset(
    {
        "command",
        "content",
        "keys",
        "query",
        "search_term",
        "text",
        "url",
    }
)


class FunctionCallLike(Protocol):
    """Protocol describing a provider-neutral local model function call."""

    name: str
    args: Mapping[str, Any]


def _is_function_call(response: Any) -> TypeGuard[FunctionCallLike]:
    """Return True when the response exposes the FunctionCall interface."""

    if not hasattr(response, "name") or not hasattr(response, "args"):
        return False

    name = response.name
    args = response.args
    return isinstance(name, str) and isinstance(args, Mapping)


def _task_timed_out(started_at: float) -> bool:
    """Return True when the wall-clock deadline for the task has been reached."""

    return (time.monotonic() - started_at) >= config.task_timeout


def _build_available_tools() -> dict[str, Callable[..., str]]:
    """Build a capability registry that matches the active runtime and operator tier."""

    tools: dict[str, Callable[..., str]] = {
        "finish_task": action_tools.finish_task,
        "browser_runtime_status": action_tools.browser_runtime_status,
        "browser_media_capability": action_tools.browser_media_capability,
        "list_files": action_tools.list_files,
        "read_file": action_tools.read_file,
    }

    if config.permits("interact"):
        if config.supports_native_desktop():
            tools["open_url"] = action_tools.open_url
            tools.update(
                {
                    "element_id": action_tools.element_id,
                    "element_id_fast": action_tools.element_id_fast,
                    "click": action_tools.click,
                    "double_click": action_tools.double_click,
                    "right_click": action_tools.right_click,
                    "type_text": action_tools.type_text,
                    "get_text": action_tools.get_text,
                    "scroll": action_tools.scroll,
                    "press_key_repeat": action_tools.press_key_repeat,
                    "press_keys": action_tools.press_keys,
                    "hotkey": action_tools.hotkey,
                    "wait_seconds": action_tools.wait_seconds,
                    "maximize_window": action_tools.maximize_window,
                    "switch_window": action_tools.switch_window,
                    "copy_to_clipboard": action_tools.copy_to_clipboard,
                    "paste_from_clipboard": action_tools.paste_from_clipboard,
                    "get_clipboard_text": action_tools.get_clipboard_text,
                    "set_clipboard_text": action_tools.set_clipboard_text,
                    "read_clipboard": action_tools.read_clipboard,
                    "browser_search": action_tools.browser_search,
                }
            )

        if config.uses_remote_selenium() or config.supports_native_desktop():
            browser = action_tools.browser_tools
            tools.update(
                {
                    "browser_find_and_click": browser.browser_find_and_click,
                    "browser_find_and_type": browser.browser_find_and_type,
                    "browser_type_text": browser.browser_type_text,
                    "browser_press_enter": browser.browser_press_enter,
                    "browser_get_current_url": browser.browser_get_current_url,
                    "browser_navigate": browser.browser_navigate,
                }
            )

    if config.permits("system"):
        tools.update(
            {
                "run_shell_command": action_tools.run_shell_command,
                "start_application": action_tools.start_application,
                "open_file": action_tools.open_file,
                "take_screenshot": action_tools.take_screenshot,
                "write_file": action_tools.write_file,
                "close_window": action_tools.close_window,
            }
        )

    return tools


def run_agent_loop(user_command: str) -> str:
    """
    Execute the main ReAct agent loop to fulfill a user command (synchronous version).

    This is the synchronous wrapper for CLI mode compatibility.
    For web mode, use agent_loop() instead which is fully asynchronous.

    This function implements the core ReAct cycle:
    1. Observe: Capture screen state and UI structure
    2. Reason: Ask the configured local model for one tool call
    3. Act: Execute the chosen action
    4. Verify: Record observation and update history

    The loop continues until the task is completed or max turns is reached.

    Args:
        user_command: The user's natural language command to execute.

    Returns:
        str: Final status message indicating success or failure.
    """
    if len(user_command) > config.command_max_chars:
        return f"FAILED: Command exceeds the {config.command_max_chars}-character limit"
    return _execute_agent_task(user_command, status_callback=print)


async def agent_loop(
    command_queue: asyncio.Queue, status_queue: asyncio.Queue, cancel_event: Event
):
    """
    Asynchronous agent loop that continuously processes commands from a queue.

    This is the main entry point for web mode. It runs indefinitely, consuming
    commands from the command_queue and sending status updates to the status_queue.

    Architecture:
        WebSocket -> command_queue -> agent_loop -> status_queue -> broadcaster -> WebSocket

    Args:
    command_queue: AsyncIO queue containing user commands to process
    status_queue: AsyncIO queue for sending status updates to web clients
    cancel_event: Thread-safe flag used to interrupt the current task

    The loop will:
    1. Wait for a command from the queue (blocking)
    2. Execute the full ReAct cycle for that command
    3. Send status updates throughout execution
    4. Mark the task as done when complete
    5. Repeat indefinitely
    """
    logger.info("Agent loop started in async queue-driven mode")
    await status_queue.put("✅ Agent loop initialized and ready for commands")
    event_loop = asyncio.get_running_loop()

    while True:
        try:
            # Block until a command is available
            user_command = await command_queue.get()
            cancel_event.clear()
            logger.info("Agent loop received a command (%d characters)", len(user_command))
            await status_queue.put(
                f"Received an operator command ({len(user_command)} characters)."
            )

            try:
                # Run the agent task (uses run_in_executor for sync code)
                def sync_status_callback(message: str) -> None:
                    """Bridge worker-thread status updates into the event loop."""

                    future = asyncio.run_coroutine_threadsafe(status_queue.put(message), event_loop)
                    future.result()

                executor_fn = functools.partial(
                    _execute_agent_task,
                    user_command,
                    status_callback=sync_status_callback,
                    cancel_event=cancel_event,
                )
                result = await event_loop.run_in_executor(None, executor_fn)
                logger.info("Command completed: %s", safe_preview(result))
                await status_queue.put(_result_status_message(result))

            except Exception as e:
                error_msg = f"❌ Error executing command: {e!s}"
                logger.error(error_msg, exc_info=True)
                await status_queue.put(error_msg)

            finally:
                # Mark task as complete
                command_queue.task_done()
                await status_queue.put("🔄 Ready for next command")

        except asyncio.CancelledError:
            logger.info("Agent loop cancelled, shutting down gracefully")
            await status_queue.put("⚠️ Agent loop shutting down")
            break
        except Exception as e:
            logger.error(f"Unexpected error in agent loop: {e}", exc_info=True)
            await status_queue.put(f"❌ Critical error: {e!s}")


def _reasoning_failure_is_terminal(response: Any) -> bool:
    """Return True when local inference already exhausted safe recovery."""

    if isinstance(response, ReasoningFailure):
        return response.terminal

    # Preserve compatibility with simple test doubles while production uses typed failures.
    normalized = str(response).casefold()
    terminal_markers = (
        "configuration error:",
        "no tools are available",
        "local model runtime failed after",
        "local model response exceeded",
        "local model endpoint returned prohibited",
        "unexpected local model error:",
        "cancelled before the local model request",
        "cancelled while waiting to retry the local model",
    )
    return any(marker in normalized for marker in terminal_markers)


def _permission_boundary(observation: str) -> bool:
    """Detect a tool result that represents a non-recoverable permission boundary."""

    normalized = str(observation).casefold()
    return any(
        marker in normalized
        for marker in (
            "permission tier",
            "permission denied",
            "not permitted",
            "dangerous actions are disabled",
            "outside the allowed paths",
            "not in the allowed",
        )
    )


def _argument_summary(arguments: Mapping[str, Any]) -> str:
    """Describe tool arguments without retaining arbitrary operator or page content."""

    summarized: dict[str, Any] = {}
    for name, value in arguments.items():
        if name in _CONTENT_ARGUMENT_NAMES:
            if isinstance(value, str):
                summarized[name] = f"<redacted string; {len(value)} characters>"
            elif isinstance(value, list):
                summarized[name] = f"<redacted list; {len(value)} items>"
            else:
                summarized[name] = f"<redacted {type(value).__name__}>"
        else:
            summarized[name] = value
    return safe_preview(summarized)


def _result_status_message(result: str) -> str:
    """Render one terminal result without displaying failures as successes."""

    if result.startswith("SUCCESS:"):
        return f"✅ {result}"
    if result.startswith("BLOCKED:"):
        return f"⛔ {result}"
    if result.startswith("CANCELLED:"):
        return f"⚠️ {result}"
    return f"❌ {result}"


def _execute_agent_task(
    user_command: str,
    status_callback: Callable[[str], None] | None = None,
    cancel_event: Event | None = None,
) -> str:
    """Execute one bounded task with host-enforced action and completion contracts."""

    def cancelled() -> bool:
        return bool(cancel_event and cancel_event.is_set())

    def log_status(message: str) -> None:
        if status_callback:
            status_callback(message)
        else:
            print(message)

    task_started_at = time.monotonic()
    task_id = uuid4().hex
    history: list[str] = []
    max_turns = max(1, config.max_loop_turns)
    available_tools = _build_available_tools()
    guard = ExecutionGuard(
        max_repeated_actions=config.max_repeated_actions,
        evidence_min_chars=config.completion_evidence_min_chars,
        objective=user_command,
        trusted_context=(
            f"permission tier {config.permission_tier}; runtime mode {config.runtime_mode}; "
            f"available tools: {', '.join(sorted(available_tools))}"
        ),
        permission_tier=config.permission_tier,
        available_tool_names=set(available_tools),
    )

    if not user_command.strip():
        return "FAILED: Command cannot be empty"
    if len(user_command) > config.command_max_chars:
        return f"FAILED: Command exceeds the {config.command_max_chars}-character limit"

    audit_logger.record_event(
        "task_started",
        task_id=task_id,
        user_command_length=len(user_command),
        max_turns=max_turns,
        task_timeout=config.task_timeout,
        max_repeated_actions=config.max_repeated_actions,
        model_name=config.local_llm_model,
        model_backend=config.local_llm_backend,
        system_prompt_fingerprint=SYSTEM_PROMPT_FINGERPRINT,
        available_tool_count=len(available_tools),
    )

    logger.info("Starting agent loop for a command (%d characters)", len(user_command))
    logger.info("Maximum turns: %d", max_turns)
    log_status("\n" + "=" * 80)
    log_status("Agent started the queued operator task.")
    log_status("=" * 80 + "\n")

    for turn in range(1, max_turns + 1):
        if _task_timed_out(task_started_at):
            audit_logger.record_event("task_timeout", task_id=task_id, turn=turn, phase="pre_turn")
            return f"FAILED: Task timed out after {config.task_timeout} seconds"
        if cancelled():
            if cancel_event:
                cancel_event.clear()
            audit_logger.record_event(
                "task_cancelled", task_id=task_id, turn=turn, phase="pre_turn"
            )
            return "CANCELLED: Task interrupted by the operator"

        audit_logger.record_event(
            "turn_started",
            task_id=task_id,
            turn=turn,
            history_size=len(history),
        )
        log_status(f"\n--- TURN {turn}/{max_turns} ---\n")

        perception_started_at = time.perf_counter()
        try:
            screenshot, ui_tree = get_multimodal_context()
            guard.note_perception(screenshot, ui_tree)
            log_status("PERCEPTION: Fresh screenshot and structural UI state captured.")
            audit_logger.record_event(
                "perception_captured",
                task_id=task_id,
                turn=turn,
                perception_index=guard.perception_index,
                ui_tree_length=len(ui_tree),
                duration_ms=round((time.perf_counter() - perception_started_at) * 1000, 2),
            )
        except Exception as exc:
            error_msg = f"Perception error: {exc!s}"
            logger.error(error_msg, exc_info=True)
            log_status(f"ERROR: {error_msg}")
            history.append(f"TURN {turn} PERCEPTION_ERROR: {safe_preview(error_msg)}")
            audit_logger.record_event(
                "perception_error",
                task_id=task_id,
                turn=turn,
                error_type=type(exc).__name__,
                duration_ms=round((time.perf_counter() - perception_started_at) * 1000, 2),
            )
            continue

        if _task_timed_out(task_started_at):
            audit_logger.record_event(
                "task_timeout", task_id=task_id, turn=turn, phase="perception"
            )
            return f"FAILED: Task timed out after {config.task_timeout} seconds"
        if cancelled():
            if cancel_event:
                cancel_event.clear()
            audit_logger.record_event(
                "task_cancelled", task_id=task_id, turn=turn, phase="perception"
            )
            return "CANCELLED: Task interrupted by the operator"

        reasoning_started_at = time.perf_counter()
        try:
            response = decide_next_action(
                screenshot_image=screenshot,
                ui_tree=ui_tree,
                user_command=user_command,
                history=history,
                available_tools=list(available_tools.values()),
                cancel_event=cancel_event,
                runtime_context=guard.prompt_context(),
            )
        except Exception as exc:
            logger.error("Reasoning error: %s", exc, exc_info=True)
            history.append(f"TURN {turn} REASONING_ERROR: {safe_preview(type(exc).__name__)}")
            audit_logger.record_event(
                "reasoning_error",
                task_id=task_id,
                turn=turn,
                error_type=type(exc).__name__,
                duration_ms=round((time.perf_counter() - reasoning_started_at) * 1000, 2),
            )
            continue

        if cancelled():
            if cancel_event:
                cancel_event.clear()
            audit_logger.record_event(
                "task_cancelled", task_id=task_id, turn=turn, phase="reasoning"
            )
            return "CANCELLED: Task interrupted by the operator"

        if not _is_function_call(response):
            invalid_response_preview = safe_preview(response or "<empty>")
            logger.warning("Local model returned no valid tool call: %s", invalid_response_preview)
            history.append(f"TURN {turn} DECISION_REJECTED: {invalid_response_preview}")
            audit_logger.record_event(
                "reasoning_invalid_response",
                task_id=task_id,
                turn=turn,
                response_length=len(str(response or "")),
                failure_code=(
                    response.code if isinstance(response, ReasoningFailure) else "untyped_response"
                ),
                failure_retryable=(
                    response.retryable if isinstance(response, ReasoningFailure) else False
                ),
                terminal=_reasoning_failure_is_terminal(response),
                duration_ms=round((time.perf_counter() - reasoning_started_at) * 1000, 2),
            )
            if _reasoning_failure_is_terminal(response):
                audit_logger.record_event(
                    "task_failed", task_id=task_id, turn=turn, reason="terminal_reasoning_error"
                )
                return "FAILED: The reasoning service could not produce a safe action"
            log_status("The model decision was rejected; requesting a corrected single tool call.")
            continue

        function_call = cast(FunctionCallLike, response)
        tool_name = function_call.name
        tool_args = dict(function_call.args)
        audit_logger.record_event(
            "reasoning_decision",
            task_id=task_id,
            turn=turn,
            tool_name=tool_name,
            duration_ms=round((time.perf_counter() - reasoning_started_at) * 1000, 2),
        )
        tool_function = available_tools.get(tool_name)
        if tool_function is None:
            observation = f"TOOL CALL REJECTED: unknown or unavailable tool '{tool_name}'."
            history.append(f"TURN {turn} TOOL_REJECTED: {observation}")
            audit_logger.record_event(
                "tool_rejected", task_id=task_id, turn=turn, tool_name=tool_name, reason="unknown"
            )
            log_status(observation)
            continue

        argument_error = validate_tool_arguments(
            tool_function,
            tool_args,
            max_serialized_chars=config.tool_argument_max_chars,
        )
        if argument_error is not None:
            observation = f"TOOL CALL REJECTED: {argument_error}."
            guard.record_tool_result(
                tool_name=tool_name,
                observation=observation,
                succeeded=False,
                arguments=tool_args,
            )
            history.append(f"TURN {turn} TOOL {tool_name} RESULT failure: {observation}")
            audit_logger.record_event(
                "tool_rejected",
                task_id=task_id,
                turn=turn,
                tool_name=tool_name,
                reason="invalid_arguments",
            )
            log_status(observation)
            continue

        if tool_name == "finish_task":
            audit_logger.record_event(
                "tool_dispatched",
                task_id=task_id,
                turn=turn,
                tool_name=tool_name,
                tool_arg_names=sorted(tool_args),
                tool_arg_lengths={key: len(str(value)) for key, value in tool_args.items()},
            )
            decision = guard.evaluate_completion(
                outcome=tool_args["outcome"],
                summary=tool_args["summary"],
                evidence=tool_args["evidence"],
            )
            if decision.allowed and decision.outcome == "completed":
                summary = str(tool_args["summary"]).strip()
                evidence = str(tool_args["evidence"]).strip()
                log_status(f"TASK COMPLETED: {summary}\nEVIDENCE: {safe_preview(evidence)}")
                audit_logger.record_event(
                    "task_completed",
                    task_id=task_id,
                    turn=turn,
                    summary_length=len(summary),
                    evidence_length=len(evidence),
                    verification=decision.reason,
                )
                audit_logger.record_event("task_succeeded", task_id=task_id, turn=turn)
                logger.info("Task completion verified: %s", safe_preview(summary))
                return f"SUCCESS: {summary}"
            if decision.allowed and decision.outcome == "blocked":
                summary = str(tool_args["summary"]).strip()
                evidence = str(tool_args["evidence"]).strip()
                log_status(f"TASK BLOCKED: {summary}\nEVIDENCE: {safe_preview(evidence)}")
                audit_logger.record_event(
                    "task_blocked",
                    task_id=task_id,
                    turn=turn,
                    source="model_report",
                    summary_length=len(summary),
                    evidence_length=len(evidence),
                )
                logger.info("Task blocker accepted: %s", safe_preview(summary))
                return f"BLOCKED: {summary}"

            observation = f"COMPLETION REJECTED: {decision.reason}."
            history.append(f"TURN {turn} TOOL finish_task RESULT failure: {observation}")
            audit_logger.record_event(
                "completion_rejected",
                task_id=task_id,
                turn=turn,
                requested_outcome=str(tool_args["outcome"]),
                reason=decision.reason,
            )
            log_status(observation)
            continue

        repeated_action_error = guard.reject_repeated_action(tool_name, tool_args)
        if repeated_action_error is not None:
            guard.record_tool_result(
                tool_name=tool_name,
                observation=repeated_action_error,
                succeeded=False,
                arguments=tool_args,
            )
            history.append(f"TURN {turn} TOOL {tool_name} RESULT failure: {repeated_action_error}")
            audit_logger.record_event(
                "tool_rejected",
                task_id=task_id,
                turn=turn,
                tool_name=tool_name,
                reason="stagnation",
            )
            log_status(repeated_action_error)
            continue

        argument_summary = _argument_summary(tool_args)
        log_status(f"ACTION: {tool_name} with {argument_summary}")
        audit_logger.record_event(
            "tool_dispatched",
            task_id=task_id,
            turn=turn,
            tool_name=tool_name,
            tool_arg_names=sorted(tool_args),
            tool_arg_lengths={key: len(str(value)) for key, value in tool_args.items()},
        )

        succeeded = False
        tool_started_at = time.perf_counter()
        try:
            raw_observation = tool_function(**tool_args)
            succeeded = not observation_is_error(str(raw_observation))
            observation = bounded_text(raw_observation, config.observation_max_chars)
        except Exception as exc:
            observation = f"Error while executing '{tool_name}': {type(exc).__name__}"
            logger.error("Tool '%s' raised: %s", tool_name, exc, exc_info=True)
            audit_logger.record_event(
                "tool_execution_error",
                task_id=task_id,
                turn=turn,
                tool_name=tool_name,
                error_type=type(exc).__name__,
            )

        guard.record_tool_result(
            tool_name=tool_name,
            observation=observation,
            succeeded=succeeded,
            arguments=tool_args,
        )
        history.append(
            f"TURN {turn} TOOL {tool_name} ARGS {argument_summary} "
            f"RESULT {'success' if succeeded else 'failure'}: {observation}"
        )
        audit_logger.record_event(
            "tool_result",
            task_id=task_id,
            turn=turn,
            tool_name=tool_name,
            observation_length=len(observation),
            observation_is_error=not succeeded,
            duration_ms=round((time.perf_counter() - tool_started_at) * 1000, 2),
        )
        log_status(
            f"OBSERVATION ({'verified call' if succeeded else 'failure'}): {safe_preview(observation)}"
        )

        if not succeeded and _permission_boundary(observation):
            audit_logger.record_event(
                "task_blocked",
                task_id=task_id,
                turn=turn,
                source="host_permission_boundary",
                tool_name=tool_name,
            )
            return "BLOCKED: A permission boundary prevented safe progress"
        if _task_timed_out(task_started_at):
            audit_logger.record_event("task_timeout", task_id=task_id, turn=turn, phase="action")
            return f"FAILED: Task timed out after {config.task_timeout} seconds"
        if cancelled():
            if cancel_event:
                cancel_event.clear()
            audit_logger.record_event("task_cancelled", task_id=task_id, turn=turn, phase="action")
            return "CANCELLED: Task interrupted by the operator"

    failure_msg = f"FAILED: Task incomplete after {max_turns} turns"
    audit_logger.record_event(
        "task_failed", task_id=task_id, message="turn budget exhausted", max_turns=max_turns
    )
    logger.warning(failure_msg)
    log_status(failure_msg)
    return failure_msg
