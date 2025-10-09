"""
Gemini Core Module

This module handles all interactions with the Google Gemini API for reasoning
and decision making. It implements the Function Calling pattern to ensure
structured, reliable responses from the model.
"""

from typing import List, Union, Any
import logging
from PIL import Image

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration
from google.api_core import exceptions as google_exceptions

from src.config import config

logger = logging.getLogger(__name__)

# System instruction that defines the agent's persona and behavior
SYSTEM_INSTRUCTION = """Sei un assistente esperto di Windows 11 chiamato MCP. Il tuo obiettivo è eseguire i comandi dell'utente interagendo con l'interfaccia grafica. Analizza lo screenshot e l'elenco degli elementi UI forniti. Usa esclusivamente gli strumenti a tua disposizione per compiere le azioni. Pensa passo dopo passo prima di decidere quale strumento chiamare. Se il compito è completato, chiama lo strumento 'finish_task'."""


def decide_next_action(
    screenshot_image: Image.Image,
    ui_tree: str,
    user_command: str,
    history: List[str],
    available_tools: List[Any]
) -> Union[genai.protos.FunctionCall, str]:
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
        # Configure and initialize the Gemini model with Function Calling support
        logger.debug(f"Initializing Gemini model: {config.gemini_model_name}")
        
        # Configure the API key
        genai.configure(api_key=config.gemini_api_key)
        
        # Create the model with tools for Function Calling
        model = genai.GenerativeModel(
            model_name=config.gemini_model_name,
            tools=available_tools,
            generation_config=genai.GenerationConfig(
                temperature=config.temperature,
                max_output_tokens=config.max_tokens,
            )
        )
        
        logger.debug(f"Model initialized with {len(available_tools)} tools")
        
        # Assemble the multimodal prompt in the correct order
        prompt_parts = [
            SYSTEM_INSTRUCTION,
            "\n\nEcco lo stato attuale dello schermo:",
            screenshot_image,
            "\n\nEcco gli elementi UI interagibili:",
            ui_tree,
            "\n\nCronologia precedente:",
            "\n".join(history) if history else "Nessuna cronologia disponibile.",
            f"\n\nObiettivo attuale: {user_command}"
        ]
        
        logger.info("Sending multimodal prompt to Gemini API")
        logger.debug(f"Prompt structure: {len(prompt_parts)} parts")
        
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
            first_part = candidate.content.parts[0]
            
            # Check if it's a function call
            if hasattr(first_part, 'function_call') and first_part.function_call:
                function_call = first_part.function_call
                logger.info(f"Model requested function call: {function_call.name}")
                logger.debug(f"Function arguments: {dict(function_call.args)}")
                return function_call
        
        # If no function call, extract text response
        if response.text:
            logger.info("Model responded with text instead of function call")
            logger.debug(f"Response text: {response.text[:100]}...")
            return response.text
        
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
