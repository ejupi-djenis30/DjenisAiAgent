"""Action tools used by the Windows automation agent."""

from __future__ import annotations

import difflib
import json
import logging
import re
import subprocess
import time
from collections import OrderedDict
from queue import Empty, Queue
from threading import Thread
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar
from uuid import uuid4

from pywinauto.application import Application
from pywinauto.findbestmatch import MatchError
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PywinautoTimeoutError

from src.perception.screen_capture import get_latest_ui_snapshot, refresh_ui_snapshot
from src.action import browser_tools

logger = logging.getLogger(__name__)

T = TypeVar('T')

_LOCATOR_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_LOCATOR_CACHE_LIMIT = 64


def _execute_with_timeout(func: Callable[[], T], timeout: float, default: Optional[T] = None) -> Optional[T]:
    """
    Execute a function in a separate thread with a timeout.
    
    This prevents pywinauto operations from blocking indefinitely when
    interacting with complex windows like browsers.
    
    Args:
        func: The function to execute
        timeout: Maximum time to wait in seconds
        default: Value to return if timeout is exceeded
        
    Returns:
        The function result, or default if timeout is exceeded
    """
    result_queue: Queue = Queue()
    
    def wrapper() -> None:
        try:
            result = func()
            result_queue.put(("success", result))
        except Exception as e:
            result_queue.put(("error", e))
    
    thread = Thread(target=wrapper, daemon=True)
    thread.start()
    
    try:
        status, value = result_queue.get(timeout=timeout)
        if status == "error":
            raise value
        return value
    except Empty:
        logger.warning(f"⏱️ Timeout di {timeout}s raggiunto durante operazione pywinauto")
        return default


def _normalize(value: Optional[str]) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _is_browser_window(window: Any) -> bool:
    """Check if the active window is a web browser."""
    try:
        window_title = _safe_attr(window, "window_text").lower()
        browser_keywords = ["chrome", "edge", "firefox", "opera", "brave", "safari"]
        return any(keyword in window_title for keyword in browser_keywords)
    except Exception:
        return False


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


