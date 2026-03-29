"""Core reasoning utilities for interacting with Google Gemini."""

from __future__ import annotations

import inspect
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from PIL import Image

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.generativeai import types as genai_types

from src.config import config

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



def _json_type_for_annotation(annotation: Any) -> str:
    """Map Python annotations to JSON schema types."""

    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
    }

    if annotation in mapping:
        return mapping[annotation]

    # Handle typing.Optional[X]
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if origin is Union and args:
        non_none = [arg for arg in args if arg is not type(None)]  # noqa: E721
        if len(non_none) == 1:
            return _json_type_for_annotation(non_none[0])

    return "string"


def _build_function_declaration(func: Any) -> Optional[genai_types.FunctionDeclaration]:
    """Create a FunctionDeclaration schema for a Python callable."""

    signature = inspect.signature(func)
    properties: Dict[str, Dict[str, Any]] = {}
    required: List[str] = []

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

        json_type = _json_type_for_annotation(param.annotation)
        properties[name] = {
            "type": json_type,
            "description": f"Parametro '{name}' per la funzione {func.__name__}.",
        }
        if param.default is inspect._empty:
            required.append(name)

    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters_schema["required"] = required

    try:
        return genai_types.FunctionDeclaration(
            name=func.__name__,
            description=inspect.getdoc(func) or "",
            parameters=parameters_schema,
        )
    except Exception as exc:  # pragma: no cover - schema construction issues
        logger.error(
            "Unable to build FunctionDeclaration for '%s': %s", func.__name__, exc
        )
        return None


def _prepare_tools_payload(available_tools: Iterable[Any]) -> List[genai_types.Tool]:
    """Convert Python callables into Gemini tool declarations."""

    declarations: List[genai_types.FunctionDeclaration] = []
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


