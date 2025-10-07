"""Enhanced Gemini API client with advanced prompting."""

import json
from typing import Optional, List, Dict, Any
import google.generativeai as genai
from PIL import Image

from logger import setup_logger
from config import config
from src.core.prompts import prompt_builder

logger = setup_logger("GeminiClient")


class EnhancedGeminiClient:
    """Enhanced client for interacting with Google's Gemini API."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize Gemini client."""
        self.api_key = api_key or config.gemini_api_key
        self.model_name = model or config.gemini_model
        
        if not self.api_key:
            raise ValueError("Gemini API key is required")
        
        genai.configure(api_key=self.api_key)  # type: ignore
        
        # Configure generation settings for better outputs
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
        }
        
        self.model = genai.GenerativeModel(  # type: ignore
            model_name=self.model_name,
            generation_config=generation_config  # type: ignore
        )
        
        logger.info(f"Initialized Enhanced Gemini client with model: {self.model_name}")
    
    def generate_task_plan(self, user_request: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate a comprehensive step-by-step execution plan."""
        
        prompt = prompt_builder.build_task_planning_prompt(user_request, context)
        
        text = ""  # Initialize to avoid unbound variable
        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            
            logger.debug(f"Raw API response length: {len(text)} chars")
            
            # Extract JSON from response
            json_text = self._extract_json(text)
            plan = json.loads(json_text)
            
            # Validate the plan structure
            if not self._validate_plan(plan):
                logger.warning("Plan validation failed, using fallback structure")
                return self._create_fallback_plan(user_request)
            
            logger.info(f"Generated task plan: {plan.get('task_summary', 'N/A')} "
                       f"({len(plan.get('steps', []))} steps)")
            
            return plan
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            text_to_log = text if 'text' in locals() else "N/A"
            logger.debug(f"Raw response: {text_to_log[:500]}...")
            return self._create_fallback_plan(user_request, error=str(e))
            
        except Exception as e:
            logger.error(f"Error generating task plan: {e}", exc_info=True)
            return self._create_fallback_plan(user_request, error=str(e))
    
    def analyze_screen(self, screenshot: Image.Image, question: Optional[str] = None) -> str:
        """Analyze a screenshot and answer questions about it."""
        
        prompt = prompt_builder.build_screen_analysis_prompt(question)
        
        try:
            response = self.model.generate_content([prompt, screenshot])
            analysis = response.text.strip()
            logger.debug(f"Screen analysis completed: {len(analysis)} chars")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing screen: {e}", exc_info=True)
            return f"Error: {str(e)}"
    
    def find_element_location(self, screenshot: Image.Image, element_description: str) -> Dict[str, Any]:
        """Use vision to locate a UI element in a screenshot."""
        
        prompt = prompt_builder.build_element_location_prompt(element_description)
        
        try:
            response = self.model.generate_content([prompt, screenshot])
            text = response.text.strip()
            
            json_text = self._extract_json(text)
            result = json.loads(json_text)
            
            if result.get("found", False):
                logger.info(f"Element found: {element_description} "
                          f"(confidence: {result.get('confidence', 0)}%)")
            else:
                logger.debug(f"Element not found: {element_description}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error finding element: {e}")
            return {"found": False, "error": str(e)}
    
    def verify_action_result(self, before_image: Image.Image, after_image: Image.Image, 
                           expected_change: str) -> Dict[str, Any]:
        """Compare before/after screenshots to verify an action succeeded."""
        
        prompt = prompt_builder.build_verification_prompt(expected_change)
        
        try:
            response = self.model.generate_content([prompt, before_image, after_image])
            text = response.text.strip()
            
            json_text = self._extract_json(text)
            result = json.loads(json_text)
            
            logger.info(f"Verification: {result.get('success', False)} "
                       f"(confidence: {result.get('confidence', 0)}%)")
            
            return result
            
        except Exception as e:
            logger.error(f"Error verifying action: {e}")
            return {
                "success": False,
                "confidence": 0,
                "reasoning": f"Verification error: {str(e)}"
            }
    
    def get_next_action(self, current_state: str, goal: str, previous_actions: List[str]) -> Dict[str, Any]:
        """Decide the next action based on current state and goal."""
        
        prompt = prompt_builder.build_next_action_prompt(current_state, goal, previous_actions)
        
        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            
            json_text = self._extract_json(text)
            result = json.loads(json_text)
            
            logger.info(f"Next action suggested: {result.get('action', 'unknown')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting next action: {e}")
            return {
                "action": "wait",
                "target": "1 second",
                "reasoning": f"Error occurred: {str(e)}"
            }
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from text that may contain markdown code blocks."""
        
        # Try to find JSON in markdown code blocks
        if "```json" in text:
            parts = text.split("```json")
            if len(parts) > 1:
                json_part = parts[1].split("```")[0].strip()
                return json_part
        
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                json_part = parts[1].strip()
                # Remove language identifier if present
                lines = json_part.split('\n')
                if lines[0].lower() in ['json', 'javascript', 'js']:
                    json_part = '\n'.join(lines[1:])
                return json_part
        
        # Try to find JSON object in text
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return text[start_idx:end_idx+1]
        
        return text
    
    def _validate_plan(self, plan: Dict[str, Any]) -> bool:
        """Validate that a plan has required structure."""
        required_keys = ['understood', 'task_summary', 'steps']
        
        if not all(key in plan for key in required_keys):
            logger.warning(f"Plan missing required keys. Has: {list(plan.keys())}")
            return False
        
        if not isinstance(plan.get('steps'), list):
            logger.warning("Plan steps is not a list")
            return False
        
        if len(plan.get('steps', [])) == 0:
            logger.warning("Plan has no steps")
            return False
        
        return True
    
    def _create_fallback_plan(self, user_request: str, error: Optional[str] = None) -> Dict[str, Any]:
        """Create a fallback plan when API fails."""
        
        clarification = "I couldn't understand your request properly."
        if error:
            clarification += f" Error: {error}"
        
        return {
            "understood": False,
            "task_summary": user_request,
            "complexity": "unknown",
            "steps": [],
            "clarification_needed": clarification
        }