def run_shell_command(command: str) -> str:
    """
    Executes a command in Windows PowerShell and returns its output.
    This is the PREFERRED method for file system operations, system queries,
    or any task that can be done via command line.

    Args:
        command: The PowerShell command to execute (e.g., "ls", "Get-Process").

    Returns:
        A JSON string with "stdout", "stderr", and "return_code".
    """
    logger.info("Executing shell command: %s", command)
    try:
        # Using PowerShell is more powerful on Windows
        # Timeout is crucial to prevent the agent from getting stuck
        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60,  # 60-second timeout
            encoding='utf-8',
            errors='ignore'
        )
        output = {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "return_code": result.returncode
        }
        logger.info("Shell command completed with return code %d", result.returncode)
        return json.dumps(output, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        logger.error("Shell command timed out: %s", command)
        return json.dumps({
            "stdout": "",
            "stderr": "Error: Command timed out after 60 seconds.",
            "return_code": -1
        })
    except Exception as e:
        logger.error("Error executing shell command '%s': %s", command, e)
        return json.dumps({
            "stdout": "",
            "stderr": f"Error: An unexpected error occurred: {e}",
            "return_code": -1
        })


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

    window_title = window.window_text()
    logger.info(f"Ricerca elemento limitata alla finestra attiva: '{window_title}'")

    snapshot = get_latest_ui_snapshot()
    # CRITICAL: Always refresh snapshot with the active window to ensure we're searching in the right context
    # This prevents finding elements from other windows/applications
    logger.debug(f"Refreshing UI snapshot for active window '{window_title}' with 8s timeout...")
    snapshot = _execute_with_timeout(
        lambda: refresh_ui_snapshot(window),
        timeout=8.0,
        default=[]
    )
    
    # If snapshot refresh timed out or failed, try browser fallback immediately
    if not snapshot:
        logger.warning(f"⏱️ UI snapshot refresh timed out or failed for query '{query}'")
        if _is_browser_window(window) and browser_tools.is_browser_available():
            logger.info(f"⚠️ Fallback diretto a Selenium per '{query}' (timeout pywinauto)")
            browser_result = browser_tools.browser_find_and_click(query)
            if "✅" in browser_result:
                return f"🔍 [Browser Mode] {browser_result}"
        return "Errore: Impossibile analizzare la finestra corrente (timeout). Se sei in un browser, assicurati che sia avviato con --remote-debugging-port=9222"

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
        # Try browser fallback if we're in a browser window
        if _is_browser_window(window) and browser_tools.is_browser_available():
            logger.info(f"⚠️ element_id fallito con pywinauto, tentativo con Selenium per '{query}'")
            browser_result = browser_tools.browser_find_and_click(query)
            if "✅" in browser_result:
                return f"🔍 [Browser Mode] {browser_result}"
        
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


def element_id_fast(query: str, control_type: Optional[str] = None, auto_id: Optional[str] = None) -> str:
    """
    Fast element search using pywinauto's native find methods.
    Falls back to slower snapshot search if direct search fails.
    
    Args:
        query: The text, name, or title to search for.
        control_type: Optional control type filter.
        auto_id: Optional automation_id filter.
        
    Returns:
        A locator string 'element:<uuid>' or an error message.
    """
    window = _get_active_window()
    if not window:
        return "Error: No active window set. Use 'switch_window' first."

    logger.info("Fast search for element '%s' in window: '%s'", query, window.window_text())

    # Strategy 1: Fast, direct search using pywinauto's native finders
    try:
        search_criteria: Dict[str, Any] = {"top_level_only": False}
        if control_type:
            search_criteria["control_type"] = control_type
        if auto_id:
            search_criteria["auto_id"] = auto_id
        
        # Try regex search for flexible matching
        search_criteria["title_re"] = f".*{re.escape(query)}.*"
        
        found_control = window.child_window(**search_criteria)
        if found_control.exists(timeout=2):
            # Build metadata similar to snapshot format
            elem_info = found_control.element_info
            metadata = {
                "title": elem_info.name,
                "name": elem_info.name,
                "auto_id": elem_info.automation_id,
                "control_type": elem_info.control_type,
                "class_name": elem_info.class_name,
                "depth": 0,
                "index": 0,
            }
            token, stored_meta = _store_locator(metadata)
            descriptor = _format_metadata(stored_meta)
            logger.info("Fast search succeeded: %s", descriptor)
            return f"🔍 Locator generato (fast): {token} -> {descriptor}. Usa questo valore con gli strumenti click, type_text o get_text."
    except (ElementNotFoundError, AttributeError, IndexError, Exception) as e:
        logger.info("Fast search failed (%s), falling back to snapshot search", type(e).__name__)

    # Strategy 2: Fallback to slower snapshot search
    logger.info("Fallback: Searching through UI snapshot.")
    return element_id(query, control_type=control_type, auto_id=auto_id)


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
        # Try browser fallback if we're in a browser window
        if _is_browser_window(window) and browser_tools.is_browser_available():
            logger.info(f"⚠️ click fallito con pywinauto, tentativo con Selenium per '{element_id}'")
            browser_result = browser_tools.browser_find_and_click(element_id)
            if "✅" in browser_result:
                return f"[Browser Mode] {browser_result}"
        
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


def press_key_repeat(key: str, times: int) -> str:
    """Press a single special key multiple times. Ideal for actions like deleting multiple characters.

    Args:
        key: The name of the special key to press (e.g., 'backspace', 'delete', 'enter').
        times: The number of times to press the key (positive integer).

    Returns:
        A string message indicating the result.
    """
    import pyautogui
    
    SPECIAL_KEYS = [
        'enter', 'return', 'esc', 'escape', 'tab', 'space', 'backspace', 'delete', 'del',
        'up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown', 'pgup', 'pgdn',
        'insert', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
        'ctrl', 'alt', 'shift', 'win', 'cmd', 'command', 'option',
        'capslock', 'numlock', 'scrolllock', 'pause', 'printscreen', 'prtsc'
    ]
    
    key_lower = key.lower().strip()

    if key_lower not in SPECIAL_KEYS:
        return f"❌ Invalid key: '{key}'. Must be a special key like 'backspace', 'delete', 'enter', etc."
    if not isinstance(times, int) or times < 1:
        return f"❌ Invalid times: '{times}'. Must be a positive integer."

    try:
        logger.info(f"Pressing key '{key}' {times} times")
        for i in range(times):
            pyautogui.press(key_lower)
            time.sleep(0.05)
            if i % 10 == 0 and i > 0:  # Log progress for large operations
                logger.debug(f"Pressed '{key}' {i}/{times} times")
        return f"✅ Successfully pressed key '{key}' {times} times."
    except Exception as e:
        logger.error(f"Error while pressing key '{key}' repeatedly: {e}", exc_info=True)
        return f"❌ Error while pressing key '{key}' repeatedly: {e}"


def press_keys(keys: List[str]) -> str:
    """Press a sequence of keys. Context-aware tool that adapts behavior based on active window.
    
    CALCULATOR MODE (auto-detected):
    - If Calculator is active, clicks buttons by name for 100% reliability
    - Symbols are automatically translated: '+' -> 'più', '*' -> 'moltiplicazione', '=' -> 'uguale'
    - Immune to keyboard layout issues
    
    GENERIC MODE (all other apps):
    - Uses keyboard simulation with layout-agnostic typing
    - For text/characters: uses pyautogui.write() for reliability
    - For special keys (enter, esc, tab, etc.): uses pyautogui.press()
    
    Args:
        keys: List of strings where each is either:
              - Digits/text: '34', 'hello', '34+98'
              - Operators: '+', '-', '*', '/', '='
              - Special keys: 'enter', 'esc', 'tab', 'backspace', 'c', 'ce'
              - Functions: 'sqrt' (square root)

    Returns:
        A descriptive status message.
    """
    import pyautogui

    # Step 1: Detect active window
    is_calculator = False
    active_window = None
    try:
        app = Application(backend="uia").connect(active_only=True, timeout=1)
        active_window = app.top_window()
        window_title = active_window.window_text()
        is_calculator = bool(re.match(r".*(Calcolatrice|Calculator).*", window_title, re.IGNORECASE))
        logger.debug(f"Active window: '{window_title}', Calculator mode: {is_calculator}")
    except (ElementNotFoundError, RuntimeError, Exception) as e:
        logger.debug(f"Could not detect active window, using generic mode: {e}")
        is_calculator = False

    # Step 2: Calculator-Specific Logic (Button Clicking)
    if is_calculator and active_window:
        # Mapping from standard symbols to Calculator button names
        # Supports both Italian and English Windows versions
        # The agent uses standard English symbols; this map handles localization
        BUTTON_MAP = {
            # Digits
            "0": ["Zero", "0"], "1": ["Uno", "One", "1"], "2": ["Due", "Two", "2"], 
            "3": ["Tre", "Three", "3"], "4": ["Quattro", "Four", "4"],
            "5": ["Cinque", "Five", "5"], "6": ["Sei", "Six", "6"], 
            "7": ["Sette", "Seven", "7"], "8": ["Otto", "Eight", "8"], "9": ["Nove", "Nine", "9"],
            # Basic Operators
            "+": ["Più", "Plus", "Add"], "-": ["Meno", "Minus", "Subtract"], 
            "*": ["Moltiplicazione", "Multiply by", "Multiply"], 
            "/": ["Divisione", "Divide by", "Divide"],
            "=": ["Uguale", "Equals"], "enter": ["Uguale", "Equals"],
            # Decimal
            ".": ["Separatore decimale", "Decimal separator"], 
            ",": ["Separatore decimale", "Decimal separator"],
            # Clear/Delete Functions
            "c": ["Cancella", "Clear"], "escape": ["Cancella", "Clear"], 
            "ce": ["Cancella voce", "Clear entry"],
            "backspace": ["Backspace"],
            # Advanced Functions (Scientific Calculator)
            "sqrt": ["Radice quadrata", "Square root"],
            "x^2": ["Quadrato", "Square", "x²"],
            "x^y": ["x elevato alla y", "x to the power of y", "x^y"],
            "1/x": ["Reciproco", "Reciprocal"],
            "%": ["Percentuale", "Percent"],
            "+/-": ["Più meno", "Plus minus", "Positive negative"],
            # Parentheses
            "(": ["Parentesi aperta", "Open parenthesis", "Left parenthesis"],
            ")": ["Parentesi chiusa", "Close parenthesis", "Right parenthesis"],
            # Trigonometric (common in scientific mode)
            "sin": ["Seno", "Sine"],
            "cos": ["Coseno", "Cosine"],
            "tan": ["Tangente", "Tangent"],
            "ln": ["Logaritmo naturale", "Natural log"],
            "log": ["Logaritmo", "Log"],
            "exp": ["Esponenziale", "Exponential"],
            "pi": ["Pi", "π"],
            "e": ["e"],
            # Memory Functions
            "ms": ["Salva in memoria", "Memory store"],
            "mr": ["Richiama memoria", "Memory recall"],
            "mc": ["Cancella memoria", "Memory clear"],
            "m+": ["Aggiungi a memoria", "Memory add"],
            "m-": ["Sottrai da memoria", "Memory subtract"],
        }
        
        clicked_buttons = []
        last_sequence = ""
        
        try:
            # Process each element in the keys list
            for key_sequence in keys:
                last_sequence = key_sequence
                key_lower = key_sequence.lower().strip()
                
                # STEP 1: Check if the entire sequence is a special command (e.g., 'sqrt', 'sin', 'ms')
                # This must be checked FIRST before iterating through characters
                if key_lower in BUTTON_MAP:
                    button_names = BUTTON_MAP[key_lower]
                    button_clicked = False
                    
                    # Try each possible button name for this command
                    for button_name in button_names:
                        try:
                            button = active_window.child_window(
                                title_re=f"(?i)^{re.escape(button_name)}$",
                                control_type="Button"
                            )
                            button.click_input()
                            clicked_buttons.append(key_sequence)
                            logger.info(f"Calculator: Clicked command button '{button_name}' for '{key_sequence}'")
                            time.sleep(0.08)
                            button_clicked = True
                            break
                        except ElementNotFoundError:
                            continue  # Try next alternative
                    
                    if not button_clicked:
                        error_msg = f"❌ Calculator button not found for command '{key_sequence}'. Tried names: {button_names}"
                        logger.error(error_msg)
                        return error_msg
                
                # STEP 2: Otherwise, iterate through each character (for multi-digit numbers like '34')
                else:
                    for char in str(key_sequence):
                        char_lower = char.lower()
                        
                        # Get possible button names for this character
                        button_names = BUTTON_MAP.get(char_lower, [char])
                        if not isinstance(button_names, list):
                            button_names = [button_names]
                        
                        # Try each possible button name
                        button_clicked = False
                        for button_name in button_names:
                            try:
                                button = active_window.child_window(
                                    title_re=f"(?i)^{re.escape(button_name)}$",
                                    control_type="Button"
                                )
                                button.click_input()
                                clicked_buttons.append(char)
                                logger.debug(f"Calculator: Clicked digit button '{button_name}' for '{char}'")
                                time.sleep(0.05)
                                button_clicked = True
                                break
                            except ElementNotFoundError:
                                continue
                        
                        if not button_clicked:
                            error_msg = f"❌ Calculator button not found for character '{char}'. Tried names: {button_names}"
                            logger.error(error_msg)
                            return error_msg
            
            result_msg = f"✅ Calculator input successful: {''.join(clicked_buttons)}"
            logger.info(result_msg)
            return result_msg
            
        except Exception as e:
            error_msg = f"❌ Error clicking calculator buttons: {e}"
            if 'last_sequence' in locals() and last_sequence:
                error_msg += f". Last sequence: '{last_sequence}'"
            logger.error(error_msg, exc_info=True)
            return error_msg

    # Step 3: Generic Logic for All Other Applications (Keyboard Simulation)
    else:
        SPECIAL_KEYS = [
            'enter', 'return', 'esc', 'escape', 'tab', 'space', 'backspace', 'delete', 'del',
            'up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown', 'pgup', 'pgdn',
            'insert', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
            'ctrl', 'alt', 'shift', 'win', 'cmd', 'command', 'option',
            'capslock', 'numlock', 'scrolllock', 'pause', 'printscreen', 'prtsc'
        ]
        
        try:
            if not keys:
                return "❌ Error: No keys provided for press_keys."

            logger.info("Pressing key sequence (generic mode): %s", keys)

            for key_item in keys:
                key_lower = key_item.lower().strip()
                
                # Check if it's a special key
                if key_lower in SPECIAL_KEYS:
                    pyautogui.press(key_lower)
                    logger.debug(f"Pressed special key: {key_item}")
                else:
                    # Type it as text for better keyboard layout compatibility
                    pyautogui.write(key_item, interval=0.05)
                    logger.debug(f"Typed text: {key_item}")
                
                time.sleep(0.05)  # Small delay between keys

            logger.info("Successfully pressed key sequence: %s", keys)
            return f"✅ Successfully pressed key sequence: {keys}"
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error pressing key sequence %s: %s", keys, exc, exc_info=True)
            return f"❌ Error pressing key sequence {keys}: {exc}"


def hotkey(keys: str) -> str:
    """Press a hotkey combination like 'ctrl+c' or 'alt+tab'.

    Args:
        keys: Combination expressed with '+', such as 'ctrl+shift+esc'.

    Returns:
        A descriptive status message.
    """
    import pyautogui

    try:
        logger.info("Pressing hotkey combination: %s", keys)
        parts = [part.strip() for part in keys.split("+") if part.strip()]
        if not parts:
            return "Error: No keys provided for hotkey."

        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)

        logger.info("Successfully pressed hotkey combination: %s", keys)
        return f"Hotkey combination '{keys}' pressed successfully."
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error pressing hotkey %s: %s", keys, exc, exc_info=True)
        return f"Error pressing hotkey '{keys}': {exc}"


