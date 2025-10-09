"""
Main entry point for DjenisAiAgent.

This module serves as the application entry point, initializing the agent
and starting the main orchestration loop. It handles environment setup,
API configuration, and user interaction.
"""

import os
import sys
import logging
import argparse
from dotenv import load_dotenv
import google.generativeai as genai

from src.config import config
from src.orchestration.agent_loop import run_agent_loop


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """
    Main application entry point.
    
    This function handles:
    1. Environment variable loading from .env
    2. Gemini API key validation and configuration
    3. User command input (CLI or interactive loop)
    4. Agent loop execution
    """
    # Step 1: Load environment variables from .env file
    load_dotenv()
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="DjenisAiAgent - AI-powered Windows automation agent"
    )
    parser.add_argument(
        "command",
        type=str,
        nargs="?",
        default=None,
        help="Natural language command to execute (optional for interactive mode)"
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Run in headless mode (no interactive UI)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Force interactive mode with continuous command loop"
    )
    
    args = parser.parse_args()
    
    logger.info("DjenisAiAgent starting...")
    print("\n" + "="*80)
    print("  🤖 DjenisAiAgent - AI-Powered Windows Automation")
    print("="*80 + "\n")
    
    try:
        # Step 2: API Key Configuration and Validation
        # Retrieve and validate Gemini API key
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        if not gemini_api_key or gemini_api_key == "YOUR_API_KEY_HERE":
            raise ValueError(
                "La variabile d'ambiente GEMINI_API_KEY non è impostata. "
                "Configura il file .env con la tua chiave API di Gemini."
            )
        
        # Configure the Gemini SDK with the API key
        genai.configure(api_key=gemini_api_key)  # type: ignore[attr-defined]
        logger.info("Gemini API configured successfully")
        
        # Validate additional configuration
        config.validate()
        logger.info("Configuration validated successfully")
        logger.info(f"Using model: {config.gemini_model_name}")
        logger.info(f"Max loop turns: {config.max_loop_turns}")
        
        # Step 3: User Interaction - Interactive Loop or Single Command
        
        # If command provided via CLI and not forcing interactive mode
        if args.command and not args.interactive:
            user_command = args.command
            logger.info(f"Command provided via CLI: {user_command}")
            
            # Run the main agent loop
            logger.info(f"Starting agent loop with command: {user_command}")
            result = run_agent_loop(user_command)
            
            logger.info(f"Agent loop completed with result: {result}")
            print(f"\n{'='*80}")
            print(f"  Risultato finale: {result}")
            print(f"{'='*80}\n")
            
        else:
            # Interactive mode: Continuous command loop
            print("DjenisAiAgent Initialized. Ready for your commands.")
            print("Enter 'exit' or 'quit' to terminate the program.\n")
            
            # Continuous user interaction loop
            while True:
                try:
                    # Prompt user for command
                    user_command = input("Please enter your command (or 'exit' to quit): ").strip()
                    
                    # Check for exit commands (case-insensitive)
                    if user_command.lower() in ['exit', 'quit']:
                        print("\n👋 Arrivederci! Chiusura di DjenisAiAgent.\n")
                        logger.info("User requested exit")
                        break
                    
                    # Skip empty commands
                    if not user_command:
                        print("⚠️  Comando vuoto. Inserisci un comando valido.\n")
                        continue
                    
                    # Execute the command
                    logger.info(f"Starting agent loop with command: {user_command}")
                    result = run_agent_loop(user_command)
                    
                    logger.info(f"Agent loop completed with result: {result}")
                    print(f"\n{'='*80}")
                    print(f"  Risultato: {result}")
                    print(f"{'='*80}\n")
                    
                except KeyboardInterrupt:
                    print("\n\n⚠️  Interruzione rilevata. Usa 'exit' per uscire in modo pulito.\n")
                    continue
                    
                except Exception as e:
                    logger.error(f"Error during command execution: {e}", exc_info=True)
                    print(f"\n❌ Errore durante l'esecuzione: {e}\n")
                    print("Puoi provare un altro comando o digitare 'exit' per uscire.\n")
                    continue
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"\n❌ Errore di configurazione: {e}\n")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Agent interrupted by user")
        print("\n\n⚠️  Agente interrotto dall'utente.\n")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n❌ Errore imprevisto: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