def decide_next_action(
    screenshot_image: Image.Image,
    ui_tree: str,
    user_command: str,
    history: List[str],
    available_tools: List[Any]
) -> Union[Any, str]:
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
        # Prepare tool declarations for function calling
        tools_payload = _prepare_tools_payload(available_tools)
        if not tools_payload:
            return (
                "Errore: Nessun tool disponibile per la chiamata di funzioni. "
                "Verificare la configurazione dell'agente."
            )

        # Build a list of available tool names for validation
        available_tool_names = {
            decl.name for decl in tools_payload[0].function_declarations
        }
        logger.debug(f"Available tools: {sorted(available_tool_names)}")
        
        # Check if last action was deep_think to prevent consecutive usage
        last_action_was_deep_think = False
        if history:
            last_history_entry = history[-1]
            if "deep_think" in last_history_entry and "PENSIERO PROFONDO" in last_history_entry:
                last_action_was_deep_think = True
                logger.debug("Last action was deep_think, consecutive usage will be blocked")

        # Configure and initialize the Gemini model with Function Calling support
        logger.debug(f"Initializing Gemini model: {config.gemini_model_name}")
        
        # Configure the API key
        genai.configure(api_key=config.gemini_api_key)  # type: ignore[attr-defined]
        
        # Create the model with tools for Function Calling
        model = genai.GenerativeModel(  # type: ignore[attr-defined]
            model_name=config.gemini_model_name,
            tools=tools_payload,
            generation_config=genai.GenerationConfig(  # type: ignore[attr-defined]
                temperature=config.temperature,
                max_output_tokens=config.max_tokens,
            )
        )

        logger.debug("Model initialized with %d tools", len(tools_payload[0].function_declarations))
        
        # Inject configuration values into system prompt
        system_prompt_with_config = SYSTEM_PROMPT.replace(
            "{MAX_MOUSE_ATTEMPTS}", str(config.max_mouse_positioning_attempts)
        ).replace(
            "{MAX_LOOP_TURNS}", str(config.max_loop_turns)
        ).replace(
            "{ACTION_TIMEOUT}", str(config.action_timeout)
        )
        
        # Assemble the multimodal prompt in the correct order
        history_text = (
            "PREVIOUS STEPS:\n" + "\n".join(history[-config.max_loop_turns :])
            if history
            else "PREVIOUS STEPS:\n- None"
        )

        prompt_parts = [
            system_prompt_with_config,
            history_text,
            f"CURRENT OBJECTIVE: {user_command}",
            "STRUCTURAL UI ELEMENTS:\n" + ui_tree,
            screenshot_image,
        ]
        
        logger.info("Sending multimodal prompt to Gemini API")
        logger.debug("Prompt structure: %d parts", len(prompt_parts))

        # Call the Gemini API with retry logic for resilience
        response = None
        last_error = None
        
        for attempt in range(1, config.api_max_retries + 1):
            try:
                logger.debug(f"API call attempt {attempt}/{config.api_max_retries}")
                
                # Call the Gemini API
                # The API has its own internal timeout, we handle retries here
                response = model.generate_content(prompt_parts)
                
                logger.debug(f"Received response from Gemini API on attempt {attempt}")
                break  # Success, exit retry loop
                
            except google_exceptions.DeadlineExceeded as e:
                last_error = e
                logger.warning(
                    f"API timeout on attempt {attempt}/{config.api_max_retries}: {str(e)}"
                )
                
                if attempt < config.api_max_retries:
                    # Exponential backoff: 2s, 4s, 8s, etc.
                    delay = config.api_retry_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"API timeout after {config.api_max_retries} attempts")
                    return (
                        f"Errore: Timeout dell'API Gemini dopo {config.api_max_retries} tentativi. "
                        "Il prompt potrebbe essere troppo complesso o c'è un problema di rete. "
                        "Provo a semplificare l'azione."
                    )
                    
            except google_exceptions.ResourceExhausted as e:
                last_error = e
                logger.warning(
                    f"API rate limit on attempt {attempt}/{config.api_max_retries}: {str(e)}"
                )
                
                if attempt < config.api_max_retries:
                    # Longer delay for rate limits
                    delay = config.api_retry_delay * (3 ** attempt)
                    logger.info(f"Rate limited, retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"API rate limit after {config.api_max_retries} attempts")
                    return (
                        f"Errore: Limite di richieste API raggiunto. "
                        "Attendi qualche secondo prima di riprovare."
                    )
                    
            except (google_exceptions.ServiceUnavailable, google_exceptions.InternalServerError) as e:
                last_error = e
                logger.warning(
                    f"API service error on attempt {attempt}/{config.api_max_retries}: {str(e)}"
                )
                
                if attempt < config.api_max_retries:
                    delay = config.api_retry_delay * (2 ** (attempt - 1))
                    logger.info(f"Service unavailable, retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"API service error after {config.api_max_retries} attempts")
                    return (
                        f"Errore: Il servizio Gemini è temporaneamente non disponibile. "
                        "Riprova tra qualche minuto."
                    )
        
        # If we got here without a response, something went wrong
        if response is None:
            error_msg = f"Errore imprevisto durante la chiamata API: {last_error}"
            logger.error(error_msg)
            return error_msg
        
        # Process and return the response
        # Check if the response was blocked for safety reasons
        if not response.candidates:
            error_msg = "Errore: La risposta di Gemini è stata bloccata per motivi di sicurezza."
            logger.warning(error_msg)
            return error_msg
        
        candidate = response.candidates[0]
        
        # Check finish_reason for errors before processing
        finish_reason = getattr(candidate, "finish_reason", None)
        if finish_reason == 10:  # INVALID_FUNCTION_CALL
            error_msg = "Errore: Il modello ha generato una chiamata a funzione non valida. Riprovo..."
            logger.warning(error_msg)
            return error_msg
        
        # Check if response contains a function call
        if candidate.content.parts:
            for part in candidate.content.parts:
                function_call = getattr(part, "function_call", None)
                if function_call:
                    # VALIDATION: Check if the called function exists
                    if function_call.name not in available_tool_names:
                        error_msg = (
                            f"ERRORE TOOL NON VALIDO: Il modello ha tentato di chiamare '{function_call.name}' "
                            f"che NON ESISTE. Tool disponibili: {sorted(available_tool_names)}. "
                            "Devi chiamare SOLO tool dalla lista 'Available Tools' nel prompt di sistema. "
                            "NON inventare funzioni. Riprova."
                        )
                        logger.error(error_msg)
                        return error_msg
                    
                    # VALIDATION: Check for consecutive deep_think usage
                    if function_call.name == "deep_think" and last_action_was_deep_think:
                        error_msg = (
                            "ERRORE: Hai tentato di usare 'deep_think' consecutivamente. "
                            "Regola: deep_think puo essere usato SOLO UNA VOLTA, poi DEVI chiamare un tool di AZIONE. "
                            "Pattern corretto: deep_think (opzionale) -> azione (obbligatorio). "
                            "Riprova con un tool di azione dalla lista Available Tools."
                        )
                        logger.error(error_msg)
                        return error_msg
                    
                    logger.info("Model requested function call: %s", function_call.name)
                    logger.debug("Function arguments: %s", dict(function_call.args))
                    return function_call
        
        # If no function call, extract text response safely
        try:
            if hasattr(response, "text") and response.text:
                logger.warning("Model responded with text instead of function call - violates CRITICAL RULE")
                logger.debug(f"Response text: {response.text[:200]}...")
                return (
                    "ERRORE CRITICO: Hai risposto con SOLO TESTO invece di chiamare uno strumento. "
                    "Questo VIOLA la regola fondamentale: 'CRITICAL RULE: ALWAYS CALL A TOOL'. "
                    "Devi SEMPRE chiamare ESATTAMENTE UN TOOL ad ogni turno. "
                    "Se non sai cosa fare, usa `switch_window` sulla finestra corrente per osservare. "
                    "NON puoi semplicemente 'pensare' o 'osservare' senza un tool. Riprova ORA."
                )
        except ValueError:
            # response.text raised ValueError, try alternative extraction
            logger.debug("response.text not accessible, trying content.parts")

        if candidate.content.parts:
            text_parts = [getattr(part, "text", "") for part in candidate.content.parts]
            joined = "\n".join(filter(None, text_parts)).strip()
            if joined:
                logger.warning("Model provided textual response via content parts - violates CRITICAL RULE")
                return (
                    "ERRORE CRITICO: Hai risposto con SOLO TESTO invece di chiamare uno strumento. "
                    "Questo VIOLA la regola fondamentale: 'CRITICAL RULE: ALWAYS CALL A TOOL'. "
                    "Devi SEMPRE chiamare ESATTAMENTE UN TOOL ad ogni turno. "
                    "Se non sai cosa fare, usa `switch_window` sulla finestra corrente per osservare. "
                    "NON puoi semplicemente 'pensare' o 'osservare' senza un tool. Riprova ORA."
                )
        
        # Empty response case
        error_msg = (
            "Errore: Gemini ha restituito una risposta vuota. "
            "Devi chiamare ESATTAMENTE UN TOOL. Controlla la lista 'Available Tools' e riprova."
        )
        logger.warning(error_msg)
        return error_msg
        
    except google_exceptions.GoogleAPIError as e:
        error_msg = f"Errore API Google: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
        
    except ValueError as e:
        # Likely an API key or configuration issue
        error_msg = f"Errore di configurazione: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
        
    except Exception as e:
        # Catch-all for unexpected errors
        error_msg = f"Errore imprevisto durante la chiamata a Gemini: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
