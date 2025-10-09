"""Core reasoning utilities for interacting with Google Gemini."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, Iterable, List, Optional, Union

from PIL import Image

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.generativeai import types as genai_types

from src.config import config

logger = logging.getLogger(__name__)

# System instruction that defines the agent's persona and behavior
SYSTEM_PROMPT = """<system_prompt>
    <persona>
        You are DjenisAiAgent, a helpful and expert AI assistant for Windows 11. Your purpose is to execute user commands by interacting with the Graphical User Interface (GUI). You operate in a strict, iterative cycle: Observe, Reason, Act.
    </persona>

    <goal>
        Your primary goal is to accurately and efficiently achieve the user's stated objective. Analyze the provided screenshot for visual context and the UI element list for structural information to decide on the best next action.
    </goal>

    <rules>
        1.  **Chain of Thought:** You MUST reason step-by-step before acting. In your thought process, break down the problem, state your hypothesis for the next action, and then select a tool. This is a form of Chain-of-Thought prompting that helps in debugging and transparency[cite: 1202, 1207].
        2.  **Tool Exclusivity:** You can ONLY interact with the system using the provided tools. Do not invent actions or assume you can perform actions for which no tool is available.
        3.  **Completion:** Once the user's objective is fully completed, you MUST call the `finish_task` tool to end the operation.
        4.  **Efficiency:** When possible, prefer using keyboard shortcuts (`press_hotkey` tool) over a sequence of mouse clicks, as they are more reliable and efficient[cite: 1277, 1279]. For example, use Ctrl+S to save instead of clicking the 'File' then 'Save' menu items[cite: 1281].
    </rules>

    <constraints>
        1.  You are forbidden from performing destructive actions (like deleting files or shutting down the system) unless explicitly and unambiguously instructed by the user in the current command.
        2.  You must not interact with financial, security, or password management applications unless it is the explicit goal of the user's command.
        3.  If an action fails, analyze the observation and the new screenshot to understand the error and formulate a new plan. Do not repeat the same failed action more than twice[cite: 1143].
    </constraints>
</system_prompt>"""


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
        
        # Assemble the multimodal prompt in the correct order
        history_text = (
            "PREVIOUS STEPS:\n" + "\n".join(history[-config.max_loop_turns :])
            if history
            else "PREVIOUS STEPS:\n- None"
        )

        prompt_parts = [
            SYSTEM_PROMPT,
            history_text,
            f"CURRENT OBJECTIVE: {user_command}",
            "STRUCTURAL UI ELEMENTS:\n" + ui_tree,
            screenshot_image,
        ]
        
        logger.info("Sending multimodal prompt to Gemini API")
        logger.debug("Prompt structure: %d parts", len(prompt_parts))

        # Call the Gemini API with the assembled prompt
        response = model.generate_content(prompt_parts)
        
        logger.debug(f"Received response from Gemini API")
        
        # Process and return the response
        # Check if the response was blocked for safety reasons
        if not response.candidates:
            error_msg = "Errore: La risposta di Gemini è stata bloccata per motivi di sicurezza."
            logger.warning(error_msg)
            return error_msg
        
        candidate = response.candidates[0]
        
        # Check if response contains a function call
        if candidate.content.parts:
            for part in candidate.content.parts:
                function_call = getattr(part, "function_call", None)
                if function_call:
                    logger.info("Model requested function call: %s", function_call.name)
                    logger.debug("Function arguments: %s", dict(function_call.args))
                    return function_call
        
        # If no function call, extract text response
        if getattr(response, "text", None):
            logger.info("Model responded with text instead of function call")
            logger.debug(f"Response text: {response.text[:100]}...")
            return response.text

        if candidate.content.parts:
            text_parts = [getattr(part, "text", "") for part in candidate.content.parts]
            joined = "\n".join(filter(None, text_parts)).strip()
            if joined:
                logger.info("Model provided textual response via content parts")
                return joined
        
        # Empty response case
        error_msg = "Errore: Gemini ha restituito una risposta vuota."
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
