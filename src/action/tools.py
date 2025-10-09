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
