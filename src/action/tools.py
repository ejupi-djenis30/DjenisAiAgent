"""
Action Tools Module

This module contains implementations for interacting with Windows UI elements
using pywinauto and performing automated actions. Each tool is designed to be
robust, handle errors gracefully, and provide clear feedback for the ReAct loop.
"""

from typing import Optional
from pywinauto import Desktop
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PywinautoTimeoutError
import logging

logger = logging.getLogger(__name__)


def _get_active_window() -> Optional[object]:
    """
    Get a handle to the currently active window with uia/win32 fallback.
    
    This private helper centralizes the logic for connecting to the active window,
    attempting first with the modern UIA backend and falling back to Win32 for
    legacy applications.
    
    Returns:
        A pywinauto window object if successful, None if no active window is found.
    """
    try:
        # Attempt connection with UIA backend (modern, recommended)
        logger.debug("Attempting to connect to active window using UIA backend")
        desktop = Desktop(backend="uia")
        active_window = desktop.windows()[0]  # Get first window (typically active)
        logger.debug(f"Successfully connected to window: {active_window.window_text()}")
        return active_window
    except (TimeoutError, RuntimeError, IndexError, ElementNotFoundError) as e:
        logger.debug(f"UIA backend failed: {e}. Attempting Win32 fallback")
        
        try:
            # Fallback to Win32 backend for legacy applications
            desktop = Desktop(backend="win32")
            active_window = desktop.windows()[0]
            logger.debug(f"Successfully connected via Win32: {active_window.window_text()}")
            return active_window
        except (TimeoutError, RuntimeError, IndexError, ElementNotFoundError) as e:
            logger.error(f"Failed to connect to active window with both backends: {e}")
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
        
    except (ElementNotFoundError, PywinautoTimeoutError, Exception) as e:
        error_msg = f"Errore: Impossibile trovare o interagire con l'elemento '{element_id}'. Dettagli: {str(e)}"
        logger.error(error_msg)
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
        
    except (ElementNotFoundError, PywinautoTimeoutError, Exception) as e:
        error_msg = f"Errore: Impossibile trovare o digitare in '{element_id}'. Dettagli: {str(e)}"
        logger.error(error_msg)
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
        
    except (ElementNotFoundError, PywinautoTimeoutError, Exception) as e:
        error_msg = f"Errore: Impossibile recuperare testo da '{element_id}'. Dettagli: {str(e)}"
        logger.error(error_msg)
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
    return f"Tool non implementato: scroll({direction}, {amount})"


def press_hotkey(keys: str) -> str:
    """
    Press a keyboard hotkey combination.
    
    Args:
        keys: Hotkey combination (e.g., 'ctrl+c', 'alt+tab').
        
    Returns:
        A string message indicating the result.
    """
    # TODO: Implement hotkey functionality in subsequent steps
    return f"Tool non implementato: press_hotkey({keys})"


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