def browser_search(query: str, search_term: str) -> str:
    """
    Search within a website by finding the search bar and typing.
    
    This is a specialized tool for browser interactions that bypasses pywinauto
    limitations when interacting with web content. Use this when you need to
    search within a website (e.g., YouTube, Google, Amazon).
    
    Args:
        query: Search bar identifier (e.g., 'search', 'cerca', 'ricerca')
        search_term: Text to search for
        
    Returns:
        A string message indicating success or failure.
    """
    window = _get_active_window()
    if window is None:
        return "Errore: Nessuna finestra attiva trovata."
    
    if not _is_browser_window(window):
        return "⚠️ Questo strumento funziona solo all'interno di un browser. Usa type_text per altre applicazioni."
    
    if not browser_tools.is_browser_available():
        return "❌ Selenium non disponibile. Avvia il browser con --remote-debugging-port=9222"
    
    logger.info(f"🔍 Browser search: cercando '{query}' per digitare '{search_term}'")
    result = browser_tools.browser_find_and_type(query, search_term, press_enter=True)
    return result


def deep_think(reasoning: str) -> str:
    """
    Take time for deeper analysis and reasoning about a complex situation.
    
    Use this tool when you need extended reasoning to analyze complex decisions,
    multiple failure scenarios, ambiguous UI states, or intricate navigation paths.
    
    CRITICAL RULES:
    - Can only be used ONCE before an action tool
    - CANNOT be used consecutively
    - After using this, you MUST call an action tool in the next turn
    - Pattern: deep_think (optional) -> action (mandatory)
    
    Args:
        reasoning: Your detailed thought process analyzing the situation, considering
                  alternatives, weighing trade-offs, and planning the best approach.
        
    Returns:
        A confirmation message that your reasoning has been recorded.
        
    Example:
        deep_think("Analyzing the current UI state: I see three menu items but previous 
                   click attempts failed. Option 1: Try keyboard shortcut Alt+F for File menu.
                   Option 2: Look for toolbar icons instead. Option 3: Right-click for context menu.
                   Best approach: Alt+F is most reliable for accessing File menu across applications.")
    """
    logger.info("Deep thinking engaged for complex reasoning")
    logger.debug(f"Reasoning content (first 200 chars): {reasoning[:200]}...")
    
    # Return a message that will be added to history
    return f"PENSIERO PROFONDO registrato: {reasoning}"


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
    
    COORDINATE SYSTEM (Screen Space - Origin at TOP-LEFT):
    - X-axis: Horizontal position (0 = left edge, increases going RIGHT)
    - Y-axis: Vertical position (0 = top edge, increases going DOWN)
    
    NAVIGATION GUIDE:
    - Target is ABOVE cursor (North): DECREASE Y (e.g., y - 50)
    - Target is BELOW cursor (South): INCREASE Y (e.g., y + 50)
    - Target is LEFT of cursor (West): DECREASE X (e.g., x - 50)
    - Target is RIGHT of cursor (East): INCREASE X (e.g., x + 50)
    - Diagonal adjustments: modify BOTH X and Y
      * North-East: x + value, y - value
      * South-East: x + value, y + value
      * South-West: x - value, y + value
      * North-West: x - value, y - value
    
    IMPORTANT: This is a LAST RESORT tool. Only use when:
    - element_id and element_id_fast have BOTH failed multiple times
    - You cannot interact with the UI through any other means
    - You must use the mouse positioning mini-loop protocol
    
    Mini-Loop Protocol:
    1. Call move_mouse with initial coordinates from screenshot analysis
    2. Call verify_mouse_position to check position
    3. Analyze screenshot to see where cursor is relative to target
    4. Calculate adjustment using coordinate system above
    5. Call move_mouse again with adjusted coordinates
    6. Repeat until verify_mouse_position confirms correct positioning
    7. Call confirm_mouse_position to EXIT mini-loop
    8. In NEXT turn (outside mini-loop), call click or other action tool
    
    Args:
        x: The X coordinate on the screen (horizontal, 0 = left).
        y: The Y coordinate on the screen (vertical, 0 = top).
        
    Returns:
        A string message indicating the result.
    """
    import pyautogui
    
    try:
        # Convert parameters to integers (function calling may pass strings)
        x_coord = int(x)
        y_coord = int(y)
        
        logger.info(f"Moving mouse to coordinates ({x_coord}, {y_coord})")
        pyautogui.moveTo(x_coord, y_coord, duration=0.5)
        logger.info(f"Successfully moved mouse to ({x_coord}, {y_coord})")
        return f"Mouse moved to coordinates ({x_coord}, {y_coord}). Use verify_mouse_position to confirm accuracy before clicking."
    except ValueError as e:
        error_msg = f"Error: Invalid coordinates x={x}, y={y}. Must be integers. Details: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error moving mouse to ({x}, {y}): {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def verify_mouse_position() -> str:
    """
    Get the current mouse cursor position for verification.
    
    Use this tool in the mouse positioning mini-loop to verify the mouse
    position and determine if adjustment is needed.
    
    AFTER CALLING THIS:
    1. Check screenshot to see cursor location relative to target
    2. If cursor is NOT on target:
       - Estimate pixel distance needed (up/down/left/right)
       - Use move_mouse with adjusted coordinates
       - Call verify_mouse_position again
    3. If cursor IS on target:
       - Call confirm_mouse_position to EXIT mini-loop
       - Next turn you can use click/double_click/right_click
    
    Returns:
        A string with current mouse coordinates.
    """
    import pyautogui
    
    try:
        x, y = pyautogui.position()
        logger.info(f"Current mouse position: ({x}, {y})")
        return f"MOUSE POSITION VERIFIED: Current position is ({x}, {y}). Analyze the screenshot to confirm this is the correct location. If correct, proceed with click. If not, adjust with move_mouse."
    except Exception as e:
        error_msg = f"Error getting mouse position: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def confirm_mouse_position() -> str:
    """
    Confirm that the mouse is correctly positioned and EXIT the mini-loop.
    
    CRITICAL: Only call this when you have visually verified in the screenshot
    that the mouse cursor is EXACTLY on the target element.
    
    This tool does NOT perform a click. It only exits the mouse positioning mini-loop.
    After exiting, you will be in the next normal turn where you can call:
    - click(element_id) for normal UI elements
    - double_click(element_id) for double-click actions  
    - right_click(element_id) for context menus
    - Or any other action tool
    
    Returns:
        A confirmation message that mini-loop has ended.
    """
    import pyautogui
    
    try:
        x, y = pyautogui.position()
        logger.info(f"Mouse position confirmed at ({x}, {y}), exiting mini-loop")
        return f"MOUSE POSITION CONFIRMED at ({x}, {y}). Mini-loop exited. You are now in the next turn. Use click, double_click, or other action tools to interact with the element at this position."
    except Exception as e:
        error_msg = f"Error confirming mouse position: {str(e)}"
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

        logger.info("Waiting for %s seconds", seconds)
        time.sleep(seconds)
        logger.info("Wait completed after %s seconds", seconds)
        return f"Attesa di {seconds} secondi completata."
    except Exception as exc:  # pragma: no cover - defensive logging
        error_msg = f"Errore durante l'attesa: {exc}"
        logger.error(error_msg, exc_info=True)
        return error_msg


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


def read_clipboard() -> str:
    """
    Read the current text content from the clipboard.
    
    Returns:
        The clipboard text content or an error message.
    """
    import pyperclip
    
    try:
        logger.info("Reading text from clipboard")
        text = pyperclip.paste()
        if text:
            logger.info(f"Successfully read {len(text)} characters from clipboard")
            return f"Clipboard content: {text}"
        else:
            return "Clipboard is empty or contains no text."
    except Exception as e:
        error_msg = f"Error reading clipboard: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def get_clipboard_text() -> str:
    """
    Deprecated: Use read_clipboard() instead.
    Get the current text content from the clipboard.
    
    Returns:
        The clipboard text content or an error message.
    """
    logger.warning("get_clipboard_text is deprecated, use read_clipboard instead")
    return read_clipboard()


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
    Start an application by name or path without waiting for it to be ready.
    This is a non-blocking operation. Use 'switch_window' in the next turn
    to focus the application's window once it appears.
    
    Args:
        app_name: Name of the application (e.g., 'notepad', 'calc') or full path to executable.
        
    Returns:
        A string message indicating the result.
    """
    import subprocess
    
    logger.info(f"Issuing command to start application: {app_name}")
    try:
        # Use Popen for a non-blocking call
        # DETACHED_PROCESS flag allows the process to run independently
        subprocess.Popen(
            app_name,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True
        )
        logger.info(f"Successfully issued start command for '{app_name}'")
        return f"Start command issued for '{app_name}'. Use 'switch_window' in the next turn to focus it."
        
    except FileNotFoundError:
        error_msg = f"Application '{app_name}' not found in system PATH."
        logger.error(error_msg)
        return f"Error: {error_msg}"
    except Exception as e:
        error_msg = f"Error starting application '{app_name}': {str(e)}"
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


