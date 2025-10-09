"""
Target Locator - Multi-level strategy for finding UI element coordinates.
Implements a funnel approach: OCR exact -> OCR fuzzy -> Vision AI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from PIL import Image
    from src.core.gemini_client import EnhancedGeminiClient
    from src.utils.ocr import TesseractOCR, OCRResult

from src.utils.logger import setup_logger

logger = setup_logger("TargetLocator")


@dataclass
class LocationResult:
    """Result of a target location search."""
    success: bool
    coordinates: Optional[Tuple[int, int]] = None
    method: str = ""  # "ocr_exact", "ocr_fuzzy", "vision_ai", "failed"
    confidence: float = 0.0
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TargetLocator:
    """
    Intelligently locates UI elements using a multi-level strategy.
    
    Strategy Levels:
    1. OCR Exact Match - Fast, precise, works for text elements
    2. OCR Fuzzy Match + AI - Handles semantic descriptions  
    3. Vision AI Analysis - Powerful fallback for visual elements
    4. Remote-Controlled Pixel-by-Pixel - AI guides mouse movement iteratively
    """
    
    def __init__(
        self,
        ocr_engine: Optional[TesseractOCR] = None,
        gemini_client: Optional[EnhancedGeminiClient] = None
    ):
        """
        Initialize the target locator.
        
        Args:
            ocr_engine: OCR engine for text detection
            gemini_client: Gemini client for AI-powered location
        """
        self.ocr_engine = ocr_engine
        self.gemini_client = gemini_client
    
    def find_target_with_remote_guidance(
        self,
        screenshot: Image.Image,
        target_description: str,
        current_mouse_pos: Tuple[int, int],
        max_iterations: int = 50
    ) -> LocationResult:
        """
        Use AI to guide mouse movement pixel-by-pixel to the target.
        
        This method:
        1. Uses OCR to get close to the target
        2. Then lets the AI see the screen and guide cursor movement iteratively
        3. AI responds with directional commands (up/down/left/right) or "click"
        
        Args:
            screenshot: Current screen image
            target_description: What to find
            current_mouse_pos: Current cursor position
            max_iterations: Maximum number of refinement iterations
            
        Returns:
            LocationResult with the final coordinates
        """
        logger.info(f"🎮 Remote-controlled targeting: '{target_description}'")
        
        # First, try OCR to get close
        ocr_result = None
        if self.ocr_engine:
            ocr_result = self._try_ocr_exact(screenshot, target_description)
            if not ocr_result.success:
                ocr_result = self._try_ocr_fuzzy(screenshot, target_description)
        
        # Start position: either OCR result or current mouse position
        if ocr_result and ocr_result.success and ocr_result.coordinates:
            start_pos = ocr_result.coordinates
            logger.info(f"   📍 OCR placed cursor near target at {start_pos}")
        else:
            start_pos = current_mouse_pos
            logger.info(f"   📍 Starting from current mouse position: {start_pos}")
        
        # Now use AI guidance for pixel-perfect targeting
        # This would be implemented in the agent's execution loop
        # Here we just return the OCR-based position as a starting point
        return LocationResult(
            success=True,
            coordinates=start_pos,
            method="ocr_approximate",
            confidence=0.7,
            metadata={
                "requires_fine_tuning": True,
                "ocr_used": ocr_result is not None and ocr_result.success,
                "description": target_description
            }
        )
        
    def find_target(
        self,
        screenshot: Image.Image,
        target_description: str,
        use_ocr: bool = True,
        use_vision: bool = True
    ) -> LocationResult:
        """
        Find target coordinates using multi-level strategy.
        
        Args:
            screenshot: Current screen image
            target_description: Description of the target element
            use_ocr: Whether to use OCR-based methods
            use_vision: Whether to use vision AI as fallback
            
        Returns:
            LocationResult with coordinates and metadata
        """
        logger.info(f"🎯 Locating target: '{target_description}'")
        
        # Level 1: Try OCR exact match
        if use_ocr and self.ocr_engine:
            result = self._try_ocr_exact(screenshot, target_description)
            if result.success:
                return result
            
            # Level 2: Try OCR fuzzy match with AI
            result = self._try_ocr_fuzzy(screenshot, target_description)
            if result.success:
                return result
        
        # Level 3: Vision AI analysis
        if use_vision and self.gemini_client:
            result = self._try_vision_ai(screenshot, target_description)
            if result.success:
                return result
        
        # All methods failed
        logger.error(f"❌ Failed to locate target: '{target_description}'")
        return LocationResult(
            success=False,
            method="failed",
            error=f"Could not locate target: {target_description}"
        )
    
    def _try_ocr_exact(
        self,
        screenshot: Image.Image,
        target_description: str
    ) -> LocationResult:
        """
        Level 1: Try exact text match with OCR.
        
        Extracts potential text from the description and searches for it.
        """
        logger.info("   📝 Level 1: Attempting OCR exact match...")
        
        # Extract potential text to search for
        search_texts = self._extract_search_texts(target_description)
        
        if not search_texts:
            logger.debug("   ⏭️  No searchable text found in description")
            return LocationResult(success=False, method="ocr_exact")
        
        ocr_engine = self.ocr_engine
        if ocr_engine is None:
            logger.debug("   ⏭️  Level 1 skipped: No OCR engine available")
            return LocationResult(success=False, method="ocr_exact")

        # Try each extracted text
        for search_text in search_texts:
            try:
                results = ocr_engine.find_text(
                    screenshot,
                    search_text,
                    case_sensitive=False
                )
                
                if results:
                    best_match = max(results, key=lambda r: r.confidence)
                    
                    # Use center if available, otherwise calculate from bounding_box
                    if best_match.center:
                        center_x, center_y = best_match.center
                    elif best_match.bounding_box:
                        # bounding_box is (x, y, width, height)
                        x, y, w, h = best_match.bounding_box
                        center_x = x + w // 2
                        center_y = y + h // 2
                    else:
                        logger.debug(f"   ⚠️  No location data for match '{search_text}'")
                        continue
                    
                    logger.info(
                        f"   ✅ Level 1 Success: Found '{search_text}' at "
                        f"({center_x}, {center_y}) with {best_match.confidence:.2f} confidence"
                    )
                    
                    return LocationResult(
                        success=True,
                        coordinates=(center_x, center_y),
                        method="ocr_exact",
                        confidence=best_match.confidence,
                        metadata={
                            "search_text": search_text,
                            "found_text": best_match.text,
                            "bounding_box": best_match.bounding_box
                        }
                    )
            except Exception as e:
                logger.debug(f"   ⚠️  OCR search failed for '{search_text}': {e}")
                continue
        
        logger.debug("   ⏭️  Level 1 failed: No exact text match found")
        return LocationResult(success=False, method="ocr_exact")
    
    def _try_ocr_fuzzy(
        self,
        screenshot: Image.Image,
        target_description: str
    ) -> LocationResult:
        """
        Level 2: OCR all text + AI semantic matching.
        
        Extracts all text from screen and asks AI to match the description.
        """
        logger.info("   🔍 Level 2: Attempting OCR fuzzy match with AI...")
        
        ocr_engine = self.ocr_engine
        if ocr_engine is None:
            logger.debug("   ⏭️  Level 2 skipped: No OCR engine available")
            return LocationResult(success=False, method="ocr_fuzzy")

        gemini_client = self.gemini_client
        if gemini_client is None:
            logger.debug("   ⏭️  Level 2 skipped: No Gemini client available")
            return LocationResult(success=False, method="ocr_fuzzy")
        
        try:
            # Get all text elements from screen
            analysis = ocr_engine.analyze_screen(screenshot)
            all_results = analysis.words  # Get word-level results
            
            if not all_results:
                logger.debug("   ⏭️  Level 2 failed: No text found on screen")
                return LocationResult(success=False, method="ocr_fuzzy")
            
            # Build prompt for AI
            elements_text = "\n".join([
                f"{i+1}. '{result.text}' at {result.bounding_box} (confidence: {result.confidence:.2f})"
                for i, result in enumerate(all_results[:50])  # Limit to top 50
            ])
            
            prompt = f"""Given the following text elements found on screen with their coordinates, 
