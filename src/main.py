"""
Main entry point for the DjenisAiAgent application.

This module initializes the agent, loads configuration, and handles command-line arguments.
"""
import sys
import os
import argparse
import json
import logging
import time

# Add the parent directory to the path to allow importing src modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_core import AgentCore
from config import Config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Main")

def load_config(config_path=None):
    """
    Load configuration from file or create default configuration.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Configuration dictionary
    """
    if config_path and os.path.exists(config_path):
        try:
            config = Config(config_path)
            return config.settings
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            sys.exit(1)
    else:
        # Use default config path
        default_config_path = "config/default_config.json"
        if os.path.exists(default_config_path):
            try:
                config = Config(default_config_path)
                return config.settings
            except Exception as e:
                logger.error(f"Error loading default config: {str(e)}")
                sys.exit(1)
                
    # If no config file exists, create a default configuration
    logger.warning("No config file found, creating default configuration")
    return create_default_config()
    
def create_default_config():
    """
    Create and return a default configuration.
    
    Returns:
        Default configuration dictionary
    """
    default_config = {
        "general": {
            "debug_mode": False,
            "log_level": "INFO"
        },
        "memory": {
            "max_items": 100,
            "expiry_seconds": 3600,
            "task_storage_dir": "data/task_memory"
        },
        "perception": {
            "screenshot_dir": "data/screenshots",
            "ocr_enabled": True,
            "ui_detection_enabled": True
        },
        "gemini": {
            "api_key": os.environ.get("GEMINI_API_KEY", ""),
            "model_name": "gemini-pro-vision",
            "templates_path": "config/prompt_templates.json"
        },
        "mcp": {
            "host": "localhost",
            "port": 8080
        },
        "tools": {
            "input": {
                "safety_delay": 0.1
            }
        }
    }
    
    # Ensure config directory exists
    os.makedirs("config", exist_ok=True)
    
    # Save default config
    with open("config/default_config.json", 'w') as f:
        json.dump(default_config, f, indent=2)
        
    return default_config

def create_credentials_template():
    """Create a template for credentials file."""
    template = {
        "gemini_api_key": "YOUR_API_KEY_HERE"
    }
    
    # Ensure config directory exists
    os.makedirs("config", exist_ok=True)
    
    # Save template
    with open("config/credentials.json.template", 'w') as f:
        json.dump(template, f, indent=2)

def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(description='DjenisAiAgent - MCP Server Agent using Gemini AI')
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()
    
    # Set debug level if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    
    # Create credentials template if it doesn't exist
    if not os.path.exists("config/credentials.json.template"):
        create_credentials_template()
    
    # Load configuration
    config = load_config(args.config)
    
    # Apply command line overrides
    if args.debug:
        config["general"]["debug_mode"] = True
    
    # Create data directories
    os.makedirs(config["memory"].get("task_storage_dir", "data/task_memory"), exist_ok=True)
    os.makedirs(config["perception"].get("screenshot_dir", "data/screenshots"), exist_ok=True)
    
    # Initialize and start the agent
    try:
        logger.info("Initializing agent...")
        agent = AgentCore(config)
        
        logger.info("Starting agent...")
        
        # Create a demo task to showcase agent functionality
        test_task_id = agent.components["task_memory"].create_task(
            description="Demo task: Take a screenshot and analyze it",
            metadata={
                "action_type": "capture_screen",
                "parameters": {},
                "user_request": "Analyze what's on my screen"
            }
        )
        logger.info(f"Created demo task with ID: {test_task_id}")
        
        # Start the agent with a timeout
        import threading
        stop_event = threading.Event()
        
        def stop_after_timeout():
            time.sleep(30)  # Run for 30 seconds
            logger.info("Stopping agent after demo timeout")
            agent.stop()
            stop_event.set()
        
        timer_thread = threading.Thread(target=stop_after_timeout)
        timer_thread.daemon = True
        timer_thread.start()
        
        # Start the agent
        agent.start()
        
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
    except Exception as e:
        logger.error(f"Error running agent: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()