def focus_window(window_title: str) -> str:
    """
    Find a window by its title (can be a partial match) and bring it to the foreground.
    This is useful if the desired window is open but not currently active.
    
    Args:
        window_title: The title or partial title of the window to focus.
        
    Returns:
        A string message indicating the result.
    """
    logger.info(f"Attempting to focus window with title: '{window_title}'")
    try:
        app = Application(backend="uia").connect(title_re=f".*{window_title}.*", timeout=10)
        main_window = app.top_window()
        main_window.set_focus()
        focused_title = main_window.window_text()
        logger.info(f"Successfully focused window: '{focused_title}'")
        return f"Finestra '{focused_title}' portata in primo piano con successo."
    except ElementNotFoundError:
        logger.error(f"Window with title containing '{window_title}' not found.")
        return f"❌ Errore: Nessuna finestra trovata con il titolo '{window_title}'."
    except Exception as e:
        logger.error(f"Failed to focus window '{window_title}': {e}")
        return f"❌ Errore: Impossibile mettere a fuoco la finestra '{window_title}': {e}"


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
            return f"Error: No window found with title containing '{window_title}'."
        
        # Activate the first matching window
        target_window = matching_windows[0]
        target_window.set_focus()
        time.sleep(0.05)  # Minimal delay for focus to take effect
        logger.info(f"Successfully switched to window: {target_window.window_text()}")
        return f"Successfully activated window '{target_window.window_text()}'."
    except Exception as e:
        error_msg = f"Error switching to window '{window_title}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def list_files(directory_path: str = ".") -> str:
    """
    List files and directories in the specified path.
    
    Args:
        directory_path: The directory path to list (default: current directory).
        
    Returns:
        A formatted list of files and directories or an error message.
    """
    import os
    from pathlib import Path
    
    try:
        path = Path(directory_path).expanduser().resolve()
        
        if not path.exists():
            return f"Error: Path '{directory_path}' does not exist."
        
        if not path.is_dir():
            return f"Error: Path '{directory_path}' is not a directory."
        
        logger.info(f"Listing files in: {path}")
        
        items = []
        for item in sorted(path.iterdir()):
            if item.is_dir():
                items.append(f"[DIR]  {item.name}")
            else:
                size_kb = item.stat().st_size / 1024
                items.append(f"[FILE] {item.name} ({size_kb:.1f} KB)")
        
        if not items:
            return f"Directory '{path}' is empty."
        
        result = f"Contents of '{path}':\n" + "\n".join(items)
        logger.info(f"Successfully listed {len(items)} items in {path}")
        return result
        
    except PermissionError:
        error_msg = f"Error: Permission denied to access '{directory_path}'."
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error listing files in '{directory_path}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def read_file(file_path: str) -> str:
    """
    Read the content of a text file.
    
    Args:
        file_path: The path to the file to read.
        
    Returns:
        The file content or an error message.
    """
    from pathlib import Path
    
    try:
        path = Path(file_path).expanduser().resolve()
        
        if not path.exists():
            return f"Error: File '{file_path}' does not exist."
        
        if not path.is_file():
            return f"Error: Path '{file_path}' is not a file."
        
        # Check file size to avoid reading huge files
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > 5:
            return f"Error: File '{file_path}' is too large ({size_mb:.1f} MB). Maximum size is 5 MB."
        
        logger.info(f"Reading file: {path}")
        
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'cp1252']
        content = None
        
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    content = f.read()
                logger.info(f"Successfully read file with {encoding} encoding")
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            return f"Error: Could not decode file '{file_path}' with standard encodings."
        
        return f"Content of '{path.name}':\n{content}"
        
    except PermissionError:
        error_msg = f"Error: Permission denied to read '{file_path}'."
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error reading file '{file_path}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def write_file(file_path: str, content: str) -> str:
    """
    Write text content to a file. Creates the file if it doesn't exist, overwrites if it does.
    
    Args:
        file_path: The path to the file to write.
        content: The text content to write to the file.
        
    Returns:
        A confirmation message or an error message.
    """
    from pathlib import Path
    
    try:
        path = Path(file_path).expanduser().resolve()
        
        # Create parent directories if they don't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Writing to file: {path}")
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        size_kb = path.stat().st_size / 1024
        logger.info(f"Successfully wrote {size_kb:.1f} KB to {path}")
        return f"Successfully wrote {len(content)} characters to '{path}'."
        
    except PermissionError:
        error_msg = f"Error: Permission denied to write to '{file_path}'."
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error writing to file '{file_path}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg

