"""Core reasoning utilities for interacting with Google Gemini."""

from __future__ import annotations

import inspect
import logging
import time
import types
from collections.abc import Iterable
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from threading import Event
from typing import Any, Literal, Union, cast, get_args, get_origin, get_type_hints

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from PIL import Image

from src.config import config
from src.redaction import bounded_text, safe_preview

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — loaded from external file at module import time.
# This keeps the source file concise while the prompt remains editable
# without touching Python code.
# ---------------------------------------------------------------------------
_PROMPT_FILE = Path(__file__).parent / "system_prompt.txt"


def _load_system_prompt() -> str:
    """Load the system prompt template from disk, falling back to empty string."""
    try:
        return _PROMPT_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Could not load system prompt from %s: %s", _PROMPT_FILE, exc)
        return ""


SYSTEM_PROMPT: str = _load_system_prompt()


def _wait_before_retry(cancel_event: Event | None, delay: float) -> bool:
    """Wait for a retry delay and return True if cancellation was requested."""

    if cancel_event is not None:
        return cancel_event.wait(delay)
    time.sleep(delay)
    return False


def _generate_content(
    *,
    api_key: str,
    model: str,
    contents: list[Any],
    generation_config: Any,
    timeout_seconds: int,
) -> Any:
    http_options = genai_types.HttpOptions(timeout=timeout_seconds * 1000)
    with genai.Client(api_key=api_key, http_options=http_options) as client:
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=generation_config,
        )


def _generate_content_with_timeout(
    *,
    api_key: str,
    model: str,
    contents: list[Any],
    generation_config: Any,
    timeout_seconds: int,
) -> Any:
    return _generate_content(
        api_key=api_key,
        model=model,
        contents=contents,
        generation_config=generation_config,
        timeout_seconds=timeout_seconds,
    )


def _json_type_for_annotation(annotation: Any) -> str:
    """Map Python annotations to JSON schema types."""

    schema = _json_schema_for_annotation(annotation)
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        return schema_type
    variants = schema.get("anyOf", [])
    for variant in variants:
        if (
            isinstance(variant, dict)
            and isinstance(variant.get("type"), str)
            and variant["type"] != "null"
        ):
            return str(variant["type"])
    return "string"


def _json_schema_for_annotation(annotation: Any) -> dict[str, Any]:
    """Convert resolved Python type hints into a compact JSON schema."""

    mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
    }

    if annotation in mapping:
        return mapping[annotation].copy()

    if annotation in {Any, inspect.Parameter.empty}:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in {Union, types.UnionType}:
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1:
            return _json_schema_for_annotation(non_none[0])
        return {"anyOf": [_json_schema_for_annotation(arg) for arg in non_none]}

    if origin in {list, set, tuple}:
        item_type = args[0] if args else str
        return {"type": "array", "items": _json_schema_for_annotation(item_type)}

    if origin is dict:
        value_type = args[1] if len(args) == 2 else str
        return {
            "type": "object",
            "additionalProperties": _json_schema_for_annotation(value_type),
        }

    if origin is Literal:
        literal_values = list(args)
        literal_type = type(literal_values[0]) if literal_values else str
        return {**_json_schema_for_annotation(literal_type), "enum": literal_values}

    return {"type": "string"}


def _build_function_declaration(func: Any) -> genai_types.FunctionDeclaration | None:
    """Create a FunctionDeclaration schema for a Python callable."""

    signature = inspect.signature(func)
    try:
        resolved_hints = get_type_hints(func)
    except (NameError, TypeError):
        resolved_hints = {}
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []

    for name, param in signature.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            logger.warning(
                "Ignoring variadic parameter '%s' on tool '%s' for function calling.",
                name,
                func.__name__,
            )
            continue

        annotation = resolved_hints.get(name, param.annotation)
        properties[name] = {
            **_json_schema_for_annotation(annotation),
            "description": f"Argument '{name}' for tool '{func.__name__}'.",
        }
        if param.default is inspect._empty:
            required.append(name)

    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters_schema["required"] = required

    try:
        return genai_types.FunctionDeclaration(
            name=func.__name__,
            description=inspect.getdoc(func) or "",
            parameters_json_schema=parameters_schema,
        )
    except Exception as exc:  # pragma: no cover - schema construction issues
        logger.error("Unable to build FunctionDeclaration for '%s': %s", func.__name__, exc)
        return None


