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
from collections.abc import Mapping
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Protocol, TypeGuard, cast

from src.perception.screen_capture import get_multimodal_context
from src.reasoning.gemini_core import decide_next_action
from src.action import tools as action_tools
from src.config import config

logger = logging.getLogger(__name__)


class FunctionCallLike(Protocol):
    """Protocol describing the attributes of a Gemini FunctionCall."""

    name: str
    args: Mapping[str, Any]


def _is_function_call(response: Any) -> TypeGuard[FunctionCallLike]:
    """Return True when the response exposes the FunctionCall interface."""

    if not hasattr(response, "name") or not hasattr(response, "args"):
        return False

    name = getattr(response, "name")
    args = getattr(response, "args")
    return isinstance(name, str) and isinstance(args, Mapping)


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
    return _execute_agent_task(user_command, status_callback=print)


async def agent_loop(
    command_queue: asyncio.Queue,
    status_queue: asyncio.Queue,
    cancel_event: Event
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
    
    while True:
        try:
            # Block until a command is available
            user_command = await command_queue.get()
            cancel_event.clear()
            logger.info(f"Agent loop received command: {user_command}")
            await status_queue.put(f"📥 Received command: {user_command}")
            
            try:
                # Execute the command with status callback
                async def status_callback(message: str):
                    """Send status updates to the queue for broadcasting."""
                    await status_queue.put(message)
                
                # Run the agent task (uses run_in_executor for sync code)
                loop = asyncio.get_event_loop()
                executor_fn = functools.partial(
                    _execute_agent_task,
                    user_command,
                    lambda msg: asyncio.run_coroutine_threadsafe(
                        status_queue.put(msg),
                        loop
                    ).result(),
                    cancel_event
                )
                result = await loop.run_in_executor(None, executor_fn)
                
                logger.info(f"Command completed: {result}")
                await status_queue.put(f"✅ {result}")
                
            except Exception as e:
                error_msg = f"❌ Error executing command: {str(e)}"
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
            await status_queue.put(f"❌ Critical error: {str(e)}")


def _execute_agent_task(
    user_command: str,
    status_callback: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[Event] = None
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
    history: List[str] = []  # Store conversation and action log
    task_completed: bool = False  # Track task completion status
    
    # Use config for max turns with fallback
    MAX_TURNS: int = max(1, config.max_loop_turns)
    
    # Map tool names to actual functions from action module
    AVAILABLE_TOOLS: Dict[str, Callable[..., str]] = {
        # Core UI interaction tools
        "element_id": action_tools.element_id,
        "click": action_tools.click,
        "double_click": action_tools.double_click,
        "right_click": action_tools.right_click,
        "type_text": action_tools.type_text,
        "get_text": action_tools.get_text,
        
        # Navigation and control tools
        "scroll": action_tools.scroll,
        "press_hotkey": action_tools.press_hotkey,
        "move_mouse": action_tools.move_mouse,
        "wait_seconds": action_tools.wait_seconds,
        
        # Window management tools
        "minimize_window": action_tools.minimize_window,
        "maximize_window": action_tools.maximize_window,
        "close_window": action_tools.close_window,
        "switch_window": action_tools.switch_window,
        
        # Clipboard tools
        "copy_to_clipboard": action_tools.copy_to_clipboard,
        "paste_from_clipboard": action_tools.paste_from_clipboard,
        "get_clipboard_text": action_tools.get_clipboard_text,
        "set_clipboard_text": action_tools.set_clipboard_text,
        
        # Application and file tools
        "start_application": action_tools.start_application,
        "open_file": action_tools.open_file,
        "open_url": action_tools.open_url,
        "take_screenshot": action_tools.take_screenshot,
        
        # Task completion
        "finish_task": action_tools.finish_task,
    }
    
    logger.info("Starting agent loop for command: %s", user_command)
    logger.info("Maximum turns: %d", MAX_TURNS)
    log_status(f"\n{'='*80}")
    log_status(f"🤖 AVVIO AGENTE - Comando: {user_command}")
    log_status(f"{'='*80}\n")
    
    # ===== MAIN REACT LOOP =====
    for turn in range(1, MAX_TURNS + 1):
        if cancelled():
            log_status("🛑 Task cancellato dall'utente. Interruzione in corso…")
            logger.info("Task cancellation detected before turn %s", turn)
            if cancel_event:
                cancel_event.clear()
            return "CANCELLATO: Task interrotto dall'utente"

        # Check if task is already completed
        if task_completed:
            success_msg = f"✅ Task completato con successo al turno {turn - 1}!"
            logger.info(success_msg)
            log_status(f"\n{success_msg}\n")
            break

        log_status(f"\n--- TURNO {turn}/{MAX_TURNS} ---\n")
        logger.info("Starting turn %s/%s", turn, MAX_TURNS)

        # ===== STEP A: OBSERVE (Perception) =====
        try:
            logger.debug("Capturing multimodal context (screenshot + UI tree)")
            screenshot, ui_tree = get_multimodal_context()
            
            log_status("📸 PERCEZIONE: Screenshot e albero UI catturati.")
            logger.info("Perception: Successfully captured screen and UI tree")
            logger.debug(f"UI tree length: {len(ui_tree)} characters")
            
        except Exception as e:
            error_msg = f"Errore durante la percezione: {str(e)}"
            logger.error(error_msg, exc_info=True)
            log_status(f"❌ {error_msg}")
            # Add error to history and continue to allow recovery
            history.append(f"ERRORE PERCEZIONE: {error_msg}")
            continue

        if cancelled():
            log_status("🛑 Task cancellato dall'utente durante la fase di percezione.")
            if cancel_event:
                cancel_event.clear()
            return "CANCELLATO: Task interrotto dall'utente"
        
        # ===== STEP B: REASON (Call Gemini) =====
        try:
            logger.debug("Calling Gemini API for next action decision")

            # Convert tool functions to list for Gemini
            tool_functions = list(AVAILABLE_TOOLS.values())

            response = decide_next_action(
                screenshot_image=screenshot,
                ui_tree=ui_tree,
                user_command=user_command,
                history=history,
                available_tools=tool_functions,
            )

            logger.info("Reasoning: Received response from Gemini")
            
        except Exception as e:
            error_msg = f"Errore durante il ragionamento: {str(e)}"
            logger.error(error_msg, exc_info=True)
            log_status(f"❌ {error_msg}")
            history.append(f"ERRORE RAGIONAMENTO: {error_msg}")
            continue

        if cancelled():
            log_status("🛑 Task cancellato dall'utente durante la fase di ragionamento.")
            if cancel_event:
                cancel_event.clear()
            return "CANCELLATO: Task interrotto dall'utente"
        
        # ===== STEP C: ACT (Dispatch the Action) =====
        observation: str = ""
        
        try:
            if _is_function_call(response):
                function_call = cast(FunctionCallLike, response)
                tool_name = function_call.name
                tool_args = dict(function_call.args)

                log_status(f"🧠 PENSIERO: Il modello ha deciso di chiamare lo strumento '{tool_name}'")
                log_status(f"   Argomenti: {tool_args}")
                logger.info("Action: Dispatching tool '%s' with args: %s", tool_name, tool_args)

                if tool_name == "finish_task":
                    task_completed = True
                    summary = tool_args.get("summary", "Task completato")
                    observation = f"✅ TASK COMPLETATO: {summary}"
                    log_status(f"\n{observation}\n")
                    logger.info("Task marked as completed: %s", summary)

                    history.append("PENSIERO: finish_task chiamato")
                    history.append(observation)
                    continue

                if tool_name not in AVAILABLE_TOOLS:
                    observation = (
                        f"Errore: Strumento '{tool_name}' non trovato nei tool disponibili."
                    )
                    logger.error(observation)
                    log_status(f"❌ {observation}")
                else:
                    tool_function = AVAILABLE_TOOLS[tool_name]
                    try:
                        observation = tool_function(**tool_args)
                        logger.info(
                            "Action: Tool '%s' executed, result: %s",
                            tool_name,
                            observation[:100],
                        )
                    except TypeError as exc:
                        observation = (
                            f"Errore: Argomenti non validi per '{tool_name}'. Dettagli: {exc}"
                        )
                        logger.error(observation)
                    except Exception as exc:
                        observation = (
                            f"Errore durante l'esecuzione di '{tool_name}': {exc}"
                        )
                        logger.error(observation, exc_info=True)
            else:
                observation = str(response)
                log_status("💬 PENSIERO: Il modello ha risposto con del testo:")
                log_status(f"   {observation}")
                logger.info("Action: Model responded with text instead of function call")

        except Exception as e:
            observation = f"Errore durante il dispatch dell'azione: {str(e)}"
            logger.error(observation, exc_info=True)
            log_status(f"❌ {observation}")

        if cancelled():
            log_status("🛑 Task cancellato dall'utente durante l'esecuzione dell'azione.")
            if cancel_event:
                cancel_event.clear()
            return "CANCELLATO: Task interrotto dall'utente"
        
        # ===== STEP D: VERIFY & UPDATE HISTORY (Feedback) =====
        log_status(f"👁️  OSSERVAZIONE: {observation}")
        
        # Update history with thought and observation for next iteration
        if _is_function_call(response):
            function_call = cast(FunctionCallLike, response)
            history.append(
                f"PENSIERO: Chiamato {function_call.name} con {dict(function_call.args)}"
            )
        else:
            history.append(f"PENSIERO: {str(response)[:200]}")
        
        history.append(f"OSSERVAZIONE: {observation}")
        
        logger.debug(f"History updated, total entries: {len(history)}")
    
    # ===== HANDLE LOOP TERMINATION =====
    if not task_completed:
        if cancelled():
            log_status("🛑 Task cancellato dall'utente.")
            return "CANCELLATO: Task interrotto dall'utente"
        failure_msg = f"⚠️  L'agente non è riuscito a completare il task entro {MAX_TURNS} turni."
        logger.warning(failure_msg)
        log_status(f"\n{failure_msg}\n")
        return f"FALLITO: Task non completato dopo {MAX_TURNS} turni"
    
    return "SUCCESSO: Task completato"
