"""
Action Tools Module

This module contains implementations for interacting with Windows UI elements
using pywinauto and performing automated actions. Each tool is designed to be
robust, handle errors gracefully, and provide clear feedback for the ReAct loop.
"""

from typing import Any, Optional

import logging

from pywinauto.application import Application
from pywinauto.findbestmatch import MatchError
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PywinautoTimeoutError

logger = logging.getLogger(__name__)


def _get_active_window() -> Optional[Any]:
    """
    Get a handle to the currently active window with UIA/Win32 fallback.

    Returns:
        The top window wrapper if connection succeeds, otherwise ``None``.
    """

    for backend in ("uia", "win32"):
        try:
            logger.debug(
                "Attempting to connect to active window using '%s' backend", backend
            )
            app = Application(backend=backend)
            app.connect(active_only=True, timeout=5)
            window = app.top_window()
            logger.debug(
                "Connected to window '%s' via backend '%s'",
                window.window_text(),
                backend,
            )
            return window
        except (PywinautoTimeoutError, RuntimeError, ElementNotFoundError, MatchError) as exc:
            logger.debug(
                "Backend '%s' failed to attach to active window: %s", backend, exc
            )
        except Exception as unexpected:
            logger.warning(
                "Unexpected error while attaching with backend '%s': %s",
                backend,
                unexpected,
                exc_info=True,
            )

    logger.error("No active window detected via UIA or Win32 backends")
    return None


def click(element_id: str) -> str:
    """
    Execute a mouse click on a specified UI element.
    
    This tool attempts to find and click a UI element in the active window.
    It waits for the element to be ready before interacting to handle dynamic UIs.
    
    Args:
        element_id: String identifier for the UI element (best match lookup).
        
    Returns:
        A string message indicating success or detailed error information.
    """
    window = _get_active_window()
    if window is None:
        return "Errore: Nessuna finestra attiva trovata."
    
    try:
        # Find the control using best match lookup
        logger.debug(f"Attempting to find element: {element_id}")
        control = window[element_id]
        
        # Wait for control to be visible and enabled (handles dynamic UIs)
        logger.debug(f"Waiting for element '{element_id}' to be ready")
        control.wait('ready', timeout=10)
        
        # Execute the click action
        control.click_input()
        logger.info(f"Successfully clicked element: {element_id}")
        return f"Elemento '{element_id}' cliccato con successo."
        
    except (ElementNotFoundError, PywinautoTimeoutError, MatchError) as e:
        error_msg = f"Errore: Impossibile trovare o interagire con l'elemento '{element_id}'. Dettagli: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:  # pragma: no cover - safety net for unexpected issues
        error_msg = (
            f"Errore imprevisto durante il click su '{element_id}'. Dettagli: {str(e)}"
        )
        logger.error(error_msg, exc_info=True)
        return error_msg


def type_text(element_id: str, text: str) -> str:
    """
    Type a given string into a specified input field.
    
    This tool finds a UI element and types text into it, preserving spaces
    and special characters.
    
    Args:
        element_id: String identifier for the input field.
        text: The text to type into the field.
        
    Returns:
        A string message indicating success or detailed error information.
    """
    window = _get_active_window()
    if window is None:
        return "Errore: Nessuna finestra attiva trovata."
    
    try:
        # Find the control using best match lookup
        logger.debug(f"Attempting to find input field: {element_id}")
        control = window[element_id]
        
        # Wait for control to be ready
        logger.debug(f"Waiting for element '{element_id}' to be ready")
        control.wait('ready', timeout=10)
        
        # Type the text with space handling
        control.type_keys(text, with_spaces=True)
        logger.info(f"Successfully typed text into element: {element_id}")
        return f"Testo '{text}' digitato con successo in '{element_id}'."
        
    except (ElementNotFoundError, PywinautoTimeoutError, MatchError) as e:
        error_msg = f"Errore: Impossibile trovare o digitare in '{element_id}'. Dettagli: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:  # pragma: no cover - safety net for unexpected issues
        error_msg = (
            f"Errore imprevisto durante la digitazione in '{element_id}'. Dettagli: {str(e)}"
        )
        logger.error(error_msg, exc_info=True)
        return error_msg


def get_text(element_id: str) -> str:
    """
    Retrieve the text content from a UI element.
    
    This tool finds a UI element and extracts its text content, useful for
    reading labels, button text, or input field values.
    
    Args:
        element_id: String identifier for the UI element.
        
    Returns:
        A string message with the retrieved text or detailed error information.
    """
    window = _get_active_window()
    if window is None:
        return "Errore: Nessuna finestra attiva trovata."
    
    try:
        # Find the control using best match lookup
        logger.debug(f"Attempting to find element: {element_id}")
        control = window[element_id]
        
        # Wait for control to exist
        logger.debug(f"Waiting for element '{element_id}' to exist")
        control.wait('exists', timeout=10)
        
        # Retrieve the text content
        text = control.window_text()
        logger.info(f"Successfully retrieved text from element: {element_id}")
        return f"Testo recuperato da '{element_id}': '{text}'"
        
    except (ElementNotFoundError, PywinautoTimeoutError, MatchError) as e:
        error_msg = f"Errore: Impossibile recuperare testo da '{element_id}'. Dettagli: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:  # pragma: no cover - safety net for unexpected issues
        error_msg = (
            f"Errore imprevisto durante il recupero del testo da '{element_id}'. Dettagli: {str(e)}"
        )
        logger.error(error_msg, exc_info=True)
        return error_msg


def scroll(direction: str, amount: int = 3) -> str:
    """
    Scroll in the active window.
    
    Args:
        direction: Direction to scroll ('up', 'down', 'left', 'right').
        amount: Number of scroll units (default: 3).
        
    Returns:
        A string message indicating the result.
    """
    # TODO: Implement scroll functionality in subsequent steps
    return "Tool not implemented yet."


def press_hotkey(keys: str) -> str:
    """
    Press a keyboard hotkey combination.
    
    Args:
        keys: Hotkey combination (e.g., 'ctrl+c', 'alt+tab').
        
    Returns:
        A string message indicating the result.
    """
    # TODO: Implement hotkey functionality in subsequent steps
    return "Tool not implemented yet."


def finish_task(summary: str) -> str:
    """
    Signal that the agent has completed the requested task.
    
    Args:
        summary: A brief summary of what was accomplished.
        
    Returns:
        A string message confirming task completion.
    """
    # TODO: Implement task completion logic in subsequent steps
    return f"Task completato: {summary}"