def _prepare_tools_payload(available_tools: Iterable[Any]) -> list[genai_types.Tool]:
    """Convert Python callables into Gemini tool declarations."""

    declarations: list[genai_types.FunctionDeclaration] = []
    for tool in available_tools:
        declaration = getattr(tool, "function_declaration", None)
        if declaration is not None:
            declarations.append(declaration)
            continue

        built = _build_function_declaration(tool)
        if built is not None:
            declarations.append(built)

    if not declarations:
        logger.error("No valid tool declarations available for Gemini model")
        return []

    return [genai_types.Tool(function_declarations=declarations)]


def _extract_api_error_code(exc: Exception) -> int | None:
    """Return the numeric status code exposed by the GenAI SDK, if present."""

    for attribute in ("code", "status_code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
    return None


def _is_invalid_function_call_finish_reason(finish_reason: Any) -> bool:
    """Detect finish reasons related to malformed or invalid tool calls."""

    if finish_reason is None:
        return False

    normalized = str(finish_reason).upper()
    if "FUNCTION_CALL" not in normalized:
        return False
    return any(token in normalized for token in ("INVALID", "MALFORMED", "UNEXPECTED"))


def decide_next_action(
    screenshot_image: Image.Image,
    ui_tree: str,
    user_command: str,
    history: list[str],
    available_tools: list[Any],
    cancel_event: Event | None = None,
) -> Any | str:
    """
    Decide the next action to take based on multimodal context.

    This is the core reasoning function that sends a multimodal prompt (image + text)
    to the Gemini API along with available tool definitions. The model uses Function
    Calling to respond with a structured action to execute.

    Args:
        screenshot_image: A Pillow Image object of the current screen state.
        ui_tree: A string containing the UI element hierarchy/structure.
        user_command: The user's objective/goal as a string.
        history: A list of strings representing previous thoughts and observations.
        available_tools: A list of Python functions the agent can call.

    Returns:
        Either a FunctionCall object (if model chose to call a tool) or a string
        (if model responded with text, asking for clarification, etc.).
    """
    try:
        if cancel_event is not None and cancel_event.is_set():
            return "Cancelled before the Gemini request."

        # Prepare tool declarations for function calling
        tools_payload = _prepare_tools_payload(available_tools)
        if not tools_payload:
            return (
                "Error: No tools are available for function calling. "
                "Check the runtime and permission configuration."
            )

        # Build a list of available tool names for validation
        declarations = getattr(tools_payload[0], "function_declarations", None) or []
        available_tool_names = {
            str(decl.name) for decl in declarations if getattr(decl, "name", None)
        }
        logger.debug(f"Available tools: {sorted(available_tool_names)}")

        # Thought and observation are stored as separate history entries. Inspect
        # both so a deep_think call cannot slip past the consecutive-call guard.
        recent_history = "\n".join(history[-2:])
        last_action_was_deep_think = "deep_think" in recent_history
        if last_action_was_deep_think:
            logger.debug("Last action was deep_think; blocking consecutive use")

        logger.debug("Preparing Google GenAI request for model: %s", config.gemini_model_name)

        # Inject configuration values into system prompt
        system_prompt_with_config = (
            SYSTEM_PROMPT.replace(
                "{MAX_MOUSE_ATTEMPTS}", str(config.max_mouse_positioning_attempts)
            )
            .replace("{MAX_LOOP_TURNS}", str(config.max_loop_turns))
            .replace("{ACTION_TIMEOUT}", str(config.action_timeout))
        )

        # Assemble the multimodal prompt in the correct order
        history_text = (
            "PREVIOUS STEPS:\n"
            + bounded_text(
                "\n".join(history[-config.max_loop_turns :]),
                config.prompt_history_max_chars,
            )
            if history
            else "PREVIOUS STEPS:\n- None"
        )

        prompt_parts = [
            system_prompt_with_config,
            history_text,
            f"CURRENT OBJECTIVE: {user_command}",
            "STRUCTURAL UI ELEMENTS:\n" + bounded_text(ui_tree, config.ui_tree_max_chars),
            screenshot_image,
        ]

        generation_config = genai_types.GenerateContentConfig(
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            tools=cast(list[Any], tools_payload),
        )

        logger.info("Sending multimodal prompt to Gemini API")
        logger.debug("Prompt structure: %d parts", len(prompt_parts))

        # Call the Gemini API with retry logic for resilience
        response = None
        last_error: Exception | None = None

        for attempt in range(1, config.api_max_retries + 1):
            if cancel_event is not None and cancel_event.is_set():
                return "Cancelled before the Gemini request."
            try:
                logger.debug(f"API call attempt {attempt}/{config.api_max_retries}")

                response = _generate_content_with_timeout(
                    api_key=config.gemini_api_key,
                    model=config.gemini_model_name,
                    contents=prompt_parts,
                    generation_config=generation_config,
                    timeout_seconds=config.api_timeout,
                )

                logger.debug(f"Received response from Gemini API on attempt {attempt}")
                break  # Success, exit retry loop

            except FuturesTimeoutError as e:
                last_error = e
                logger.warning(
                    "API timeout on attempt %d/%d after %ds",
                    attempt,
                    config.api_max_retries,
                    config.api_timeout,
                )
                if attempt < config.api_max_retries:
                    delay = config.api_retry_delay * (2 ** (attempt - 1))
                    logger.info("Retrying in %.1f seconds...", delay)
                    if _wait_before_retry(cancel_event, delay):
                        return "Cancelled while waiting to retry Gemini."
                    continue
                logger.error("API timeout after %d attempts", config.api_max_retries)
                return (
                    f"Error: Gemini timed out after {config.api_max_retries} attempts. "
                    "The network or upstream service may be unavailable."
                )

            except genai_errors.APIError as e:
                last_error = e
                error_code = _extract_api_error_code(e)
                error_text = str(e).lower()

                if (
                    error_code in {408, 504}
                    or "deadline" in error_text
                    or "timed out" in error_text
                ):
                    logger.warning(
                        "API timeout on attempt %d/%d: %s",
                        attempt,
                        config.api_max_retries,
                        e,
                    )
                    if attempt < config.api_max_retries:
                        delay = config.api_retry_delay * (2 ** (attempt - 1))
                        logger.info("Retrying in %.1f seconds...", delay)
                        if _wait_before_retry(cancel_event, delay):
                            return "Cancelled while waiting to retry Gemini."
                        continue
                    logger.error("API timeout after %d attempts", config.api_max_retries)
                    return (
                        f"Error: Gemini timed out after {config.api_max_retries} attempts. "
                        "The network or upstream service may be unavailable."
                    )

                if error_code == 429 or any(
                    token in error_text for token in ("resource exhausted", "rate limit", "quota")
                ):
                    logger.warning(
                        "API rate limit on attempt %d/%d: %s",
                        attempt,
                        config.api_max_retries,
                        e,
                    )
                    if attempt < config.api_max_retries:
                        delay = config.api_retry_delay * (3**attempt)
                        logger.info("Rate limited, retrying in %.1f seconds...", delay)
                        if _wait_before_retry(cancel_event, delay):
                            return "Cancelled while waiting to retry Gemini."
                        continue
                    logger.error("API rate limit after %d attempts", config.api_max_retries)
                    return "Error: Gemini rate limit reached. Wait before submitting another task."

                if error_code in {500, 502, 503} or any(
                    token in error_text
                    for token in ("service unavailable", "internal server error")
                ):
                    logger.warning(
                        "API service error on attempt %d/%d: %s",
                        attempt,
                        config.api_max_retries,
                        e,
                    )
                    if attempt < config.api_max_retries:
                        delay = config.api_retry_delay * (2 ** (attempt - 1))
                        logger.info("Service unavailable, retrying in %.1f seconds...", delay)
                        if _wait_before_retry(cancel_event, delay):
                            return "Cancelled while waiting to retry Gemini."
                        continue
                    logger.error("API service error after %d attempts", config.api_max_retries)
                    return "Error: Gemini is temporarily unavailable. Try again later."

                raise

        # If we got here without a response, something went wrong
        if response is None:
            error_msg = f"Unexpected Gemini API failure: {last_error}"
            logger.error(error_msg)
            return error_msg

        # Process and return the response
        # Check if the response was blocked for safety reasons
        if not response.candidates:
            error_msg = "Error: Gemini blocked the response for safety reasons."
            logger.warning(error_msg)
            return error_msg

        candidate = response.candidates[0]

        # Check finish_reason for errors before processing
        finish_reason = getattr(candidate, "finish_reason", None)
        if _is_invalid_function_call_finish_reason(finish_reason):
            error_msg = "Error: The model generated an invalid function call."
            logger.warning(error_msg)
            return error_msg

        response_function_calls = getattr(response, "function_calls", None) or []
        if response_function_calls:
            function_call = response_function_calls[0]
            if function_call.name not in available_tool_names:
                error_msg = (
                    f"INVALID TOOL: The model requested '{function_call.name}', which is not "
                    f"available. Available tools: {sorted(available_tool_names)}."
                )
                logger.error(error_msg)
                return error_msg

            if function_call.name == "deep_think" and last_action_was_deep_think:
                error_msg = (
                    "Error: deep_think cannot be called twice in a row. "
                    "Choose one available action tool."
                )
                logger.error(error_msg)
                return error_msg

            logger.info("Model requested function call: %s", function_call.name)
            logger.debug("Function arguments: %s", safe_preview(dict(function_call.args)))
            return function_call

        # Check if response contains a function call
        if candidate.content.parts:
            for part in candidate.content.parts:
                function_call = getattr(part, "function_call", None)
                if function_call:
                    # VALIDATION: Check if the called function exists
                    if function_call.name not in available_tool_names:
                        error_msg = (
                            f"INVALID TOOL: The model requested '{function_call.name}', which is "
                            f"not available. Available tools: {sorted(available_tool_names)}."
                        )
                        logger.error(error_msg)
                        return error_msg

                    # VALIDATION: Check for consecutive deep_think usage
                    if function_call.name == "deep_think" and last_action_was_deep_think:
                        error_msg = (
                            "Error: deep_think cannot be called twice in a row. "
                            "Choose one available action tool."
                        )
                        logger.error(error_msg)
                        return error_msg

                    logger.info("Model requested function call: %s", function_call.name)
                    logger.debug("Function arguments: %s", safe_preview(dict(function_call.args)))
                    return function_call

        # If no function call, extract text response safely
        try:
            if hasattr(response, "text") and response.text:
                logger.warning(
                    "Model responded with text instead of function call - violates CRITICAL RULE"
                )
                logger.debug("Response text: %s", safe_preview(response.text))
                return "TOOL CALL REQUIRED: The model returned text instead of one available tool call."
        except ValueError:
            # response.text raised ValueError, try alternative extraction
            logger.debug("response.text not accessible, trying content.parts")

        if candidate.content.parts:
            text_parts = [getattr(part, "text", "") for part in candidate.content.parts]
            joined = "\n".join(filter(None, text_parts)).strip()
            if joined:
                logger.warning(
                    "Model provided textual response via content parts - violates CRITICAL RULE"
                )
                return "TOOL CALL REQUIRED: The model returned text instead of one available tool call."

        # Empty response case
        error_msg = "Error: Gemini returned an empty response instead of one available tool call."
        logger.warning(error_msg)
        return error_msg

    except genai_errors.APIError as e:
        error_msg = f"Google API error: {e!s}"
        logger.error(error_msg, exc_info=True)
        return error_msg

    except ValueError as e:
        # Likely an API key or configuration issue
        error_msg = f"Configuration error: {e!s}"
        logger.error(error_msg, exc_info=True)
        return error_msg

    except Exception as e:
        # Catch-all for unexpected errors
        error_msg = f"Unexpected Gemini error: {e!s}"
        logger.error(error_msg, exc_info=True)
        return error_msg