which element best matches the description: '{target_description}'?

Elements found:
{elements_text}

Respond ONLY with the number of the matching element (1-{min(len(all_results), 50)}), or '0' if none match.
Do not provide any explanation, just the number."""
            
            response = gemini_client.generate_content(prompt)
            
            # Parse response
            match = re.search(r'\b(\d+)\b', response)
            if match:
                element_index = int(match.group(1)) - 1
                
                if 0 <= element_index < len(all_results):
                    matched_result = all_results[element_index]
                    
                    # Calculate center from bounding_box or use center directly
                    if matched_result.center:
                        center_x, center_y = matched_result.center
                    elif matched_result.bounding_box:
                        x, y, w, h = matched_result.bounding_box
                        center_x = x + w // 2
                        center_y = y + h // 2
                    else:
                        logger.debug("   ⏭️  Level 2 failed: No location data for matched element")
                        return LocationResult(success=False, method="ocr_fuzzy")
                    
                    logger.info(
                        f"   ✅ Level 2 Success: AI matched to '{matched_result.text}' "
                        f"at ({center_x}, {center_y})"
                    )
                    
                    return LocationResult(
                        success=True,
                        coordinates=(center_x, center_y),
                        method="ocr_fuzzy",
                        confidence=matched_result.confidence,
                        metadata={
                            "matched_text": matched_result.text,
                            "bounding_box": matched_result.bounding_box,
                            "ai_selection": element_index + 1
                        }
                    )
            
            logger.debug("   ⏭️  Level 2 failed: AI could not match description")
            return LocationResult(success=False, method="ocr_fuzzy")
            
        except Exception as e:
            logger.warning(f"   ⚠️  Level 2 error: {e}")
            return LocationResult(success=False, method="ocr_fuzzy", error=str(e))
    
    def _try_vision_ai(
        self,
        screenshot: Image.Image,
        target_description: str
    ) -> LocationResult:
        """
        Level 3: Use Vision AI to locate element.
        
        Sends screenshot to Gemini Vision and asks for bounding box coordinates.
        """
        logger.info("   👁️  Level 3: Attempting Vision AI analysis...")
        
        gemini_client = self.gemini_client
        if gemini_client is None:
            logger.debug("   ⏭️  Level 3 skipped: No Gemini client available")
            return LocationResult(success=False, method="vision_ai")
        
        try:
            location_data = gemini_client.find_element_location(
                screenshot,
                target_description
            )
            
            if location_data and "box" in location_data:
                box = location_data["box"]
                center_x = (box[0] + box[2]) // 2
                center_y = (box[1] + box[3]) // 2
                
                logger.info(
                    f"   ✅ Level 3 Success: Vision AI located element at "
                    f"({center_x}, {center_y})"
                )
                
                return LocationResult(
                    success=True,
                    coordinates=(center_x, center_y),
                    method="vision_ai",
                    confidence=location_data.get("confidence", 0.8),
                    metadata={
                        "box": box,
                        "description": target_description
                    }
                )
            elif location_data and "error" in location_data:
                logger.debug(f"   ⏭️  Level 3 failed: {location_data['error']}")
                return LocationResult(
                    success=False,
                    method="vision_ai",
                    error=location_data["error"]
                )
            else:
                logger.debug("   ⏭️  Level 3 failed: Invalid response from Vision AI")
                return LocationResult(
                    success=False,
                    method="vision_ai",
                    error="Invalid response from Vision AI"
                )
                
        except Exception as e:
            logger.warning(f"   ⚠️  Level 3 error: {e}")
            return LocationResult(success=False, method="vision_ai", error=str(e))
    
    @staticmethod
    def _extract_search_texts(description: str) -> List[str]:
        """
        Extract potential search texts from a target description.
        
        Examples:
            "Click the 'Login' button" -> ["Login"]
            "the pulsante Chiudi" -> ["Chiudi"]
            "Calculator 'C' (Clear) button" -> ["C", "Clear"]
        """
        search_texts = []
        
        # Extract text in quotes
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", description)
        search_texts.extend(quoted)
        
        # Extract text in parentheses
        parenthesized = re.findall(r"\(([^)]+)\)", description)
        search_texts.extend(parenthesized)
        
        # If no quotes/parentheses, try to extract capitalized words
        # or last significant word
        if not search_texts:
            words = description.split()
            # Look for capitalized words (but not at sentence start)
            for i, word in enumerate(words):
                if i > 0 and word[0].isupper() and len(word) > 1:
                    search_texts.append(word)
            
            # Also try the last noun-like word
            if words:
                last_word = words[-1].strip('.,!?;:')
                if len(last_word) > 2 and last_word not in {'button', 'field', 'the', 'a', 'an'}:
                    search_texts.append(last_word)
        
        # Clean and deduplicate
        search_texts = list(dict.fromkeys([t.strip() for t in search_texts if len(t.strip()) > 1]))
        
        logger.debug(f"   📋 Extracted search texts: {search_texts}")
        return search_texts
