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
        """Execute the task plan with DYNAMIC adaptation and verification."""
        
        completed_steps = 0
        total_steps = len(steps)
        
        # Dynamic execution: we can add/modify steps on the fly
        remaining_steps = list(steps)  # Make a copy we can modify
        
        while remaining_steps:
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
            
            # Get next step
            step = remaining_steps.pop(0)
            step_num = completed_steps + 1
            action = step.get("action", "unknown")
            target = step.get("target", "")
            parameters = step.get("parameters", {})
            
            logger.info(f"⚡ Step {step_num}/{total_steps}: {action} → {target}")
            print(f"⚡ Step {step_num}/{total_steps + len(remaining_steps)}: {action}")
            print(f"   Target: {target}")
            
            # Update UI
            if self.overlay:
                self.overlay.update_progress(step_num, total_steps + len(remaining_steps), action)
                self.overlay.add_log(f"Step {step_num}: {action} - {target}", "INFO")
            
            if parameters and parameters != {}:
                print(f"   Parameters: {parameters}")
            
            # Hide UI for screenshot
            if self.overlay and action in ["screenshot", "take_screenshot", "take_screenshot_region"]:
                self.overlay.hide()
                time.sleep(0.2)
            
            # Take screenshot BEFORE action
            before_screenshot = None
            if config.enable_screen_recording:
                before_screenshot = self.ui.take_screenshot()
            
            # Execute the action
            result = self.executor.execute(action, target, parameters)
            
            # Take screenshot AFTER action
            after_screenshot = None
            if config.enable_screen_recording:
                time.sleep(0.5)  # Wait for UI to update
                after_screenshot = self.ui.take_screenshot()
            
            # Show UI again
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
            
            # ============== DYNAMIC VERIFICATION & ADAPTATION ==============
            
            # For critical actions, VERIFY with AI if they actually worked
            if action in ["click", "type_text", "press_key", "hotkey", "focus_window"]:
                logger.info(f"   🔍 Verifying step result with AI...")
                print(f"   🔍 Verifying with AI vision...")
                
                verification = self._verify_step_with_ai(
                    step=step,
                    before_screenshot=before_screenshot,
                    after_screenshot=after_screenshot,
                    expected_outcome=step.get("expected_outcome", target)
                )
                
                if not verification.get("success", True):
                    # Step FAILED verification!
                    logger.warning(f"   ⚠️  AI detected step didn't work: {verification.get('issue')}")
                    print(f"   ⚠️  AI detected issue: {verification.get('issue')}")
                    
                    if self.overlay:
                        self.overlay.add_log(f"Step verification failed: {verification.get('issue')}", "WARNING")
                    
                    # Ask AI for CORRECTIVE ACTIONS
                    logger.info(f"   🧠 Asking AI for corrective actions...")
                    print(f"   🧠 Generating corrective plan...")
                    
                    corrective_steps = self._generate_corrective_steps(
                        failed_step=step,
                        issue=verification.get("issue"),
                        screenshot=after_screenshot,
                        original_goal=step.get("expected_outcome", target)
                    )
                    
                    if corrective_steps:
                        logger.info(f"   🔄 AI generated {len(corrective_steps)} corrective steps")
                        print(f"   🔄 AI generated {len(corrective_steps)} corrective steps")
                        
                        # INSERT corrective steps at the BEGINNING of remaining steps
                        remaining_steps = corrective_steps + remaining_steps
                        total_steps += len(corrective_steps)
                        
                        if self.overlay:
                            self.overlay.add_log(f"Added {len(corrective_steps)} corrective steps", "INFO")
                        
                        # Continue to next iteration (execute corrective steps)
                        continue
                    else:
                        # No corrective steps possible, retry original step
                        logger.warning(f"   ⚠️  No corrective steps available, retrying...")
                        print(f"   ⚠️  Retrying original action...")
                        
                        # Retry with slight delay
                        time.sleep(1.0)
                        result = self.executor.execute(action, target, parameters)
                        
                        if not result.get("success", False):
                            error_msg = f"Step {step_num} failed and could not be corrected"
                            logger.error(f"   ❌ {error_msg}")
                            print(f"   ❌ {error_msg}\n")
                            
                            return {
                                "success": False,
                                "error": error_msg,
                                "steps_completed": completed_steps,
                                "failed_step": step
                            }
                else:
                    logger.info(f"   ✅ AI verified step succeeded")
                    print(f"   ✅ AI verified success")
            
            # Basic success check
            if not result.get("success", False):
                logger.warning(f"   ⚠️  Step execution failed: {result.get('error', 'Unknown error')}")
                
                # Simple retry with exponential backoff
                retry_count = 0
                retry_delay = 1.0
                
                while retry_count < config.max_retries and not result.get("success", False):
                    retry_count += 1
                    logger.info(f"   🔄 Retry {retry_count}/{config.max_retries}")
                    print(f"   🔄 Retry {retry_count}/{config.max_retries} (waiting {retry_delay}s)...")
                    
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    
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
        
        # Verify final success
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
    
    def _get_element_coordinates(
        self,
        screenshot: Any,
        element_description: str,
        screen_width: int = 2880,
        screen_height: int = 1920
    ) -> Optional[tuple[int, int]]:
        """Ask AI to identify the coordinates of an element in a screenshot.
        
        Args:
            screenshot: PIL Image
            element_description: What we're looking for (e.g., "YouTube search box", "first video thumbnail")
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            
        Returns:
            Tuple (x, y) of coordinates, or None if not found
        """
        try:
            prompt = f"""Analyze this screenshot and identify the EXACT pixel coordinates of the following element:

TARGET ELEMENT: {element_description}

Screen Resolution: {screen_width} x {screen_height}

YOUR TASK:
1. Locate the element visually in the screenshot
2. Estimate its CENTER position in pixels (x, y)
3. Be as precise as possible

COORDINATE SYSTEM:
- Origin (0, 0) is at TOP-LEFT corner
- X increases going RIGHT
- Y increases going DOWN
- Maximum X: {screen_width}
- Maximum Y: {screen_height}

EXAMPLES:
- Search box in top-center: might be at (1440, 180)
- First video thumbnail: might be at (700, 500)
- Button in bottom-right: might be at (2500, 1800)

Respond in JSON format:
{{
    "found": true/false,
    "x": pixel_x_coordinate,
    "y": pixel_y_coordinate,
    "confidence": "high|medium|low",
    "description": "what you see at those coordinates"
}}

If the element is not visible, set found to false."""

            response = self.gemini.analyze_screen(screenshot, prompt)
            
            # Parse JSON response
            import json
            try:
                json_str = response
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0].strip()
                
                result = json.loads(json_str)
                
                if result.get("found", False):
                    x = int(result.get("x", 0))
                    y = int(result.get("y", 0))
                    confidence = result.get("confidence", "unknown")
                    
                    logger.info(f"AI found element at ({x}, {y}) - confidence: {confidence}")
                    print(f"   📍 AI located element at ({x}, {y}) - {confidence} confidence")
                    
                    return (x, y)
                else:
                    logger.warning(f"AI could not find element: {element_description}")
                    print(f"   ⚠️  AI could not locate element: {element_description}")
                    return None
                    
            except Exception as e:
                logger.error(f"Could not parse coordinate response: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Coordinate identification error: {e}")
            return None
    
    def _verify_step_with_ai(
        self,
        step: Dict[str, Any],
        before_screenshot: Optional[Any],  # PIL Image
        after_screenshot: Optional[Any],   # PIL Image
        expected_outcome: str
    ) -> Dict[str, Any]:
        """Use AI vision to verify if a step actually succeeded.
        
        Args:
            step: The executed step
            before_screenshot: PIL Image before action
            after_screenshot: PIL Image after action
            expected_outcome: What we expected to happen
            
        Returns:
            Dict with 'success' (bool) and 'issue' (str) if failed
        """
        try:
            if not after_screenshot:
                return {"success": True}  # Can't verify without screenshot
            
            action = step.get("action", "")
            target = step.get("target", "")
            
            # Build verification prompt - BE VERY CRITICAL
            prompt = f"""CRITICAL VISUAL VERIFICATION - Be extremely strict!

ACTION PERFORMED: {action}
TARGET: {target}
EXPECTED OUTCOME: {expected_outcome}

🔍 YOUR JOB: Verify if the action ACTUALLY WORKED by examining the screenshot.

VERIFICATION CHECKLIST:
✓ If we typed "cat video" → Is the text "cat video" VISIBLE in a search box?
✓ If we pressed TAB to focus search box → Is the search box HIGHLIGHTED/FOCUSED?
✓ If we pressed ENTER to search → Did search results APPEAR? Are there video thumbnails?
✓ If we pressed ENTER to play video → Is a video PLAYING? Is player interface visible?
✓ If we typed in address bar → Is the typed URL VISIBLE in the address bar?

CRITICAL EXAMPLES:
❌ FAIL: We typed "cat video" but text is NOT visible anywhere → success: false
❌ FAIL: We pressed ENTER to search but still on YouTube homepage → success: false  
❌ FAIL: We pressed ENTER to play video but no video opened → success: false
✅ PASS: Text "cat video" is clearly visible in the search box → success: true
✅ PASS: Search results page showing cat videos → success: true
✅ PASS: Video player is visible and playing → success: true

⚠️ DEFAULT TO FALSE: If you're not 100% certain the action worked, set success to false!

Respond in JSON format:
{{
    "success": true/false,
    "issue": "specific problem - what is missing or wrong",
    "observed_state": "exactly what you see in screenshot"
}}

BE HARSH - Only return success:true if you clearly see the expected result!"""

            analysis = self.gemini.analyze_screen(after_screenshot, prompt)
            
            # Try to parse JSON response
            import json
            try:
                # Extract JSON from response (might have markdown code blocks)
                json_str = analysis
                if "```json" in analysis:
                    json_str = analysis.split("```json")[1].split("```")[0].strip()
                elif "```" in analysis:
                    json_str = analysis.split("```")[1].split("```")[0].strip()
                
                result = json.loads(json_str)
                return result
            except:
                # Fallback: simple text analysis
                success = "success" in analysis.lower() and "true" in analysis.lower()
                issue = "Could not verify - AI response unclear" if not success else ""
                
                return {
                    "success": success,
                    "issue": issue,
                    "observed_state": analysis[:200]
                }
                
        except Exception as e:
            logger.error(f"Step verification error: {e}")
            return {"success": True}  # Don't block execution on verification errors
    
    def _generate_corrective_steps(
        self,
        failed_step: Dict[str, Any],
        issue: Optional[str],
        screenshot: Optional[Any],  # PIL Image
        original_goal: str
    ) -> List[Dict[str, Any]]:
        """Ask AI to generate corrective steps to fix a failed action.
        
        Args:
            failed_step: The step that didn't work
            issue: Description of what went wrong
            screenshot: Current PIL Image
            original_goal: What we were trying to achieve
            
        Returns:
            List of new steps to try
        """
        try:
            if not screenshot:
                return []
            
            if not issue:
                issue = "Unknown issue"
            
            action = failed_step.get("action", "")
            target = failed_step.get("target", "")
            parameters = failed_step.get("parameters", {})
            
            # Build correction prompt
            prompt = f"""A step in our automation plan failed. Analyze the screenshot and generate SPECIFIC corrective actions.

FAILED ACTION: {action}
TARGET: {target}
PARAMETERS: {parameters}
ORIGINAL GOAL: {original_goal}
ISSUE DETECTED: {issue}

🔍 ANALYZE THE SCREENSHOT:
1. Locate the target element VISUALLY (search box, button, video, etc.)
2. Estimate PRECISE pixel coordinates (x, y) of the element's CENTER
3. Verify current mouse position if relevant

CRITICAL STRATEGY - USE COORDINATES:
✅ ALWAYS prefer direct clicks with coordinates
✅ Take screenshot first to see current state
✅ Identify element coordinates by analyzing screenshot
✅ Move mouse, verify position, then click

EXAMPLE CORRECTIONS:

If search failed:
1. Identify where search box is in screenshot (e.g., x=1440, y=180)
2. click at those coordinates
3. type_text "cat video"
4. press_key enter

If video didn't open:
1. Take screenshot to see video thumbnails
2. Identify first video thumbnail position (e.g., x=700, y=500)
3. click at those coordinates
4. wait for video to load

COORDINATE ESTIMATION:
- Look carefully at the screenshot
- Estimate pixel positions (x, y)
- YouTube search box typically: (1400-1500, 150-200)
- First video thumbnail typically: (600-800, 400-600)
- Buttons/links: estimate center point

Generate JSON with SPECIFIC coordinate-based actions:
{{
    "analysis": "what went wrong and why",
    "strategy": "use coordinate-based clicks to fix",
    "steps": [
        {{
            "action": "take_screenshot|click|move_to|type_text",
            "target": "element description",
            "parameters": {{"x": actual_pixels, "y": actual_pixels, "text": "..."}},
            "expected_outcome": "specific visual result",
            "reason": "why this will work"
        }}
    ]
}}

IMPORTANT: 
- ALWAYS include take_screenshot as first corrective step
- Provide REAL coordinates by analyzing the screenshot
- Maximum 5 corrective steps
- NO TAB navigation - use coordinates!"""

            response = self.gemini.analyze_screen(screenshot, prompt)
            
            # Try to parse JSON response
            import json
            try:
                json_str = response
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0].strip()
                
                result = json.loads(json_str)
                steps = result.get("steps", [])
                
                logger.info(f"AI Analysis: {result.get('analysis', 'N/A')}")
                logger.info(f"AI Strategy: {result.get('strategy', 'N/A')}")
                
                print(f"   💡 AI Analysis: {result.get('analysis', 'N/A')}")
                print(f"   💡 AI Strategy: {result.get('strategy', 'N/A')}")
                
                return steps[:5]  # Max 5 corrective steps
                
            except Exception as e:
                logger.error(f"Could not parse AI corrective steps: {e}")
                logger.debug(f"AI Response: {response}")
                return []
                
        except Exception as e:
            logger.error(f"Corrective steps generation error: {e}")
            return []
    
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
