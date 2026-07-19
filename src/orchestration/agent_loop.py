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
from src.perception.screen_capture import get_multimodal_context
from src.reasoning.gemini_core import decide_next_action
from src.redaction import bounded_text, safe_preview

logger = logging.getLogger(__name__)


class FunctionCallLike(Protocol):
    """Protocol describing the attributes of a Gemini FunctionCall."""

    name: str
    args: Mapping[str, Any]


def _is_function_call(response: Any) -> TypeGuard[FunctionCallLike]:
    """Return True when the response exposes the FunctionCall interface."""

    if not hasattr(response, "name") or not hasattr(response, "args"):
        return False

    name = response.name
    args = response.args
    return isinstance(name, str) and isinstance(args, Mapping)


def _is_mouse_positioning_tool(tool_name: str) -> bool:
    """Check if a tool is part of the mouse positioning mini-loop."""
    return tool_name in {"move_mouse", "verify_mouse_position", "confirm_mouse_position"}


def _task_timed_out(started_at: float) -> bool:
    """Return True when the wall-clock deadline for the task has been reached."""

    return (time.monotonic() - started_at) >= config.task_timeout


def _build_available_tools() -> dict[str, Callable[..., str]]:
    """Build a capability registry that matches the active runtime and operator tier."""

    tools: dict[str, Callable[..., str]] = {
        "deep_think": action_tools.deep_think,
        "finish_task": action_tools.finish_task,
        "browser_runtime_status": action_tools.browser_runtime_status,
        "browser_media_capability": action_tools.browser_media_capability,
        "list_files": action_tools.list_files,
        "read_file": action_tools.read_file,
    }

    if config.permits("interact"):
        tools["open_url"] = action_tools.open_url
        if config.supports_native_desktop():
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
                    "move_mouse": action_tools.move_mouse,
                    "verify_mouse_position": action_tools.verify_mouse_position,
                    "confirm_mouse_position": action_tools.confirm_mouse_position,
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
    2. Reason: Use Gemini to decide next action
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
                await status_queue.put(f"✅ {result}")

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


