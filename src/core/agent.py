"""Enhanced AI Agent with improved architecture and UI overlay."""

import time
from typing import Dict, Any, List, Optional
from datetime import datetime
import keyboard

from logger import setup_logger
from config import config
from src.core.gemini_client import EnhancedGeminiClient
from src.core.executor import ActionExecutor
from src.core.ui_overlay import get_overlay
from ui_automation import UIAutomationEngine

logger = setup_logger("EnhancedAgent")


class EnhancedAIAgent:
    """Enhanced AI Agent for Windows UI automation with improved architecture."""
    
    def __init__(self, use_ui: bool = True):
        """Initialize the enhanced AI agent.
        
        Args:
            use_ui: Whether to show the overlay UI
        """
        logger.info("Initializing Enhanced AI Agent...")
        
        try:
            config.validate_config()
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            raise
        
        # Initialize components
        self.gemini = EnhancedGeminiClient()
        self.ui = UIAutomationEngine()
        self.executor = ActionExecutor(self.ui)
        
        # UI Overlay
        self.use_ui = use_ui
        self.overlay = None
        if use_ui:
            self.overlay = get_overlay()
            self.overlay.start()
            time.sleep(0.5)  # Give UI time to initialize
            self.overlay.add_log("Agent initialized", "INFO")
            self.overlay.update_status("🟢 Ready")
        
        # State management
        self.current_task: Optional[str] = None
        self.task_plan: Optional[Dict[str, Any]] = None
        self.execution_history: List[Dict[str, Any]] = []
        self.is_running: bool = False
        self.task_start_time: Optional[float] = None
        
        # Setup emergency stop
        self._setup_emergency_stop()
        
        logger.info("Enhanced AI Agent initialized successfully")
    
    def _setup_emergency_stop(self):
        """Setup emergency stop hotkey."""
        def emergency_stop():
            if self.is_running:
                logger.warning("🚨 EMERGENCY STOP ACTIVATED")
                self.is_running = False
        
        try:
            keyboard.add_hotkey('ctrl+shift+q', emergency_stop)
            logger.info("Emergency stop: Press Ctrl+Shift+Q to abort")
        except Exception as e:
            logger.warning(f"Could not setup emergency stop hotkey: {e}")
    
    def execute_task(self, user_request: str) -> Dict[str, Any]:
        """Execute a user task request with enhanced error handling."""
        
        if self.is_running:
            return {
                "success": False,
                "error": "Agent is already running a task"
            }
        
        self.is_running = True
        self.current_task = user_request
        self.task_start_time = time.time()
        self.execution_history = []
        
        # Update UI
        if self.overlay:
            self.overlay.update_status("🔄 Working...", "#0078d4")
            self.overlay.update_task(user_request)
            self.overlay.add_log(f"Starting task: {user_request}", "INFO")
        
        logger.info(f"🎯 Starting task: {user_request}")
        self._print_task_header(user_request)
        
        try:
            # Step 1: Generate comprehensive task plan
            logger.info("📋 Generating task plan...")
            print("📋 Analyzing request and generating detailed plan...\n")
            
            if self.overlay:
                self.overlay.add_log("Generating task plan...", "INFO")
            
            context = self._get_current_context()
            self.task_plan = self.gemini.generate_task_plan(user_request, context)
            
            # Check for clarification
            if self.task_plan.get("clarification_needed"):
                logger.warning(f"❓ Clarification needed: {self.task_plan['clarification_needed']}")
                if self.overlay:
                    self.overlay.add_log("Clarification needed", "WARNING")
                    self.overlay.update_status("❓ Needs clarification")
                return {
                    "success": False,
                    "needs_clarification": True,
                    "question": self.task_plan["clarification_needed"]
                }
            
            if not self.task_plan.get("understood", False):
                if self.overlay:
                    self.overlay.add_log("Could not understand request", "ERROR")
                    self.overlay.update_status("❌ Failed")
                return {
                    "success": False,
                    "error": "Could not understand the request",
                    "details": self.task_plan
                }
            
            # Display comprehensive plan
            self._display_plan(self.task_plan)
            
            # Update UI with plan
            if self.overlay:
                steps = self.task_plan.get("steps", [])
                self.overlay.update_progress(0, len(steps))
                self.overlay.add_log(f"Plan generated: {len(steps)} steps", "INFO")
            
            # Step 2: Execute the plan with enhanced monitoring
            logger.info(f"⚡ Executing plan...")
            result = self._execute_plan(self.task_plan.get("steps", []))
            
            # Calculate metrics
            execution_time = time.time() - self.task_start_time
            
            # Record task in history
            self.execution_history.append({
                "type": "task",
                "task": user_request,
                "success": result["success"],
                "duration": execution_time,
                "timestamp": datetime.now().isoformat()
            })
            
            # Update UI with result
            if self.overlay:
                if result["success"]:
                    self.overlay.update_status("✅ Completed", "#4ec9b0")
                    self.overlay.add_log(f"Task completed in {execution_time:.2f}s", "INFO")
                else:
                    self.overlay.update_status("❌ Failed", "#f48771")
                    self.overlay.add_log(f"Task failed: {result.get('error', 'Unknown')}", "ERROR")
            
            # Final reporting
            if result["success"]:
                self._print_success(execution_time, result)
            else:
                self._print_failure(execution_time, result)
            
            return {
                "success": result["success"],
                "execution_time": execution_time,
                "steps_completed": result.get("steps_completed", 0),
                "total_steps": len(self.task_plan.get("steps", [])),
                "error": result.get("error"),
                "history": self.execution_history,
                "plan": self.task_plan
            }
            
        except Exception as e:
            logger.error(f"❌ Task execution error: {e}", exc_info=True)
            if self.overlay:
                self.overlay.update_status("❌ Error", "#f48771")
                self.overlay.add_log(f"Error: {str(e)}", "ERROR")
            return {
                "success": False,
                "error": str(e),
                "history": self.execution_history
            }
        finally:
            self.is_running = False
            self.current_task = None
            if self.overlay:
                self.overlay.reset()
    
    def _get_current_context(self) -> Dict[str, Any]:
        """Get comprehensive current system context."""
        return {
            "active_window": self.ui.get_active_window_title(),
            "running_processes": self.ui.get_running_processes()[:20],
            "screen_size": self.ui.screen_size,
            "timestamp": datetime.now().isoformat(),
            "agent_version": "2.0"
        }
    
    def _execute_plan(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute the task plan with comprehensive error handling."""
        
        completed_steps = 0
        total_steps = len(steps)
        
        for step in steps:
            if not self.is_running:
                logger.warning("⚠️  Execution aborted by user")
                return {
                    "success": False,
                    "error": "Aborted by user",
                    "steps_completed": completed_steps
                }
            
            # Check timeout
            if self.task_start_time and time.time() - self.task_start_time > config.max_task_duration:
                logger.error("⏱️  Task timeout exceeded")
                return {
                    "success": False,
                    "error": f"Task timeout exceeded ({config.max_task_duration}s)",
                    "steps_completed": completed_steps
                }
            
            step_num = step.get("step_number", completed_steps + 1)
            action = step.get("action", "unknown")
            target = step.get("target", "")
            parameters = step.get("parameters", {})
            
            logger.info(f"⚡ Step {step_num}/{total_steps}: {action} → {target}")
            print(f"⚡ Step {step_num}/{total_steps}: {action}")
            print(f"   Target: {target}")
            
            # Update UI
            if self.overlay:
                self.overlay.update_progress(step_num, total_steps, action)
                self.overlay.add_log(f"Step {step_num}/{total_steps}: {action} - {target}", "INFO")
            
            if parameters and parameters != {}:
                print(f"   Parameters: {parameters}")
            
            # Hide UI for screenshot
            if self.overlay and action in ["screenshot", "take_screenshot", "take_screenshot_region"]:
                self.overlay.hide()
                time.sleep(0.2)  # Brief pause to ensure UI is hidden
            
            # Take screenshot before action (for verification)
            before_screenshot = None
            if config.enable_screen_recording:
                before_screenshot = self.ui.take_screenshot()
            
            # Execute the action using the executor
            result = self.executor.execute(action, target, parameters)
            
            # Show UI again if it was hidden
            if self.overlay and action in ["screenshot", "take_screenshot", "take_screenshot_region"]:
                self.overlay.show()
            
            # Record in history
            self.execution_history.append({
                "step": step_num,
                "action": action,
                "target": target,
                "parameters": parameters,
                "result": result,
                "timestamp": datetime.now().isoformat(),
                "type": "action"
            })
            
            if not result.get("success", False):
                # Log failure details
                logger.warning(f"   ⚠️  Step failed: {result.get('error', 'Unknown error')}")
                
                # Update UI
                if self.overlay:
                    self.overlay.add_log(f"Step failed: {result.get('error', 'Unknown error')}", "ERROR")
                
                # Try fallback if specified
                fallback = step.get("fallback")
                if fallback:
                    logger.info(f"   🔄 Trying fallback: {fallback}")
                    print(f"   🔄 Attempting fallback strategy...")
                    if self.overlay:
                        self.overlay.add_log("Trying fallback strategy...", "WARNING")
                
                # Retry logic with exponential backoff
                retry_count = 0
                retry_delay = 1.0
                
                while retry_count < config.max_retries and not result.get("success", False):
                    retry_count += 1
                    logger.info(f"   🔄 Retry {retry_count}/{config.max_retries}")
                    print(f"   🔄 Retry {retry_count}/{config.max_retries} (waiting {retry_delay}s)...")
                    
                    time.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
                    
                    result = self.executor.execute(action, target, parameters)
                    
                    if result.get("success", False):
                        logger.info(f"   ✅ Retry successful!")
                        print(f"   ✅ Retry successful!\n")
                        break
                
                if not result.get("success", False):
                    error_msg = (f"Step {step_num} failed after {config.max_retries} retries: "
                               f"{result.get('error', 'Unknown error')}")
                    logger.error(f"   ❌ {error_msg}")
                    print(f"   ❌ {error_msg}\n")
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "steps_completed": completed_steps,
                        "failed_step": step
                    }
            else:
                logger.info(f"   ✅ Step completed successfully")
                print(f"   ✅ Completed\n")
            
            completed_steps += 1
            
            # Wait between steps
            time.sleep(config.action_delay)
        
        # Verify final success if criteria specified
        success_criteria = self.task_plan.get("success_criteria") if self.task_plan else None
        if success_criteria:
            logger.info("🔍 Verifying final task completion...")
            print("🔍 Verifying task completion...")
            verification = self._verify_completion(success_criteria)
            
            if verification.get("success", True):
                print("   ✅ Verification passed\n")
            else:
                print(f"   ⚠️  Verification: {verification.get('reasoning', 'Uncertain')}\n")
        
        return {
            "success": True,
            "steps_completed": completed_steps
        }
    
    def _verify_completion(self, success_criteria: str) -> Dict[str, Any]:
        """Verify that the task completed successfully."""
        try:
            screenshot = self.ui.take_screenshot()
            analysis = self.gemini.analyze_screen(
                screenshot,
                f"Verify if this success criteria is met: {success_criteria}. "
                f"Respond with 'YES' if met, 'NO' if not met, and explain why."
            )
            
            success = "yes" in analysis.lower()
            
            return {
                "success": success,
                "analysis": analysis
            }
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return {"success": False, "error": str(e)}
    
    def _print_task_header(self, request: str):
        """Print formatted task header."""
        print(f"\n{'='*70}")
        print(f"🤖 AI Agent Starting Task")
        print(f"{'='*70}")
        print(f"Request: {request}")
        print(f"Emergency Stop: Ctrl+Shift+Q")
        print(f"{'='*70}\n")
    
    def _display_plan(self, plan: Dict[str, Any]):
        """Display the task plan in a formatted way."""
        print(f"✅ Task Plan Generated:\n")
        print(f"   📝 Summary: {plan.get('task_summary', 'N/A')}")
        print(f"   📊 Complexity: {plan.get('complexity', 'N/A')}")
        print(f"   ⏱️  Estimated Duration: {plan.get('estimated_duration', 'Unknown')}")
        print(f"   📋 Total Steps: {len(plan.get('steps', []))}")
        
        # Show prerequisites if any
        prereqs = plan.get('prerequisites', [])
        if prereqs:
            print(f"   ⚠️  Prerequisites: {', '.join(prereqs)}")
        
        print(f"\n📝 Execution Steps:")
        steps = plan.get("steps", [])
        for step in steps:
            step_num = step.get('step_number', '?')
            action = step.get('action', 'unknown')
            target = step.get('target', '')
            print(f"   {step_num}. {action} → {target}")
        
        # Show potential issues
        issues = plan.get('potential_issues', [])
        if issues:
            print(f"\n⚠️  Potential Issues:")
            for issue in issues:
                print(f"   • {issue}")
        
        print(f"\n{'='*70}\n")
    
    def _print_success(self, execution_time: float, result: Dict[str, Any]):
        """Print success message."""
        logger.info(f"✅ Task completed successfully in {execution_time:.2f}s")
        print(f"\n{'='*70}")
        print(f"✅ Task Completed Successfully!")
        print(f"{'='*70}")
        print(f"⏱️  Time taken: {execution_time:.2f} seconds")
        print(f"📊 Steps executed: {result.get('steps_completed', 0)}")
        print(f"{'='*70}\n")
    
    def _print_failure(self, execution_time: float, result: Dict[str, Any]):
        """Print failure message."""
        error = result.get('error', 'Unknown error')
        logger.error(f"❌ Task failed: {error}")
        print(f"\n{'='*70}")
        print(f"❌ Task Failed")
        print(f"{'='*70}")
        print(f"⏱️  Time taken: {execution_time:.2f} seconds")
        print(f"📊 Steps completed: {result.get('steps_completed', 0)}")
        print(f"❌ Error: {error}")
        print(f"{'='*70}\n")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        total_tasks = len([h for h in self.execution_history if h.get('type') == 'task'])
        successful = len([h for h in self.execution_history if h.get('type') == 'task' and h.get('success')])
        failed = total_tasks - successful
        
        total_actions = len([h for h in self.execution_history if h.get('type') == 'action'])
        total_time = sum(h.get('duration', 0) for h in self.execution_history if h.get('type') == 'task')
        
        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful,
            "failed_tasks": failed,
            "success_rate": (successful / total_tasks * 100) if total_tasks > 0 else 0,
            "total_actions": total_actions,
            "avg_execution_time": (total_time / total_tasks) if total_tasks > 0 else 0
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            "is_running": self.is_running,
            "current_task": self.current_task,
            "steps_completed": len(self.execution_history),
            "uptime": time.time() - self.task_start_time if self.task_start_time else 0,
            "version": "2.0-enhanced"
        }
