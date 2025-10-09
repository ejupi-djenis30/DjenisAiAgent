"""Action tools used by the Windows automation agent."""

from __future__ import annotations

import difflib
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pywinauto.application import Application
from pywinauto.findbestmatch import MatchError
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PywinautoTimeoutError

from src.perception.screen_capture import get_latest_ui_snapshot, refresh_ui_snapshot

logger = logging.getLogger(__name__)

_LOCATOR_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_LOCATOR_CACHE_LIMIT = 64


def _normalize(value: Optional[str]) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _safe_attr(source: Any, attribute: str) -> str:
    try:
        candidate = getattr(source, attribute)
        if callable(candidate):
            candidate = candidate()
        return str(candidate).strip()
    except Exception:
        return ""


def _augment_metadata(metadata: Optional[Dict[str, Any]], control: Any) -> Dict[str, Any]:
    info = getattr(control, "element_info", None)
    metadata = metadata.copy() if metadata else {}
    metadata.setdefault("title", _safe_attr(control, "window_text"))
    if info is not None:
        metadata.setdefault("name", _safe_attr(info, "name"))
        metadata.setdefault("auto_id", _safe_attr(info, "automation_id"))
        metadata.setdefault("control_type", _safe_attr(info, "control_type"))
        metadata.setdefault("class_name", _safe_attr(info, "class_name"))
    return metadata