def _execute_agent_task(
    user_command: str,
    status_callback: Callable[[str], None] | None = None,
    cancel_event: Event | None = None,
) -> str:
    """
    Internal function that executes a single agent task.

    This function contains the core ReAct logic and is used by both:
    - run_agent_loop() for synchronous CLI mode
    - agent_loop() for asynchronous web mode

    Args:
        user_command: The user's natural language command to execute
        status_callback: Optional callback function to report status updates

    Returns:
        str: Final status message indicating success, failure or cancellation
    """

    def cancelled() -> bool:
        return bool(cancel_event and cancel_event.is_set())

    def log_status(message: str):
        """Helper to log status via callback or print."""
        if status_callback:
            status_callback(message)
        else:
            print(message)

    # ===== INITIALIZATION =====
    history: list[str] = []  # Store conversation and action log
    task_completed: bool = False  # Track task completion status
    task_started_at = time.monotonic()
    task_id = uuid4().hex

    audit_logger.record_event(
        "task_started",
        task_id=task_id,
        user_command_length=len(user_command),
        max_turns=config.max_loop_turns,
        task_timeout=config.task_timeout,
    )

    # Use config for max turns with fallback
    MAX_TURNS: int = max(1, config.max_loop_turns)

    AVAILABLE_TOOLS = _build_available_tools()

    logger.info("Starting agent loop for a command (%d characters)", len(user_command))
    logger.info("Maximum turns: %d", MAX_TURNS)
    logger.info("Maximum mouse positioning attempts: %d", config.max_mouse_positioning_attempts)
    log_status(f"\n{'=' * 80}")
    log_status("Agent started the queued operator task.")
    log_status(f"{'=' * 80}\n")

    # Mouse positioning state tracking
    mouse_positioning_active = False
    mouse_positioning_attempts = 0

    # ===== MAIN REACT LOOP =====
    # Mouse-positioning steps are bounded separately and do not consume a normal
    # reasoning turn. All failures do consume a turn, so the loop cannot spin
    # forever when perception or the model repeatedly fails.
    turn = 1
    while turn <= MAX_TURNS:
        if _task_timed_out(task_started_at):
            timeout_msg = f"Task exceeded the {config.task_timeout}-second limit."
            logger.warning(timeout_msg)
            log_status(f"\n{timeout_msg}\n")
            audit_logger.record_event(
                "task_timeout", task_id=task_id, turn=turn, message=timeout_msg
            )
            return f"FAILED: Task timed out after {config.task_timeout} seconds"

        audit_logger.record_event(
            "turn_started",
            task_id=task_id,
            turn=turn,
            history_size=len(history),
        )

        if cancelled():
            log_status("Task cancelled by the operator.")
            logger.info("Task cancellation detected before turn %s", turn)
            if cancel_event:
                cancel_event.clear()
            audit_logger.record_event(
                "task_cancelled", task_id=task_id, turn=turn, phase="pre_turn"
            )
            return "CANCELLED: Task interrupted by the operator"

        log_status(f"\n--- TURN {turn}/{MAX_TURNS} ---\n")
        logger.info("Starting turn %s/%s", turn, MAX_TURNS)

        # ===== STEP A: OBSERVE (Perception) =====
        try:
            logger.debug("Capturing multimodal context (screenshot + UI tree)")
            screenshot, ui_tree = get_multimodal_context()

            log_status("PERCEPTION: Screenshot and UI tree captured.")
            logger.info("Perception: Successfully captured screen and UI tree")
            logger.debug(f"UI tree length: {len(ui_tree)} characters")

        except Exception as e:
            error_msg = f"Perception error: {e!s}"
            logger.error(error_msg, exc_info=True)
            log_status(f"❌ {error_msg}")
            # Add error to history and continue to allow recovery
            history.append(f"PERCEPTION ERROR: {error_msg}")
            audit_logger.record_event(
                "perception_error", task_id=task_id, turn=turn, error=error_msg
            )
            turn += 1
            continue

        if _task_timed_out(task_started_at):
            timeout_msg = f"Task exceeded the {config.task_timeout}-second limit during perception."
            logger.warning(timeout_msg)
            log_status(f"\n{timeout_msg}\n")
            audit_logger.record_event(
                "task_timeout", task_id=task_id, turn=turn, phase="perception", message=timeout_msg
            )
            return f"FAILED: Task timed out after {config.task_timeout} seconds"

        if cancelled():
            log_status("Task cancelled during perception.")
            if cancel_event:
                cancel_event.clear()
            audit_logger.record_event(
                "task_cancelled", task_id=task_id, turn=turn, phase="perception"
            )
            return "CANCELLED: Task interrupted by the operator"

        # ===== STEP B: REASON =====
        # Gemini owns the network retry policy. Keeping a single retry layer here
        # prevents one logical turn from multiplying into many API calls.
        try:
            response = decide_next_action(
                screenshot_image=screenshot,
                ui_tree=ui_tree,
                user_command=user_command,
                history=history,
                available_tools=list(AVAILABLE_TOOLS.values()),
                cancel_event=cancel_event,
            )
        except Exception as exc:
            error_msg = f"Reasoning error: {exc!s}"
            logger.error(error_msg, exc_info=True)
            log_status(f"❌ {error_msg}")
            history.append(f"REASONING ERROR: {error_msg}")
            audit_logger.record_event(
                "reasoning_error", task_id=task_id, turn=turn, error=error_msg
            )
            turn += 1
            continue

        if not _is_function_call(response):
            invalid_response_preview = safe_preview(response or "<empty>")
            logger.warning("Gemini returned no valid tool call: %s", invalid_response_preview)
            log_status("⚠️ The model did not choose a valid action. Moving to the next turn.")
            history.append(f"REASONING ERROR: {invalid_response_preview}")
            audit_logger.record_event(
                "reasoning_invalid_response",
                task_id=task_id,
                turn=turn,
                response_preview=invalid_response_preview,
            )
            turn += 1
            continue

        if _task_timed_out(task_started_at):
            timeout_msg = f"Task exceeded the {config.task_timeout}-second limit during reasoning."
            logger.warning(timeout_msg)
            log_status(f"\n{timeout_msg}\n")
            audit_logger.record_event(
                "task_timeout", task_id=task_id, turn=turn, phase="reasoning", message=timeout_msg
            )
            return f"FAILED: Task timed out after {config.task_timeout} seconds"

        if cancelled():
            log_status("Task cancelled during reasoning.")
            if cancel_event:
                cancel_event.clear()
            audit_logger.record_event(
                "task_cancelled", task_id=task_id, turn=turn, phase="reasoning"
            )
            return "CANCELLED: Task interrupted by the operator"

        # ===== STEP C: ACT (Dispatch the Action) =====
        observation: str = ""

        try:
            if _is_function_call(response):
                function_call = cast(FunctionCallLike, response)
                tool_name = function_call.name
                tool_args = dict(function_call.args)

                # Check if entering mouse positioning mini-loop
                if _is_mouse_positioning_tool(tool_name):
                    if not mouse_positioning_active:
                        # Starting new mouse positioning sequence
                        mouse_positioning_active = True
                        mouse_positioning_attempts = 0
                        log_status(
                            f"🖱️  MINI-LOOP MOUSE: Starting mouse positioning sequence (max attempts: {config.max_mouse_positioning_attempts})"
                        )
                        logger.info("Entering mouse positioning mini-loop")

                    mouse_positioning_attempts += 1

                    # Check if max attempts exceeded
                    if mouse_positioning_attempts > config.max_mouse_positioning_attempts:
                        mouse_positioning_active = False
                        mouse_positioning_attempts = 0
                        observation = (
                            f"ERROR: Mouse positioning mini-loop exceeded maximum attempts "
                            f"({config.max_mouse_positioning_attempts}). Exiting mini-loop. "
                            "Consider using element_id or alternative approaches."
                        )
                        log_status(f"❌ {observation}")
                        logger.warning(observation)
                        history.append(
                            f"THOUGHT: Mouse positioning failed after {config.max_mouse_positioning_attempts} attempts"
                        )
                        history.append(f"OBSERVATION: {observation}")
                        turn += 1
                        continue

                    log_status(
                        f"THOUGHT: The model selected '{tool_name}' "
                        f"(mouse attempt {mouse_positioning_attempts}/"
                        f"{config.max_mouse_positioning_attempts})"
                    )
                    log_status(f"   Arguments: {safe_preview(tool_args)}")
                    logger.info(
                        "Mouse mini-loop action: Dispatching tool '%s' (attempt %d/%d)",
                        tool_name,
                        mouse_positioning_attempts,
                        config.max_mouse_positioning_attempts,
                    )

                    # Execute mouse tool
                    tool_function = AVAILABLE_TOOLS[tool_name]
                    try:
                        observation = tool_function(**tool_args)
                        logger.info(
                            "Mouse tool '%s' executed, result: %s",
                            tool_name,
                            safe_preview(observation[:100]),
                        )

                        # Check if this was confirm_mouse_position - if so, exit mini-loop
                        if tool_name == "confirm_mouse_position":
                            log_status(
                                f"🖱️  MINI-LOOP MOUSE: Position confirmed, exiting mini-loop after {mouse_positioning_attempts} attempts"
                            )
                            logger.info("Mouse position confirmed, exiting mini-loop")
                            mouse_positioning_active = False
                            mouse_positioning_attempts = 0

                    except TypeError as exc:
                        observation = f"Error: Invalid arguments for '{tool_name}'. Details: {exc}"
                        logger.error(observation)
                    except Exception as exc:
                        observation = f"Error executing '{tool_name}': {exc}"
                        logger.error(observation, exc_info=True)

                    observation = bounded_text(observation, config.observation_max_chars)
                    log_status(f"OBSERVATION: {safe_preview(observation)}")

                    # Update history for mini-loop
                    history.append(
                        f"MOUSE MINI-LOOP [{mouse_positioning_attempts}/{config.max_mouse_positioning_attempts}]: "
                        f"Called {tool_name} with {safe_preview(tool_args)}"
                    )
                    history.append(f"OBSERVATION: {observation}")

                    # Mouse positioning has its own strict attempt limit, so it can
                    # gather another frame without spending a normal ReAct turn.
                    continue

                # If we were in mouse positioning mode but now calling a non-mouse tool, exit mini-loop
                if mouse_positioning_active and not _is_mouse_positioning_tool(tool_name):
                    log_status("🖱️  MINI-LOOP MOUSE: Exiting due to non-mouse tool call")
                    logger.info("Exiting mouse mini-loop - non-mouse tool called")
                    mouse_positioning_active = False
                    mouse_positioning_attempts = 0

                log_status(f"THOUGHT: The model selected tool '{tool_name}'")
                log_status(f"   Arguments: {safe_preview(tool_args)}")
                logger.info(
                    "Action: Dispatching tool '%s' with args: %s",
                    tool_name,
                    safe_preview(tool_args),
                )
                audit_logger.record_event(
                    "tool_dispatched",
                    task_id=task_id,
                    turn=turn,
                    tool_name=tool_name,
                    tool_arg_names=sorted(tool_args),
                    tool_arg_lengths={key: len(str(value)) for key, value in tool_args.items()},
                )

                if tool_name == "finish_task":
                    task_completed = True
                    summary = tool_args.get("summary", "Task completed")
                    observation = f"TASK COMPLETED: {summary}"
                    log_status(f"\n{observation}\n")
                    logger.info("Task marked as completed: %s", safe_preview(summary))
                    audit_logger.record_event(
                        "task_completed",
                        task_id=task_id,
                        turn=turn,
                        summary_length=len(str(summary)),
                    )

                    history.append("THOUGHT: finish_task called")
                    history.append(observation)
                    break

                if tool_name not in AVAILABLE_TOOLS:
                    observation = f"Error: Tool '{tool_name}' is not in the available registry."
                    logger.error(observation)
                    log_status(f"❌ {observation}")
                else:
                    tool_function = AVAILABLE_TOOLS[tool_name]
                    try:
                        observation = bounded_text(
                            tool_function(**tool_args), config.observation_max_chars
                        )
                        logger.info(
                            "Action: Tool '%s' executed, result: %s",
                            tool_name,
                            safe_preview(observation[:100]),
                        )
                    except TypeError as exc:
                        observation = f"Error: Invalid arguments for '{tool_name}'. Details: {exc}"
                        logger.error(observation)
                        audit_logger.record_event(
                            "tool_argument_error",
                            task_id=task_id,
                            turn=turn,
                            tool_name=tool_name,
                            error=str(exc),
                        )
                    except Exception as exc:
                        observation = f"Error while executing '{tool_name}': {exc}"
                        logger.error(observation, exc_info=True)
                        audit_logger.record_event(
                            "tool_execution_error",
                            task_id=task_id,
                            turn=turn,
                            tool_name=tool_name,
                            error=str(exc),
                        )
                    else:
                        audit_logger.record_event(
                            "tool_result",
                            task_id=task_id,
                            turn=turn,
                            tool_name=tool_name,
                            observation_length=len(observation),
                            observation_is_error=observation.casefold().startswith("error"),
                        )
            else:
                observation = str(response)
                log_status("THOUGHT: The model returned text instead of a tool call:")
                log_status(f"   {observation}")
                logger.info("Action: Model responded with text instead of function call")
                audit_logger.record_event(
                    "model_text_response", task_id=task_id, turn=turn, response=observation
                )

        except Exception as e:
            observation = f"Action dispatch error: {e!s}"
            logger.error(observation, exc_info=True)
            log_status(f"❌ {observation}")
            audit_logger.record_event(
                "dispatch_error", task_id=task_id, turn=turn, error=observation
            )

        if cancelled():
            log_status("Task cancelled during action execution.")
            if cancel_event:
                cancel_event.clear()
            audit_logger.record_event("task_cancelled", task_id=task_id, turn=turn, phase="action")
            return "CANCELLED: Task interrupted by the operator"

        if _task_timed_out(task_started_at):
            timeout_msg = f"Task exceeded the {config.task_timeout}-second limit during execution."
            logger.warning(timeout_msg)
            log_status(f"\n{timeout_msg}\n")
            audit_logger.record_event(
                "task_timeout", task_id=task_id, turn=turn, phase="action", message=timeout_msg
            )
            return f"FAILED: Task timed out after {config.task_timeout} seconds"

        # ===== STEP D: VERIFY & UPDATE HISTORY (Feedback) =====
        log_status(f"OBSERVATION: {safe_preview(observation)}")

        # Update history with thought and observation for next iteration
        if _is_function_call(response):
            function_call = cast(FunctionCallLike, response)
            history.append(
                f"THOUGHT: Called {function_call.name} with {safe_preview(dict(function_call.args))}"
            )
        else:
            history.append(f"THOUGHT: {str(response)[:200]}")

        history.append(f"OBSERVATION: {observation}")

        logger.debug(f"History updated, total entries: {len(history)}")
        turn += 1

    # ===== HANDLE LOOP TERMINATION =====
    if not task_completed:
        if cancelled():
            log_status("Task cancelled by the operator.")
            audit_logger.record_event("task_cancelled", task_id=task_id, phase="finalize")
            return "CANCELLED: Task interrupted by the operator"
        failure_msg = f"FAILED: Agent did not complete the task within {MAX_TURNS} turns."
        logger.warning(failure_msg)
        log_status(f"\n{failure_msg}\n")
        audit_logger.record_event("task_failed", task_id=task_id, message=failure_msg)
        return f"FAILED: Task incomplete after {MAX_TURNS} turns"

    audit_logger.record_event("task_succeeded", task_id=task_id)
    return "SUCCESS: Task completed"
