"""Enhanced Gemini API client with advanced prompting."""

import json
from typing import Optional, List, Dict, Any
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from PIL import Image

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - fallback for older Pillow
    RESAMPLE_LANCZOS = getattr(Image, "LANCZOS", Image.BICUBIC)  # type: ignore[attr-defined]

from src.utils.logger import setup_logger
from src.config.config import config
from src.core.prompts import prompt_builder
from src.utils.ocr import get_ocr_engine, ScreenTextAnalysis

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
            "max_output_tokens": config.gemini_max_output_tokens,
        }
        
        self.model = genai.GenerativeModel(  # type: ignore
            model_name=self.model_name,
            generation_config=generation_config  # type: ignore
        )
        
        # Initialize OCR engine
        self.ocr = get_ocr_engine()
        if self.ocr:
            logger.info("OCR engine initialized alongside vision model")
        else:
            logger.warning("OCR engine unavailable - vision-only mode")
        
        logger.info(f"Initialized Enhanced Gemini client with model: {self.model_name}")
    
    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 64,
        *,
        temperature: float = 0.5,
    ) -> str:
        """Generate a concise text response without requiring JSON parsing."""

        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUAL_CONTENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        try:
            response = self.model.generate_content(  # type: ignore[attr-defined]
                prompt,
                generation_config=GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    top_p=0.9,
                    top_k=20,
                ),
                safety_settings=safety_settings,
            )
            text = self._extract_text_from_response(response)
            if not text:
                raise ValueError("Model returned empty text response")
            logger.debug("Generated text response (%d chars)", len(text))
            return text
        except Exception as exc:  # pragma: no cover - upstream API exceptions
            logger.error(f"Gemini text generation failed: {exc}")

            fallback_text = self._extract_text_from_response(getattr(exc, "response", None))
            if not fallback_text:
                fallback_text = self._extract_text_from_response(getattr(exc, "result", None))

            if fallback_text:
                logger.warning("Using fallback text extracted from blocked response")
                return fallback_text

            raise

    def generate_task_plan(
        self,
        user_request: str,
        context: Optional[Dict[str, Any]] = None,
        *,
        complexity_hint: str = "auto",
        include_examples: bool = True,
    ) -> Dict[str, Any]:
        """Generate a comprehensive step-by-step execution plan."""
        
        prompt = prompt_builder.build_task_planning_prompt(
            user_request,
            context,
            complexity_hint=complexity_hint,
            include_examples=include_examples,
        )
        
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
    
    def analyze_screen(
        self,
        screenshot: Image.Image,
        question: Optional[str] = None,
        *,
        additional_images: Optional[List[Image.Image]] = None,
        focus_area: Optional[str] = None,
        use_ocr: bool = True,
    ) -> str:
        """
        Analyze a screenshot and answer questions about it.
        
        Args:
            screenshot: PIL Image to analyze
            question: Optional question to answer
            additional_images: Optional additional images for context
            focus_area: Optional focus area hint (center, top, bottom, etc.)
            use_ocr: Whether to run OCR first and include text in prompt (recommended)
        """
        
        # Extract text via OCR first (preferred method)
        ocr_text = ""
        ocr_metadata = ""
        if use_ocr and self.ocr:
            try:
                analysis = self.ocr.analyze_screen(screenshot, min_confidence=60.0)
                ocr_text = analysis.full_text
                
                if ocr_text:
                    ocr_metadata = (
                        f"\n\n═══ OCR TEXT EXTRACTION ═══\n"
                        f"The following text was extracted via Tesseract OCR from the screenshot:\n"
                        f"(Average confidence: {analysis.average_confidence:.1f}%)\n\n"
                        f"{ocr_text}\n"
                        f"═══════════════════════════\n\n"
                        f"Use this extracted text to assist your visual analysis. "
                        f"The OCR text is reliable and should be referenced when describing UI elements, "
                        f"button labels, menu items, or any visible text content."
                    )
                    logger.info(
                        f"OCR extracted {len(ocr_text)} chars of text "
                        f"({len(analysis.words)} words, confidence: {analysis.average_confidence:.1f}%)"
                    )
                else:
                    logger.debug("OCR found no text in screenshot")
                    
            except Exception as e:
                logger.warning(f"OCR extraction failed, continuing with vision only: {e}")

        prompt = prompt_builder.build_screen_analysis_prompt(
            question,
            focus_area=focus_area,
        )
        
        # Prepend OCR results to prompt if available
        if ocr_metadata:
            prompt = ocr_metadata + prompt

        optimized_primary = self._prepare_image_for_model(screenshot)
        inputs: List[Any] = [prompt, optimized_primary]

        if additional_images:
            optimized_extras = [self._prepare_image_for_model(img) for img in additional_images]
            inputs.extend(optimized_extras)

        try:
            response = self.model.generate_content(inputs)
            analysis = response.text.strip()
            logger.debug(f"Screen analysis completed: {len(analysis)} chars")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing screen: {e}", exc_info=True)
            # Return OCR text as fallback if available
            if ocr_text:
                return f"Vision model error, OCR text only:\n{ocr_text}"
            return f"Error: {str(e)}"
    
    def find_element_location(
        self, 
        screenshot: Image.Image, 
        element_description: str,
        *,
        use_ocr: bool = True
    ) -> Dict[str, Any]:
        """
        Use vision to locate a UI element in a screenshot.
        
        Args:
            screenshot: PIL Image to search
            element_description: Description of element to find
            use_ocr: Whether to attempt OCR text search first (recommended)
            
        Returns:
            Dict with location data and confidence
        """
        
        # Try OCR-based text search first (faster and more accurate for text elements)
        if use_ocr and self.ocr:
            try:
                # Check if description looks like text search
                if len(element_description.split()) <= 5 and not any(
                    keyword in element_description.lower() 
                    for keyword in ["button", "icon", "image", "picture", "graphic"]
                ):
                    matches = self.ocr.find_text(
                        screenshot,
                        element_description,
                        exact_match=False,
                        min_confidence=70.0
                    )
                    
                    if matches:
                        # Use the first high-confidence match
                        best_match = max(matches, key=lambda m: m.confidence)
                        logger.info(
                            f"OCR found '{element_description}' at {best_match.center} "
                            f"(confidence: {best_match.confidence:.1f}%)"
                        )
                        return {
                            "found": True,
                            "x": best_match.center[0] if best_match.center else 0,
                            "y": best_match.center[1] if best_match.center else 0,
                            "confidence": best_match.confidence,
                            "method": "ocr",
                            "bounding_box": best_match.bounding_box,
                            "text_matched": best_match.text
                        }
                    else:
                        logger.debug(f"OCR found no match for '{element_description}', trying vision model")
                        
            except Exception as e:
                logger.warning(f"OCR element search failed, falling back to vision: {e}")
        
        # Fall back to vision model
        prompt = prompt_builder.build_element_location_prompt(element_description)

        prepared_image = self._prepare_image_for_model(screenshot)

        try:
            response = self.model.generate_content([prompt, prepared_image])
            text = response.text.strip()
            
            json_text = self._extract_json(text)
            result = json.loads(json_text)
            result["method"] = "vision"
            
            if result.get("found", False):
                logger.info(f"Vision model found: {element_description} "
                          f"(confidence: {result.get('confidence', 0)}%)")
            else:
                logger.debug(f"Vision model could not find: {element_description}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error finding element: {e}")
            return {"found": False, "error": str(e), "method": "vision"}
    
    def verify_action_result(self, before_image: Image.Image, after_image: Image.Image, 
                           expected_change: str) -> Dict[str, Any]:
        """Compare before/after screenshots to verify an action succeeded."""
        
        prompt = prompt_builder.build_verification_prompt(expected_change)

        before_prepared = self._prepare_image_for_model(before_image)
        after_prepared = self._prepare_image_for_model(after_image)

        try:
            response = self.model.generate_content([prompt, before_prepared, after_prepared])
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

    def _prepare_image_for_model(self, image: Image.Image) -> Image.Image:
        """Downscale and normalize images before sending to the vision model."""

        scale = config.vision_image_scale
        max_dim = config.vision_image_max_dim
        target_format = config.vision_image_format

        processed = image.copy()
        processed = self._resize_image(processed, scale=scale, max_dim=max_dim)

        if target_format in {"jpeg", "webp"} and processed.mode not in ("RGB", "L"):
            processed = processed.convert("RGB")

        return processed

    @staticmethod
    def _resize_image(image: Image.Image, *, scale: float, max_dim: int) -> Image.Image:
        """Resize image based on scale factor and maximum dimension."""

        width, height = image.size
        if width <= 0 or height <= 0:
            return image

        ratio = 1.0
        if scale < 1.0:
            ratio = min(ratio, max(scale, 0.05))

        if max_dim > 0:
            longest_side = max(width, height)
            if longest_side > max_dim:
                ratio = min(ratio, max_dim / longest_side)

        if ratio >= 1.0:
            return image

        new_size = (
            max(1, int(round(width * ratio))),
            max(1, int(round(height * ratio))),
        )

        if new_size == image.size:
            return image

        return image.resize(new_size, RESAMPLE_LANCZOS)
    
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

    @staticmethod
    def _extract_text_from_response(response: Any) -> str:
        """Best-effort extraction of text from a Gemini response or error payload."""

        if response is None:
            return ""

        try:
            text_attr = getattr(response, "text", None)
            if text_attr:
                return str(text_attr).strip()
        except Exception:
            pass

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) if content else None

            if parts:
                for part in parts:
                    part_text = getattr(part, "text", None)
                    if part_text:
                        return str(part_text).strip()

            legacy_parts = getattr(candidate, "parts", None)
            if legacy_parts:
                for part in legacy_parts:
                    part_text = getattr(part, "text", None)
                    if part_text:
                        return str(part_text).strip()

        return ""
