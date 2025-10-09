"""Screen capture and UI tree utilities."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pyautogui
from PIL import Image
from pywinauto import Desktop
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PywinautoTimeoutError

logger = logging.getLogger(__name__)

MAX_SNAPSHOT_DEPTH = 4
LAST_UI_SNAPSHOT: List[Dict[str, Any]] = []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value).strip()
    except Exception:  # pragma: no cover - defensive
        return ""


def _extract_metadata(wrapper: Any, depth: int, index: int, include_wrappers: bool) -> Dict[str, Any]:
    info = getattr(wrapper, "element_info", None)

    def attr(name: str) -> str:
        return _safe_str(getattr(info, name, "")) if info is not None else ""

    metadata: Dict[str, Any] = {
        "index": index,
        "depth": depth,
        "title": _safe_str(getattr(wrapper, "window_text", lambda: "")()),
        "name": attr("name"),
        "auto_id": attr("automation_id"),
        "control_type": attr("control_type"),
        "class_name": attr("class_name"),
        "control_id": attr("control_id"),
        "handle": getattr(info, "handle", None) if info is not None else None,
    }

    try:
        metadata["friendly_class"] = _safe_str(wrapper.friendly_class_name())
    except Exception:  # pragma: no cover - backend differences
        metadata["friendly_class"] = ""

    selector_candidates = [value for value in (metadata["auto_id"], metadata["title"], metadata["name"]) if value]
    metadata["selector"] = selector_candidates[0] if selector_candidates else ""

    search_hints: Dict[str, str] = {}
    if metadata["selector"]:
        search_hints["title"] = metadata["selector"]
    if metadata["auto_id"]:
        search_hints["auto_id"] = metadata["auto_id"]
    control_type = metadata["control_type"] or metadata["friendly_class"] or metadata["class_name"]
    if control_type:
        search_hints["control_type"] = control_type
    metadata["search_hints"] = search_hints

    if include_wrappers:
        metadata["wrapper"] = wrapper

    return metadata


def build_control_snapshot(
    window: Any,
    *,
    max_depth: int = MAX_SNAPSHOT_DEPTH,
    include_wrappers: bool = False,
) -> List[Dict[str, Any]]:
    """Enumerate controls for the active window up to the requested depth."""

    results: List[Dict[str, Any]] = []
    counter = 0

    def _walk(node: Any, depth: int) -> None:
        nonlocal counter
        if depth > max_depth:
            return

        counter += 1
        results.append(_extract_metadata(node, depth, counter, include_wrappers))

        if depth >= max_depth:
            return

        try:
            children = node.children()
        except Exception as exc:  # pragma: no cover - backend-specific failures
            logger.debug("Unable to enumerate children for node %s: %s", results[-1].get("selector") or results[-1]["index"], exc)
            return

        for child in children:
            _walk(child, depth + 1)

    _walk(window, 0)
    return results


def snapshot_to_text(snapshot: List[Dict[str, Any]]) -> str:
    """Convert a control snapshot into a readable tree for the LLM."""

    if not snapshot:
        return "Nessuna finestra attiva trovata."

    lines: List[str] = []
    for entry in snapshot:
        indent = "  " * entry["depth"]
        type_label = entry.get("control_type") or entry.get("friendly_class") or entry.get("class_name") or "Control"
        parts = [f"type={type_label}"]

        title = entry.get("title")
        if title:
            parts.append(f'title="{title}"')

        name = entry.get("name")
        if name and name != title:
            parts.append(f'name="{name}"')

        auto_id = entry.get("auto_id")
        if auto_id:
            parts.append(f'auto_id="{auto_id}"')

        control_id = entry.get("control_id")
        if control_id:
            parts.append(f"control_id={control_id}")

        selector = entry.get("selector")
        if selector and selector not in (title, name, auto_id):
            parts.append(f'selector="{selector}"')

        lines.append(f"{indent}[{entry['index']}] " + " | ".join(parts))

    return "\n".join(lines)


def capture_ui_tree(window: Any) -> str:
    """Capture the UI tree and cache the underlying snapshot for tool reuse."""

    global LAST_UI_SNAPSHOT
    snapshot = build_control_snapshot(window, include_wrappers=True)
    LAST_UI_SNAPSHOT = snapshot
    return snapshot_to_text(snapshot)


def refresh_ui_snapshot(window: Any) -> List[Dict[str, Any]]:
    """Rebuild and cache the UI snapshot without producing formatted text."""

    global LAST_UI_SNAPSHOT
    LAST_UI_SNAPSHOT = build_control_snapshot(window, include_wrappers=True)
    return LAST_UI_SNAPSHOT


def get_latest_ui_snapshot() -> List[Dict[str, Any]]:
    """Return the most recent UI snapshot captured during perception."""

    return LAST_UI_SNAPSHOT


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
    
    global LAST_UI_SNAPSHOT

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
            logger.warning("Impossibile acquisire l'albero UI: %s", details)
            LAST_UI_SNAPSHOT = []
    
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