def _store_locator(entry: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    token = f"element:{uuid4().hex[:12]}"
    metadata = {k: v for k, v in entry.items() if k != "wrapper"}
    _LOCATOR_CACHE[token] = {"metadata": metadata, "wrapper": entry.get("wrapper")}
    if len(_LOCATOR_CACHE) > _LOCATOR_CACHE_LIMIT:
        _LOCATOR_CACHE.popitem(last=False)
    return token, metadata


def _resolve_cached_control(window: Any, identifier: str) -> Optional[Tuple[Any, Dict[str, Any]]]:
    entry = _LOCATOR_CACHE.get(identifier)
    if not entry:
        return None

    metadata = entry.get("metadata", {})
    wrapper = entry.get("wrapper")

    if wrapper is not None:
        try:
            _ = wrapper.element_info  # Access to ensure the wrapper is still valid
            return wrapper, metadata
        except Exception:
            logger.debug("Cached wrapper invalid for %s; attempting to refresh", identifier)

    search_hints = {k: v for k, v in metadata.get("search_hints", {}).items() if v}
    if search_hints:
        try:
            spec = window.child_window(**search_hints)
            spec.wait('ready', timeout=10)
            wrapper = spec.wrapper_object()
            entry["wrapper"] = wrapper
            return wrapper, metadata
        except (ElementNotFoundError, MatchError, PywinautoTimeoutError) as exc:
            logger.debug("Search hints failed for %s: %s", identifier, exc)

    selector = metadata.get("selector")
    if selector:
        try:
            spec = window[selector]
            spec.wait('ready', timeout=10)
            wrapper = spec.wrapper_object()
            entry["wrapper"] = wrapper
            return wrapper, metadata
        except (ElementNotFoundError, MatchError, PywinautoTimeoutError) as exc:
            logger.debug("Selector fallback failed for %s: %s", identifier, exc)

    _LOCATOR_CACHE.pop(identifier, None)
    return None


def _prepare_wrapper(control: Any, timeout: float = 10.0) -> Any:
    try:
        control.wait('ready', timeout=timeout)
    except AttributeError:
        pass
    except Exception as exc:
        logger.debug("Wait on control failed: %s", exc)

    try:
        return control.wrapper_object()
    except AttributeError:
        return control


def _resolve_control(window: Any, identifier: str) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
    cached = _resolve_cached_control(window, identifier)
    if cached is not None:
        wrapper, metadata = cached
        try:
            wrapper = _prepare_wrapper(wrapper)
            metadata = _augment_metadata(metadata, wrapper)
            return wrapper, metadata
        except Exception as exc:
            logger.debug("Cached locator unusable (%s). Retrying lookup.", exc)

    try:
        spec = window[identifier]
        spec.wait('ready', timeout=10)
        wrapper = spec.wrapper_object()
        metadata = _augment_metadata({"selector": identifier}, wrapper)
        return wrapper, metadata
    except (ElementNotFoundError, MatchError, PywinautoTimeoutError) as exc:
        logger.error("Unable to resolve element '%s': %s", identifier, exc)
        return None, {"error": str(exc), "selector": identifier}


def _describe_target(metadata: Optional[Dict[str, Any]]) -> str:
    if not metadata:
        return "elemento"
    for key in ("title", "name", "auto_id", "selector"):
        value = metadata.get(key)
        if value:
            return f"elemento '{value}'"
    control_type = metadata.get("control_type") or metadata.get("class_name")
    if control_type:
        return f"elemento {control_type}"
    return "elemento"


def _score_candidate(
    entry: Dict[str, Any],
    query_norm: str,
    control_type_norm: str,
    auto_id_norm: str,
    exact: bool,
) -> float:
    if auto_id_norm and _normalize(entry.get("auto_id")) != auto_id_norm:
        return -1.0

    entry_type = _normalize(entry.get("control_type") or entry.get("friendly_class") or entry.get("class_name"))
    if control_type_norm and entry_type != control_type_norm:
        return -1.0

    candidates = [
        _normalize(entry.get("title")),
        _normalize(entry.get("name")),
        _normalize(entry.get("auto_id")),
        _normalize(entry.get("selector")),
    ]

    score = 0.0

    if exact and query_norm:
        if query_norm not in candidates:
            return -1.0
        score += 4.0
    elif query_norm:
        matched = False
        for value in candidates:
            if not value:
                continue
            if value == query_norm:
                score += 4.0
                matched = True
            elif query_norm in value:
                score += 2.5
                matched = True
            else:
                similarity = difflib.SequenceMatcher(None, query_norm, value).ratio()
                if similarity > 0.55:
                    score += similarity
                    matched = True
        if not matched and not auto_id_norm:
            score += 0.1  # small encouragement for loose matches
    else:
        score += 0.2

    score += max(0.0, 1.5 - entry.get("depth", 0) * 0.1)
    return score


def _format_metadata(metadata: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("title", "name", "auto_id", "control_type", "class_name", "selector"):
        value = metadata.get(key)
        if not value:
            continue
        if key in {"control_type", "class_name"}:
            parts.append(f"{key}={value}")
        else:
            parts.append(f'{key}="{value}"')
    return ", ".join(parts) if parts else "elemento"


def _build_suggestions(snapshot: List[Dict[str, Any]], limit: int = 5) -> str:
    suggestions: List[str] = []
    for entry in snapshot:
        label = entry.get("title") or entry.get("name") or entry.get("auto_id")
        if not label:
            continue
        suggestions.append(f"#{entry['index']} {label}")
        if len(suggestions) >= limit:
            break
    if suggestions:
        return "Suggerimenti: " + ", ".join(suggestions)
    return "Suggerimento: verifica che la finestra corretta sia attiva e che gli elementi siano visibili."

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


def element_id(
    query: str,
    *,
    control_type: Optional[str] = None,
    auto_id: Optional[str] = None,
    index: Optional[int] = None,
    exact: bool = False,
) -> str:
    """Return a reusable locator token for a UI element.

    Args:
        query: Text to search for (title, name, etc.). Accepts ``#42`` to reference an index from the UI tree.
        control_type: Optional control type filter (e.g., ``Button``).
        auto_id: Optional automation id filter.
        index: Optional 1-based index from the UI tree listing.
        exact: Require exact string matches when True.

    Returns:
        str: Message containing the generated locator token or an error description.
    """

    window = _get_active_window()
    if window is None:
        return "Errore: Nessuna finestra attiva trovata. Apri o attiva l'applicazione prima di continuare."

    snapshot = get_latest_ui_snapshot()
    if not snapshot or not snapshot[0].get("wrapper"):
        snapshot = refresh_ui_snapshot(window)

    query_norm = _normalize(query)
    control_type_norm = _normalize(control_type)
    auto_id_norm = _normalize(auto_id)

    resolved_index: Optional[int] = None
    if index and index > 0:
        resolved_index = index
    elif query_norm.startswith("#"):
        try:
            resolved_index = int(query_norm.lstrip("#"))
            query_norm = ""
        except ValueError:
            resolved_index = None

    candidates = snapshot
    if resolved_index:
        candidates = [entry for entry in snapshot if entry.get("index") == resolved_index]
        if not candidates:
            return f"Errore: Nessun elemento con indice #{resolved_index} trovato nella finestra corrente."

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for entry in candidates:
        score = _score_candidate(entry, query_norm, control_type_norm, auto_id_norm, exact)
        if score < 0:
            continue
        scored.append((score, entry))

    if not scored:
        suggestion = _build_suggestions(snapshot)
        return "Errore: Nessun elemento corrispondente trovato. " + suggestion

    scored.sort(key=lambda item: (-item[0], item[1].get("depth", 0), item[1].get("index", 0)))
    best_entry = scored[0][1]
    token, metadata = _store_locator(best_entry)
    descriptor = _format_metadata(metadata)

    response = (
        f"🔍 Locator generato: {token} -> {descriptor}. "
        "Usa questo valore con gli strumenti click, type_text o get_text."
    )

    if len(scored) > 1:
        alt_entry = scored[1][1]
        alt_label = alt_entry.get("title") or alt_entry.get("name") or alt_entry.get("auto_id") or f"indice #{alt_entry.get('index')}"
        response += f" Alternativa suggerita: index=#{alt_entry.get('index')} ({alt_label})."

    return response


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

    control, metadata = _resolve_control(window, element_id)
    if control is None:
        reason = metadata.get("error") if metadata else "Elemento non trovato."
        return f"Errore: Impossibile trovare o interagire con l'elemento '{element_id}'. Dettagli: {reason}"

    descriptor = _describe_target(metadata)

    try:
        wrapper = _prepare_wrapper(control)
        wrapper.click_input()
        logger.info("Successfully clicked %s (%s)", element_id, descriptor)
        return f"{descriptor.capitalize()} cliccato con successo."
    except Exception as exc:  # pragma: no cover - safety net for unexpected issues
        logger.error("Unexpected error while clicking %s: %s", descriptor, exc, exc_info=True)
        return f"Errore imprevisto durante il click su {descriptor}. Dettagli: {exc}"


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

    control, metadata = _resolve_control(window, element_id)
    if control is None:
        reason = metadata.get("error") if metadata else "Elemento non trovato."
        return f"Errore: Impossibile trovare o digitare in '{element_id}'. Dettagli: {reason}"

    descriptor = _describe_target(metadata)

    try:
        wrapper = _prepare_wrapper(control)
        wrapper.type_keys(text, with_spaces=True)
        logger.info("Successfully typed into %s (%s)", element_id, descriptor)
        return f"Testo '{text}' digitato con successo in {descriptor}."
    except Exception as exc:  # pragma: no cover - safety net for unexpected issues
        logger.error("Unexpected error while typing into %s: %s", descriptor, exc, exc_info=True)
        return f"Errore imprevisto durante la digitazione in {descriptor}. Dettagli: {exc}"


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

    control, metadata = _resolve_control(window, element_id)
    if control is None:
        reason = metadata.get("error") if metadata else "Elemento non trovato."
        return f"Errore: Impossibile recuperare testo da '{element_id}'. Dettagli: {reason}"

    descriptor = _describe_target(metadata)

    try:
        wrapper = _prepare_wrapper(control)
        text_value = _safe_attr(wrapper, "window_text")
        logger.info("Successfully retrieved text from %s (%s)", element_id, descriptor)
        return f"Testo recuperato da {descriptor}: '{text_value}'"
    except Exception as exc:  # pragma: no cover - safety net for unexpected issues
        logger.error("Unexpected error while retrieving text from %s: %s", descriptor, exc, exc_info=True)
        return f"Errore imprevisto durante il recupero del testo da {descriptor}. Dettagli: {exc}"


def scroll(direction: str, amount: int = 3) -> str:
    """
    Scroll in the active window.
    
    Args:
        direction: Direction to scroll ('up', 'down', 'left', 'right').
        amount: Number of scroll units (default: 3).
        
    Returns:
        A string message indicating the result.
    """
    import pyautogui
    
    try:
        logger.info(f"Scrolling {direction} by {amount} units")
        
        direction = direction.lower().strip()
        
        if direction in ['up', 'down']:
            # Positive for up, negative for down
            scroll_amount = amount if direction == 'up' else -amount
            pyautogui.scroll(scroll_amount)
            logger.info(f"Successfully scrolled {direction}")
            return f"Scroll {direction} di {amount} unità eseguito con successo."
        elif direction in ['left', 'right']:
            # Horizontal scroll using hscroll
            scroll_amount = -amount if direction == 'left' else amount
            pyautogui.hscroll(scroll_amount)
            logger.info(f"Successfully scrolled {direction}")
            return f"Scroll {direction} di {amount} unità eseguito con successo."
        else:
            error_msg = f"Direzione non valida: '{direction}'. Usa 'up', 'down', 'left', o 'right'."
            logger.warning(error_msg)
            return error_msg
            
    except Exception as e:
        error_msg = f"Errore durante lo scroll {direction}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def press_hotkey(keys: str) -> str:
    """
    Press a keyboard hotkey combination.
    
    Args:
        keys: Hotkey combination (e.g., 'ctrl+c', 'alt+tab', 'enter').
        
    Returns:
        A string message indicating the result.
    """
    import pyautogui
    import time
    
    try:
        logger.info(f"Pressing hotkey: {keys}")
        
        # Parse the keys (support both '+' and ' ' as separators)
        key_list = keys.replace('+', ' ').split()
        
        if len(key_list) == 1:
            # Single key press
            pyautogui.press(key_list[0])
            logger.info(f"Successfully pressed key: {key_list[0]}")
            return f"Tasto '{key_list[0]}' premuto con successo."
        else:
            # Key combination (e.g., ctrl+c)
            pyautogui.hotkey(*key_list)
            logger.info(f"Successfully pressed hotkey combination: {keys}")
            return f"Combinazione di tasti '{keys}' premuta con successo."
            
    except Exception as e:
        error_msg = f"Errore durante la pressione del tasto '{keys}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def finish_task(summary: str) -> str:
    """
    Signal that the agent has completed the requested task.
    
    Args:
        summary: A brief summary of what was accomplished.
        
    Returns:
        A string message confirming task completion.
    """
    logger.info(f"Task completed: {summary}")
    return f"✅ Task completato con successo: {summary}"


def double_click(element_id: str) -> str:
    """
    Double-click on a UI element identified by its ID.
    
    Args:
        element_id: The element identifier (e.g., 'element:abc123').
        
    Returns:
        A string message indicating the result.
    """
    window = _get_active_window()
    if not window:
        return "Errore: Impossibile accedere alla finestra attiva."

    control, metadata = _resolve_control(window, element_id)
    if not control:
        snapshot = refresh_ui_snapshot(window)
        suggestions = _build_suggestions(snapshot)
        return f"Errore: Elemento '{element_id}' non trovato o non più valido. {suggestions}"

    descriptor = _describe_target(metadata)
    try:
        wrapper = _prepare_wrapper(control)
        wrapper.double_click_input()
        logger.info("Successfully double-clicked %s (elemento '%s')", element_id, descriptor)
        return f"Elemento '{descriptor}' doppio-cliccato con successo."
    except Exception as exc:
        logger.error("Failed to double-click %s: %s", element_id, exc, exc_info=True)
        return f"Errore durante il doppio-click su '{descriptor}': {exc}"


def right_click(element_id: str) -> str:
    """
    Right-click on a UI element to open context menu.
    
    Args:
        element_id: The element identifier (e.g., 'element:abc123').
        
    Returns:
        A string message indicating the result.
    """
    window = _get_active_window()
    if not window:
        return "Errore: Impossibile accedere alla finestra attiva."

    control, metadata = _resolve_control(window, element_id)
    if not control:
        snapshot = refresh_ui_snapshot(window)
        suggestions = _build_suggestions(snapshot)
        return f"Errore: Elemento '{element_id}' non trovato o non più valido. {suggestions}"

    descriptor = _describe_target(metadata)
    try:
        wrapper = _prepare_wrapper(control)
        wrapper.right_click_input()
        logger.info("Successfully right-clicked %s (elemento '%s')", element_id, descriptor)
        return f"Click destro su elemento '{descriptor}' eseguito con successo."
    except Exception as exc:
        logger.error("Failed to right-click %s: %s", element_id, exc, exc_info=True)
        return f"Errore durante il click destro su '{descriptor}': {exc}"


def move_mouse(x: int, y: int) -> str:
    """
    Move the mouse cursor to specific screen coordinates.
    
    Args:
        x: The X coordinate on the screen.
        y: The Y coordinate on the screen.
        
    Returns:
        A string message indicating the result.
    """
    import pyautogui
    
    try:
        logger.info(f"Moving mouse to coordinates ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.5)
        logger.info(f"Successfully moved mouse to ({x}, {y})")
        return f"Mouse spostato alle coordinate ({x}, {y})."
    except Exception as e:
        error_msg = f"Errore durante lo spostamento del mouse a ({x}, {y}): {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def wait_seconds(seconds: int) -> str:
    """
    Wait for a specified number of seconds before continuing.
    
    Args:
        seconds: Number of seconds to wait (1-30).
        
    Returns:
        A string message indicating the result.
    """
    import time
    
    try:
        if seconds < 1 or seconds > 30:
            return "Errore: Il tempo di attesa deve essere tra 1 e 30 secondi."
        
        logger.info(f"Waiting for {seconds} seconds")
        time.sleep(seconds)
        logger.info(f"Wait completed after {seconds} seconds")
        return f"Attesa di {seconds} secondi completata."
    except Exception as e:
        error_msg = f"Errore durante l'attesa: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def minimize_window() -> str:
    """
    Minimize the currently active window.
    
    Returns:
        A string message indicating the result.
    """
    window = _get_active_window()
    if not window:
        return "Errore: Impossibile accedere alla finestra attiva."
    
    try:
        window.minimize()
        logger.info("Successfully minimized active window")
        return "Finestra attiva minimizzata con successo."
    except Exception as exc:
        logger.error("Failed to minimize window: %s", exc, exc_info=True)
        return f"Errore durante la minimizzazione della finestra: {exc}"


def maximize_window() -> str:
    """
    Maximize the currently active window.
    
    Returns:
        A string message indicating the result.
    """
    window = _get_active_window()
    if not window:
        return "Errore: Impossibile accedere alla finestra attiva."
    
    try:
        window.maximize()
        logger.info("Successfully maximized active window")
        return "Finestra attiva massimizzata con successo."
    except Exception as exc:
        logger.error("Failed to maximize window: %s", exc, exc_info=True)
        return f"Errore durante la massimizzazione della finestra: {exc}"


def close_window() -> str:
    """
    Close the currently active window.
    
    Returns:
        A string message indicating the result.
    """
    window = _get_active_window()
    if not window:
        return "Errore: Impossibile accedere alla finestra attiva."
    
    try:
        window.close()
        logger.info("Successfully closed active window")
        return "Finestra attiva chiusa con successo."
    except Exception as exc:
        logger.error("Failed to close window: %s", exc, exc_info=True)
        return f"Errore durante la chiusura della finestra: {exc}"


def copy_to_clipboard() -> str:
    """
    Copy selected text to clipboard using Ctrl+C.
    
    Returns:
        A string message indicating the result.
    """
    import pyautogui
    
    try:
        logger.info("Copying to clipboard with Ctrl+C")
        pyautogui.hotkey('ctrl', 'c')
        logger.info("Successfully executed Ctrl+C")
        return "Testo copiato negli appunti con Ctrl+C."
    except Exception as e:
        error_msg = f"Errore durante la copia negli appunti: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def paste_from_clipboard() -> str:
    """
    Paste text from clipboard using Ctrl+V.
    
    Returns:
        A string message indicating the result.
    """
    import pyautogui
    
    try:
        logger.info("Pasting from clipboard with Ctrl+V")
        pyautogui.hotkey('ctrl', 'v')
        logger.info("Successfully executed Ctrl+V")
        return "Testo incollato dagli appunti con Ctrl+V."
    except Exception as e:
        error_msg = f"Errore durante l'incolla dagli appunti: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def get_clipboard_text() -> str:
    """
    Get the current text content from the clipboard.
    
    Returns:
        The clipboard text content or an error message.
    """
    import pyperclip
    
    try:
        logger.info("Reading text from clipboard")
        text = pyperclip.paste()
        if text:
            logger.info(f"Successfully read {len(text)} characters from clipboard")
            return f"Contenuto appunti: {text}"
        else:
            return "Gli appunti sono vuoti o non contengono testo."
    except Exception as e:
        error_msg = f"Errore durante la lettura degli appunti: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def set_clipboard_text(text: str) -> str:
    """
    Set text content to the clipboard.
    
    Args:
        text: The text to copy to clipboard.
    
    Returns:
        A string message indicating the result.
    """
    import pyperclip
    
    try:
        logger.info(f"Setting clipboard text ({len(text)} characters)")
        pyperclip.copy(text)
        logger.info("Successfully set clipboard text")
        return f"Testo copiato negli appunti: '{text[:50]}{'...' if len(text) > 50 else ''}'"
    except Exception as e:
        error_msg = f"Errore durante l'impostazione degli appunti: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def start_application(app_name: str) -> str:
    """
    Start an application by name or path.
    
    Args:
        app_name: Name of the application (e.g., 'notepad', 'calc') or full path to executable.
        
    Returns:
        A string message indicating the result.
    """
    import subprocess
    
    try:
        logger.info(f"Starting application: {app_name}")
        subprocess.Popen(app_name, shell=True)
        logger.info(f"Successfully started application: {app_name}")
        return f"Applicazione '{app_name}' avviata con successo."
    except Exception as e:
        error_msg = f"Errore durante l'avvio dell'applicazione '{app_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def open_file(file_path: str) -> str:
    """
    Open a file with its default application.
    
    Args:
        file_path: Full path to the file to open.
        
    Returns:
        A string message indicating the result.
    """
    import os
    import subprocess
    
    try:
        logger.info(f"Opening file: {file_path}")
        if not os.path.exists(file_path):
            return f"Errore: Il file '{file_path}' non esiste."
        
        os.startfile(file_path)
        logger.info(f"Successfully opened file: {file_path}")
        return f"File '{file_path}' aperto con successo."
    except Exception as e:
        error_msg = f"Errore durante l'apertura del file '{file_path}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def open_url(url: str) -> str:
    """
    Open a URL in the default web browser.
    
    Args:
        url: The URL to open (e.g., 'https://www.google.com').
        
    Returns:
        A string message indicating the result.
    """
    import webbrowser
    
    try:
        logger.info(f"Opening URL: {url}")
        webbrowser.open(url)
        logger.info(f"Successfully opened URL: {url}")
        return f"URL '{url}' aperto nel browser predefinito."
    except Exception as e:
        error_msg = f"Errore durante l'apertura dell'URL '{url}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def take_screenshot(save_path: Optional[str] = None) -> str:
    """
    Take a screenshot and optionally save it to a file.
    
    Args:
        save_path: Optional path where to save the screenshot. If None, screenshot is not saved.
        
    Returns:
        A string message indicating the result.
    """
    import pyautogui
    from datetime import datetime
    
    try:
        logger.info("Taking screenshot")
        screenshot = pyautogui.screenshot()
        
        if save_path:
            screenshot.save(save_path)
            logger.info(f"Screenshot saved to: {save_path}")
            return f"Screenshot salvato in: {save_path}"
        else:
            # Save with timestamp if no path provided
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_path = f"screenshot_{timestamp}.png"
            screenshot.save(default_path)
            logger.info(f"Screenshot saved to: {default_path}")
            return f"Screenshot salvato in: {default_path}"
    except Exception as e:
        error_msg = f"Errore durante lo screenshot: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def switch_window(window_title: str) -> str:
    """
    Switch to a window by its title (partial match supported).
    
    Args:
        window_title: The title or partial title of the window to activate.
        
    Returns:
        A string message indicating the result.
    """
    from pywinauto import Desktop
    
    try:
        logger.info(f"Searching for window with title: {window_title}")
        desktop = Desktop(backend="uia")
        
        # Find windows matching the title
        windows = desktop.windows()
        matching_windows = [w for w in windows if window_title.lower() in w.window_text().lower()]
        
        if not matching_windows:
            return f"Errore: Nessuna finestra trovata con titolo contenente '{window_title}'."
        
        # Activate the first matching window
        target_window = matching_windows[0]
        target_window.set_focus()
        logger.info(f"Successfully switched to window: {target_window.window_text()}")
        return f"Finestra '{target_window.window_text()}' attivata con successo."
    except Exception as e:
        error_msg = f"Errore durante il cambio finestra '{window_title}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg

