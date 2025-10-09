"""
Agent Loop Module

This module contains the main orchestration loop that coordinates perception,
reasoning, and action execution using the ReAct (Reason+Act) paradigm.
"""

import logging
from typing import List, Dict, Callable, Any

from src.perception.screen_capture import get_multimodal_context
from src.reasoning.gemini_core import decide_next_action
from src.action import tools as action_tools
from src.config import config

logger = logging.getLogger(__name__)


def run_agent_loop(user_command: str) -> str:
    """
    Execute the main ReAct agent loop to fulfill a user command.
    
    This function implements the core ReAct cycle:
    1. Observe: Capture screen state and UI structure
    2. Reason: Use Gemini to decide next action
    3. Act: Execute the chosen action
    4. Verify: Record observation and update history
    
    The loop continues until the task is completed or max turns is reached.
    
    Args:
        user_command: The user's natural language command to execute.
        
    Returns:
        str: Final status message indicating success or failure.
    """
    # ===== INITIALIZATION =====
    history: List[str] = []  # Store conversation and action log
    task_completed: bool = False  # Track task completion status
    
    # Use config for max turns with fallback
    MAX_TURNS: int = config.max_loop_turns
    
    # Map tool names to actual functions from action module
    AVAILABLE_TOOLS: Dict[str, Callable] = {
        "click": action_tools.click,
        "type_text": action_tools.type_text,
        "get_text": action_tools.get_text,
        "scroll": action_tools.scroll,
        "press_hotkey": action_tools.press_hotkey,
        "finish_task": action_tools.finish_task,
    }
    
    logger.info(f"Starting agent loop for command: {user_command}")
    logger.info(f"Maximum turns: {MAX_TURNS}")
    print(f"\n{'='*80}")
    print(f"🤖 AVVIO AGENTE - Comando: {user_command}")
    print(f"{'='*80}\n")
    
    # ===== MAIN REACT LOOP =====
    for turn in range(1, MAX_TURNS + 1):
        # Check if task is already completed
        if task_completed:
            success_msg = f"✅ Task completato con successo al turno {turn - 1}!"
            logger.info(success_msg)
            print(f"\n{success_msg}\n")
            break
        
        print(f"\n--- TURNO {turn}/{MAX_TURNS} ---\n")
        logger.info(f"Starting turn {turn}/{MAX_TURNS}")
        
        # ===== STEP A: OBSERVE (Perception) =====
        try:
            logger.debug("Capturing multimodal context (screenshot + UI tree)")
            screenshot, ui_tree = get_multimodal_context()
            
            print("📸 PERCEZIONE: Screenshot e albero UI catturati.")
            logger.info("Perception: Successfully captured screen and UI tree")
            logger.debug(f"UI tree length: {len(ui_tree)} characters")
            
        except Exception as e:
            error_msg = f"Errore durante la percezione: {str(e)}"
            logger.error(error_msg, exc_info=True)
            print(f"❌ {error_msg}")
            # Add error to history and continue to allow recovery
            history.append(f"ERRORE PERCEZIONE: {error_msg}")
            continue
        
        # ===== STEP B: REASON (Call Gemini) =====
        try:
            logger.debug("Calling Gemini API for next action decision")
            
            # Convert tool functions to list for Gemini
            tool_functions = list(AVAILABLE_TOOLS.values())
            
            response = decide_next_action(
                screenshot_image=screenshot,
                ui_tree=ui_tree,
                user_command=user_command,
                history=history,
                available_tools=tool_functions
            )
            
            logger.info("Reasoning: Received response from Gemini")
            
        except Exception as e:
            error_msg = f"Errore durante il ragionamento: {str(e)}"
            logger.error(error_msg, exc_info=True)
            print(f"❌ {error_msg}")
            history.append(f"ERRORE RAGIONAMENTO: {error_msg}")
            continue
        
        # ===== STEP C: ACT (Dispatch the Action) =====
        observation: str = ""
        
        try:
            # Try to extract FunctionCall from response
            if hasattr(response, 'name') and hasattr(response, 'args'):
                # Response is a FunctionCall object
                tool_name = response.name
                tool_args = dict(response.args)
                
                print(f"🧠 PENSIERO: Il modello ha deciso di chiamare lo strumento '{tool_name}'")
                print(f"   Argomenti: {tool_args}")
                logger.info(f"Action: Dispatching tool '{tool_name}' with args: {tool_args}")
                
                # Special handling for finish_task
                if tool_name == "finish_task":
                    task_completed = True
                    summary = tool_args.get("summary", "Task completato")
                    observation = f"✅ TASK COMPLETATO: {summary}"
                    print(f"\n{observation}\n")
                    logger.info(f"Task marked as completed: {summary}")
                    
                    # Add to history and continue to trigger loop exit
                    history.append(f"PENSIERO: finish_task chiamato")
                    history.append(observation)
                    continue
                
                # Look up the tool function
                if tool_name not in AVAILABLE_TOOLS:
                    observation = f"Errore: Strumento '{tool_name}' non trovato nei tool disponibili."
                    logger.error(observation)
                    print(f"❌ {observation}")
                else:
                    # Execute the tool function with unpacked arguments
                    tool_function = AVAILABLE_TOOLS[tool_name]
                    try:
                        observation = tool_function(**tool_args)
                        logger.info(f"Action: Tool '{tool_name}' executed, result: {observation[:100]}")
                    except TypeError as e:
                        observation = f"Errore: Argomenti non validi per '{tool_name}'. Dettagli: {str(e)}"
                        logger.error(observation)
                    except Exception as e:
                        observation = f"Errore durante l'esecuzione di '{tool_name}': {str(e)}"
                        logger.error(observation, exc_info=True)
            
            else:
                # Response is text (model asking for clarification or providing commentary)
                observation = str(response)
                print(f"💬 PENSIERO: Il modello ha risposto con del testo:")
                print(f"   {observation}")
                logger.info(f"Action: Model responded with text instead of function call")
        
        except Exception as e:
            observation = f"Errore durante il dispatch dell'azione: {str(e)}"
            logger.error(observation, exc_info=True)
            print(f"❌ {observation}")
        
        # ===== STEP D: VERIFY & UPDATE HISTORY (Feedback) =====
        print(f"👁️  OSSERVAZIONE: {observation}")
        
        # Update history with thought and observation for next iteration
        if hasattr(response, 'name'):
            history.append(f"PENSIERO: Chiamato {response.name} con {dict(response.args)}")
        else:
            history.append(f"PENSIERO: {str(response)[:200]}")
        
        history.append(f"OSSERVAZIONE: {observation}")
        
        logger.debug(f"History updated, total entries: {len(history)}")
    
    # ===== HANDLE LOOP TERMINATION =====
    if not task_completed:
        failure_msg = f"⚠️  L'agente non è riuscito a completare il task entro {MAX_TURNS} turni."
        logger.warning(failure_msg)
        print(f"\n{failure_msg}\n")
        return f"FALLITO: Task non completato dopo {MAX_TURNS} turni"
    
    return "SUCCESSO: Task completato"
