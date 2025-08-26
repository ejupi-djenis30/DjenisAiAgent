import os
import time
import json
import threading
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AgentCore")

class AgentCore:
    """
    Main class for the MCP Server Agent that coordinates all components and implements
    the core agent functionality to automate UI tasks in Windows 11.
    """
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the agent with configuration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.components = {}
        self.running = False
        self.paused = False
        self.last_error = None
        self.current_task = None
        self.screenshot_path = None
        
        # Initialize components
        self._initialize_components()
        
        logger.info("Agent initialized")
        
    def _initialize_components(self):
        """Initialize all agent components."""
        try:
            # Initialize memory components
            from memory.short_term_memory import ShortTermMemory
            from memory.task_memory import TaskMemory
            
            self.components["short_term_memory"] = ShortTermMemory(
                max_items=self.config.get("memory", {}).get("max_items", 100),
                expiry_seconds=self.config.get("memory", {}).get("expiry_seconds")
            )
            
            self.components["task_memory"] = TaskMemory(
                storage_dir=self.config.get("memory", {}).get("task_storage_dir", "task_memory")
            )
            
            # Initialize perception components
            from perception.screen_analyzer import ScreenAnalyzer
            from perception.win11_capture import Win11Capture
            
            self.components["screen_capture"] = Win11Capture(
                screenshot_dir=self.config.get("perception", {}).get("screenshot_dir", "screenshots")
            )
            
            self.components["screen_analyzer"] = ScreenAnalyzer(
                ocr_enabled=self.config.get("perception", {}).get("ocr_enabled", True),
                ui_detection_enabled=self.config.get("perception", {}).get("ui_detection_enabled", True)
            )
            
            # Initialize planning components
            from planning.planner import Planner
            
            self.components["planner"] = Planner(
                short_term_memory=self.components["short_term_memory"],
                task_memory=self.components["task_memory"]
            )
            
            # Initialize tools
            from tools.win11_input import Win11InputTool
            from tools.mcp_tool import MCPTool
            
            self.components["input_tool"] = Win11InputTool(
                safety_delay=self.config.get("tools", {}).get("input", {}).get("safety_delay", 0.1)
            )
            
            self.components["mcp_tool"] = MCPTool(
                host=self.config.get("mcp", {}).get("host", "localhost"),
                port=self.config.get("mcp", {}).get("port", 8080)
            )
            
            # Initialize AI components
            from gemini.client import GeminiClient
            from gemini.prompt_manager import PromptManager
            
            gemini_api_key = self.config.get("gemini", {}).get("api_key")
            if not gemini_api_key:
                # Look for API key in environment
                gemini_api_key = os.environ.get("GEMINI_API_KEY")
                if not gemini_api_key:
                    logger.warning("Gemini API key not found in config or environment")
                
            self.components["gemini_client"] = GeminiClient(
                api_key=gemini_api_key,
                model_name=self.config.get("gemini", {}).get("model_name", "gemini-pro-vision")
            )
            
            self.components["prompt_manager"] = PromptManager(
                templates_path=self.config.get("gemini", {}).get("templates_path")
            )
            
            # Register action handlers with the planner
            self._register_actions()
            
            logger.info("All components initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing components: {str(e)}", exc_info=True)
            self.last_error = str(e)
            raise
    
    def _register_actions(self):
        """Register available actions with the planner."""
        from planning.schemas import ActionSchema
        
        # Input actions
        self.components["planner"].register_action(
            ActionSchema(
                action_id="click",
                description="Click at specified coordinates",
                required_parameters=["x", "y"],
                optional_parameters=["button", "clicks"]
            )
        )
        
        self.components["planner"].register_action(
            ActionSchema(
                action_id="type_text",
                description="Type the specified text",
                required_parameters=["text"],
                optional_parameters=["interval"]
            )
        )
        
        self.components["planner"].register_action(
            ActionSchema(
                action_id="key_press",
                description="Press specified key or key combination",
                required_parameters=["key"],
                optional_parameters=["duration"]
            )
        )
        
        self.components["planner"].register_action(
            ActionSchema(
                action_id="scroll",
                description="Scroll the screen",
                required_parameters=["amount"],
                optional_parameters=["x", "y"]
            )
        )
        
        # Perception actions
        self.components["planner"].register_action(
            ActionSchema(
                action_id="capture_screen",
                description="Capture the current screen",
                required_parameters=[],
                optional_parameters=["region", "save"]
            )
        )
        
        self.components["planner"].register_action(
            ActionSchema(
                action_id="analyze_screen",
                description="Analyze the current screen",
                required_parameters=[],
                optional_parameters=["screenshot_path"]
            )
        )
        
        # Wait action
        self.components["planner"].register_action(
            ActionSchema(
                action_id="wait",
                description="Wait for specified seconds",
                required_parameters=["seconds"],
                optional_parameters=[]
            )
        )
        
    def start(self):
        """Start the agent."""
        if self.running:
            logger.warning("Agent already running")
            return
        
        self.running = True
        logger.info("Agent started")
        
        try:
            self._main_loop()
        except KeyboardInterrupt:
            logger.info("Agent stopped by user")
        except Exception as e:
            logger.error(f"Error in agent main loop: {str(e)}", exc_info=True)
            self.last_error = str(e)
        finally:
            self.running = False
            
    def stop(self):
        """Stop the agent."""
        self.running = False
        logger.info("Agent stopped")
        
    def pause(self):
        """Pause the agent."""
        self.paused = True
        logger.info("Agent paused")
        
    def resume(self):
        """Resume the agent."""
        self.paused = False
        logger.info("Agent resumed")
        
    def _main_loop(self):
        """Main agent loop."""
        while self.running:
            try:
                if self.paused:
                    time.sleep(1)
                    continue
                    
                # Process any pending tasks
                self._process_next_task()
                
                # Sleep to prevent CPU hogging
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}", exc_info=True)
                self.last_error = str(e)
                time.sleep(5)  # Sleep longer after error
                
    def _process_next_task(self):
        """Process the next task in queue."""
        # Check if we have any active tasks
        task_memory = self.components["task_memory"]
        active_tasks = task_memory.get_active_tasks()
        
        if not active_tasks:
            # No active tasks, check for user input or create a monitoring task
            return
            
        # Get the next task
        task = active_tasks[0]
        self.current_task = task
        
        logger.info(f"Processing task: {task.description}")
        
        # Execute the task based on its type
        # This is a simplified implementation - in a real agent,
        # you would have more sophisticated task handling
        try:
            # Capture the current screen
            screenshot = self.components["screen_capture"].capture_screen()
            self.screenshot_path = self.components["screen_capture"].save_capture(screenshot)
            
            # Analyze the screen
            screen_analysis = self.components["screen_analyzer"].analyze(screenshot)
            
            # Extract high-level information
            extracted_info = self.components["screen_analyzer"].extract_information(screen_analysis)
            
            # Make a decision based on the analysis
            decision = self.components["screen_analyzer"].make_decision(extracted_info)
            
            # Execute the decision
            self._execute_decision(decision)
            
            # Mark task step as completed
            task_memory.add_task_step(
                task.task_id,
                f"Executed decision: {decision['action_type']}",
                result=decision
            )
            
        except Exception as e:
            logger.error(f"Error processing task: {str(e)}", exc_info=True)
            self.last_error = str(e)
            
            # Mark task step as failed
            task_memory.add_task_step(
                task.task_id,
                "Error processing task",
                result={"error": str(e)}
            )
            
    def _execute_decision(self, decision: Dict[str, Any]):
        """Execute a decision made by the screen analyzer."""
        action_type = decision.get("action_type")
        parameters = decision.get("parameters", {})
        
        logger.info(f"Executing decision: {action_type} with parameters {parameters}")
        
        # Execute the appropriate action
        if action_type == "click":
            x = parameters.get("x", 0)
            y = parameters.get("y", 0)
            self.components["input_tool"].simulate_mouse_click(x, y)
        elif action_type == "type_text":
            text = parameters.get("text", "")
            self.components["input_tool"].type_text(text)
        elif action_type == "key_press" or action_type == "escape_key":
            key = parameters.get("key", "escape")
            self.components["input_tool"].simulate_key_press(key)
        elif action_type == "wait":
            time.sleep(parameters.get("seconds", 1))
        elif action_type == "report":
            logger.info(f"Report: {parameters.get('message', '')}")
        else:
            logger.warning(f"Unknown action type: {action_type}")
            
    def process_user_request(self, request: str):
        """
        Process a user request using Gemini AI.
        
        Args:
            request: The user's request
            
        Returns:
            The AI's response and actions
        """
        try:
            # Capture current screen
            screenshot = self.components["screen_capture"].capture_screen()
            screenshot_path = self.components["screen_capture"].save_capture(screenshot)
            
            # Analyze screen for context
            screen_analysis = self.components["screen_analyzer"].analyze(screenshot)
            extracted_info = self.components["screen_analyzer"].extract_information(screen_analysis)
            
            # Get context for the prompt
            context = {
                "current_app": extracted_info.get("screen_state", "unknown"),
                "recent_actions": [],  # Could fetch from task history
                "user_request": request
            }
            
            # Format prompt using template
            prompt = self.components["prompt_manager"].format_prompt(
                "screen_analysis", 
                context
            )
            
            # Send to Gemini
            gemini_response = self.components["gemini_client"].send_request(
                prompt=prompt,
                images=[screenshot_path]
            )
            
            # Process the response
            processed_response = self.components["gemini_client"].handle_response(gemini_response)
            
            # Store in memory
            self.components["short_term_memory"].store(
                f"user_request_{time.time()}",
                {
                    "request": request,
                    "response": processed_response,
                    "screenshot": screenshot_path
                }
            )
            
            # Execute any actions in the response
            for action in processed_response.get("actions", []):
                action_type = action.get("type")
                parameters = action.get("parameters", {})
                
                # Create a task for the action
                self.components["task_memory"].create_task(
                    description=f"Execute action: {action_type}",
                    metadata={
                        "action_type": action_type,
                        "parameters": parameters,
                        "user_request": request
                    }
                )
                
            return processed_response
            
        except Exception as e:
            logger.error(f"Error processing user request: {str(e)}", exc_info=True)
            self.last_error = str(e)
            return {"error": str(e)}
            
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the agent.
        
        Returns:
            Dictionary with status information
        """
        return {
            "running": self.running,
            "paused": self.paused,
            "last_error": self.last_error,
            "current_task": self.current_task.to_dict() if self.current_task else None,
            "screenshot": self.screenshot_path,
            "timestamp": datetime.now().isoformat()
        }