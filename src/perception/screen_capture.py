"""
Screen Capture Module

This module handles capturing screenshots of the desktop for perception.
"""

import io
import re
import contextlib
from typing import Optional, Tuple

import pyautogui
from PIL import Image
from pywinauto import Desktop
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PywinautoTimeoutError


def capture_ui_tree(window) -> str:
    """
    Extract and format the UI element hierarchy from a pywinauto window object.
    
    This function captures the structural information of UI elements, which complements
    the visual screenshot. It uses print_control_identifiers() to get the hierarchy
    and cleans up the output for better LLM consumption.
    
    Args:
        window: A pywinauto window object to extract UI tree from.
        
    Returns:
        str: A cleaned, formatted string representation of the UI element hierarchy.
    """
    # Create an in-memory text buffer to capture printed output
    buffer = io.StringIO()
    
    # Redirect stdout to the buffer and capture the UI tree
    with contextlib.redirect_stdout(buffer):
        try:
            # Print the control identifiers with limited depth to keep output manageable
            # Use wrapper_object() to get the actual window wrapper if needed
            if hasattr(window, 'print_control_identifiers'):
                window.print_control_identifiers(depth=4)
            elif hasattr(window, 'wrapper_object'):
                window.wrapper_object().print_control_identifiers(depth=4)
            else:
                # If neither method exists, try to get window info directly
                return f"Window: {window.window_text()}\nClass: {window.class_name()}"
        except Exception as e:
            return f"Error capturing UI tree: {str(e)}"
    
    # Get the complete string from the buffer
    ui_tree_raw = buffer.getvalue()
    
    # If buffer is empty, try alternative approach
    if not ui_tree_raw.strip():
        try:
            return f"Window: {window.window_text()}\nClass: {window.class_name()}\nControls: {len(window.children())}"
        except:
            return "Could not extract detailed UI tree information"
    
    # Clean up the output for better LLM consumption
    lines = ui_tree_raw.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Remove positional coordinates with various formats:
        # (L123, T456, R789, B910) or (L-13, T-13, R2893, B1837)
        line = re.sub(r'\(L-?\d+,\s*T-?\d+,\s*R-?\d+,\s*B-?\d+\)', '', line)
        
        # Filter out lines containing verbose 'child_window' phrase
        if 'child_window' not in line.lower():
            # Only add non-empty lines after cleaning
            cleaned_line = line.strip()
            if cleaned_line:
                cleaned_lines.append(cleaned_line)
    
    # Join the cleaned lines back into a single string
    return '\n'.join(cleaned_lines)


def get_multimodal_context() -> Tuple[Image.Image, str]:
    """
    Capture both visual and structural information about the current UI state.
    
    This is the main perception function that provides multimodal context:
    1. Visual: A screenshot of the current screen
    2. Structural: A text representation of UI elements
    
    The function attempts to use the UIA backend first (for modern Windows apps),
    then falls back to Win32 backend (for legacy apps) if needed.
    
    Returns:
        Tuple[Image.Image, str]: A tuple containing:
            - PIL Image object of the screenshot
            - String representation of the UI element tree
    """
    # Step 1: Capture the visual state of the screen
    screenshot = pyautogui.screenshot()
    
    # Step 2: Capture the structural UI information with fallback mechanisms
    ui_tree_text = ""

    try:
        active_window = _get_active_window("uia")
        if active_window is None:
            raise RuntimeError("UIA backend non ha restituito una finestra attiva.")
        ui_tree_text = capture_ui_tree(active_window)
    except Exception as primary_exc:
        try:
            active_window = _get_active_window("win32")
            if active_window is None:
                raise RuntimeError("Win32 backend non ha restituito una finestra attiva.")
            ui_tree_text = capture_ui_tree(active_window)
        except Exception as fallback_exc:
            reasons = []
            primary_reason = str(primary_exc).strip()
            if primary_reason:
                reasons.append(f"UIA: {primary_reason}")
            fallback_reason = str(fallback_exc).strip()
            if fallback_reason:
                reasons.append(f"Win32: {fallback_reason}")
            details = " | ".join(reasons) if reasons else "nessun dettaglio disponibile"
            ui_tree_text = (
                "Nessuna finestra attiva trovata o impossibile accedere agli elementi UI. "
                f"Dettagli: {details}"
            )
    
    return screenshot, ui_tree_text


def _get_active_window(backend: str) -> Optional[object]:
    """Return the active window for the requested pywinauto backend."""

    try:
        desktop = Desktop(backend=backend)
        windows = desktop.windows()
        if not windows:
            return None
        return windows[0]
    except (PywinautoTimeoutError, RuntimeError, ElementNotFoundError):
        return None


class ScreenCapture:
    """
    Handles screen capture operations.
    
    This class provides methods for:
    - Capturing full screen screenshots
    - Capturing multimodal context (screenshot + UI tree)
    - Processing and optimizing images
    - Converting images to formats suitable for Gemini API
    """
    
    def __init__(self):
        """Initialize the ScreenCapture."""
        pass
    
    def get_context(self) -> Tuple[Image.Image, str]:
        """
        Get the complete multimodal context (visual + structural).
        
        This is a convenience wrapper around the get_multimodal_context function.
        
        Returns:
            Tuple[Image.Image, str]: Screenshot and UI tree text.
        """
        return get_multimodal_context()
    
    def capture_screen(self) -> Image.Image:
        """
        Capture a screenshot of the entire screen.
        
        Returns:
            PIL.Image.Image: The captured screenshot.
        """
        return pyautogui.screenshot()
    
    def prepare_for_gemini(self, image: Image.Image) -> Image.Image:
        """
        Prepare an image for sending to Gemini API.
        
        Args:
            image: The image to prepare.
            
        Returns:
            Image.Image: The prepared image in a format suitable for Gemini API.
        """
        # For now, return the image as-is
        # In future steps, we might add optimization like resizing or compression
        return image
