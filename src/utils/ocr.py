"""OCR (Optical Character Recognition) utilities using Tesseract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast
import re

if TYPE_CHECKING:  # pragma: no cover - hints for type checkers
    from PIL import Image as PILImageModule
    from PIL.Image import Image as PILImage
    import pytesseract
    import cv2
    import numpy as np

try:  # pragma: no cover - dependency resolution happens at runtime
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    TESSERACT_AVAILABLE = True
except ImportError:  # pragma: no cover - handled gracefully
    pytesseract = cast(Any, None)
    Image = cast(Any, None)
    cv2 = cast(Any, None)
    np = cast(Any, None)
    TESSERACT_AVAILABLE = False

if not TYPE_CHECKING:
    PILImage = Any

from src.utils.logger import setup_logger

logger = setup_logger("OCR")


@dataclass
class OCRResult:
    """Structured OCR result with text and location data."""
    
    text: str
    confidence: float
    bounding_box: Optional[Tuple[int, int, int, int]] = None  # (x, y, width, height)
    center: Optional[Tuple[int, int]] = None  # (x, y) center point
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "bounding_box": self.bounding_box,
            "center": self.center,
        }


@dataclass
class ScreenTextAnalysis:
    """Complete text analysis of a screenshot."""
    
    full_text: str
    words: List[OCRResult]
    lines: List[OCRResult]
    blocks: List[OCRResult]
    average_confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "full_text": self.full_text,
            "words": [w.to_dict() for w in self.words],
            "lines": [l.to_dict() for l in self.lines],
            "blocks": [b.to_dict() for b in self.blocks],
            "average_confidence": self.average_confidence,
        }


class TesseractOCR:
    """OCR engine using Tesseract for text extraction from screenshots."""
    
    def __init__(self, tesseract_cmd: Optional[str] = None):
        """
        Initialize Tesseract OCR engine.
        
        Args:
            tesseract_cmd: Path to tesseract executable (optional, uses PATH by default)
        """
        if not TESSERACT_AVAILABLE:
            raise ImportError(
                "Tesseract dependencies not available. "
                "Install with: pip install pytesseract pillow opencv-python"
            )
        self._ensure_dependencies()
        assert pytesseract is not None
        assert Image is not None
        assert cv2 is not None
        assert np is not None
        
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        # Verify Tesseract is accessible
        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract OCR initialized (version {version})")
        except pytesseract.TesseractNotFoundError:
            logger.error(
                "Tesseract executable not found. Please install Tesseract OCR:\n"
                "  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki\n"
                "  Linux: sudo apt-get install tesseract-ocr\n"
                "  macOS: brew install tesseract"
            )
            raise

    @staticmethod
    def _ensure_dependencies() -> None:
        """Ensure all required third-party modules are available."""

        missing = [
            name
            for name, module in (
                ("pytesseract", pytesseract),
                ("Pillow", Image),
                ("opencv-python", cv2),
                ("numpy", np),
            )
            if module is None
        ]

        if missing:
            raise ImportError(
                "Missing OCR dependencies: " + ", ".join(missing)
            )
    
    def extract_text(
        self,
    image: "PILImage",
        *,
        lang: str = "eng",
        config: str = "--psm 3",
        preprocess: bool = True
    ) -> str:
        """
        Extract all text from an image.
        
        Args:
            image: PIL Image to process
            lang: Tesseract language code (default: English)
            config: Tesseract configuration string
            preprocess: Whether to preprocess image for better OCR
            
        Returns:
            Extracted text as string
        """
        try:
            processed_image = self._preprocess_image(image) if preprocess else image
            text = pytesseract.image_to_string(processed_image, lang=lang, config=config)
            logger.debug(f"Extracted {len(text)} characters of text")
            return text.strip()
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return ""
    
    def analyze_screen(
        self,
    image: "PILImage",
        *,
        lang: str = "eng",
        config: str = "--psm 3",
        preprocess: bool = True,
        min_confidence: float = 0.0
    ) -> ScreenTextAnalysis:
        """
        Perform comprehensive OCR analysis with position data.
        
        Args:
            image: PIL Image to analyze
            lang: Tesseract language code
            config: Tesseract configuration
            preprocess: Whether to preprocess image
            min_confidence: Minimum confidence threshold (0-100)
            
        Returns:
            ScreenTextAnalysis with structured text data
        """
        try:
            processed_image = self._preprocess_image(image) if preprocess else image
            
            # Get detailed OCR data
            data = pytesseract.image_to_data(
                processed_image,
                lang=lang,
                config=config,
                output_type=pytesseract.Output.DICT
            )
            
            words: List[OCRResult] = []
            lines: Dict[int, List[OCRResult]] = {}
            blocks: Dict[int, List[OCRResult]] = {}
            
            total_confidence = 0.0
            confidence_count = 0
            
            # Parse word-level data
            for i in range(len(data['text'])):
                text = data['text'][i].strip()
                if not text:
                    continue
                
                conf = float(data['conf'][i])
                if conf < min_confidence:
                    continue
                
                x = int(data['left'][i])
                y = int(data['top'][i])
                w = int(data['width'][i])
                h = int(data['height'][i])
                
                center = (x + w // 2, y + h // 2)
                
                word = OCRResult(
                    text=text,
                    confidence=conf,
                    bounding_box=(x, y, w, h),
                    center=center
                )
                
                words.append(word)
                
                # Group by line
                line_num = int(data['line_num'][i])
                if line_num not in lines:
                    lines[line_num] = []
                lines[line_num].append(word)
                
                # Group by block
                block_num = int(data['block_num'][i])
                if block_num not in blocks:
                    blocks[block_num] = []
                blocks[block_num].append(word)
                
                total_confidence += conf
                confidence_count += 1
            
            # Merge words into lines
            line_results = []
            for line_words in lines.values():
                if not line_words:
                    continue
                line_text = " ".join(w.text for w in line_words)
                line_conf = sum(w.confidence for w in line_words) / len(line_words)
                
                # Calculate line bounding box
                min_x = min(w.bounding_box[0] for w in line_words if w.bounding_box)
                min_y = min(w.bounding_box[1] for w in line_words if w.bounding_box)
                max_x = max(
                    w.bounding_box[0] + w.bounding_box[2]
                    for w in line_words if w.bounding_box
                )
                max_y = max(
                    w.bounding_box[1] + w.bounding_box[3]
                    for w in line_words if w.bounding_box
                )
                
                line_box = (min_x, min_y, max_x - min_x, max_y - min_y)
                line_center = (min_x + (max_x - min_x) // 2, min_y + (max_y - min_y) // 2)
                
                line_results.append(OCRResult(
                    text=line_text,
                    confidence=line_conf,
                    bounding_box=line_box,
                    center=line_center
                ))
            
            # Merge words into blocks
            block_results = []
            for block_words in blocks.values():
                if not block_words:
                    continue
                block_text = " ".join(w.text for w in block_words)
                block_conf = sum(w.confidence for w in block_words) / len(block_words)
                
                # Calculate block bounding box
                min_x = min(w.bounding_box[0] for w in block_words if w.bounding_box)
                min_y = min(w.bounding_box[1] for w in block_words if w.bounding_box)
                max_x = max(
                    w.bounding_box[0] + w.bounding_box[2]
                    for w in block_words if w.bounding_box
                )
                max_y = max(
                    w.bounding_box[1] + w.bounding_box[3]
                    for w in block_words if w.bounding_box
                )
                
                block_box = (min_x, min_y, max_x - min_x, max_y - min_y)
                block_center = (min_x + (max_x - min_x) // 2, min_y + (max_y - min_y) // 2)
                
                block_results.append(OCRResult(
                    text=block_text,
                    confidence=block_conf,
                    bounding_box=block_box,
                    center=block_center
                ))
            
            # Get full text
            full_text = pytesseract.image_to_string(processed_image, lang=lang, config=config)
            
            avg_conf = total_confidence / confidence_count if confidence_count > 0 else 0.0
            
            logger.info(
                f"OCR analysis complete: {len(words)} words, "
                f"{len(line_results)} lines, {len(block_results)} blocks, "
                f"avg confidence: {avg_conf:.1f}%"
            )
            
            return ScreenTextAnalysis(
                full_text=full_text.strip(),
                words=words,
                lines=line_results,
                blocks=block_results,
                average_confidence=avg_conf
            )
            
        except Exception as e:
            logger.error(f"Screen analysis failed: {e}", exc_info=True)
            return ScreenTextAnalysis(
                full_text="",
                words=[],
                lines=[],
                blocks=[],
                average_confidence=0.0
            )
    
    def find_text(
        self,
    image: "PILImage",
        search_text: str,
        *,
        case_sensitive: bool = False,
        exact_match: bool = False,
        lang: str = "eng",
        min_confidence: float = 60.0
    ) -> List[OCRResult]:
        """
        Find specific text in an image and return locations.
        
        Args:
            image: PIL Image to search
            search_text: Text to find
            case_sensitive: Whether search is case-sensitive
            exact_match: Whether to require exact word match (vs. substring)
            lang: Tesseract language code
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of OCRResult objects for matches
        """
        analysis = self.analyze_screen(
            image,
            lang=lang,
            min_confidence=min_confidence
        )
        
        matches: List[OCRResult] = []
        
        search_normalized = search_text if case_sensitive else search_text.lower()
        
        for word in analysis.words:
            word_normalized = word.text if case_sensitive else word.text.lower()
            
            if exact_match:
                if word_normalized == search_normalized:
                    matches.append(word)
            else:
                if search_normalized in word_normalized:
                    matches.append(word)
        
        logger.debug(f"Found {len(matches)} matches for '{search_text}'")
        return matches
    
    def _preprocess_image(self, image: "PILImage") -> "PILImage":
        """
        Preprocess image to improve OCR accuracy.
        
        Applies:
        - Grayscale conversion
        - Contrast enhancement
        - Noise reduction
        - Thresholding
        """
        try:
            # Convert PIL to OpenCV
            img_array = np.array(image)
            
            # Convert to grayscale
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            # Apply denoising
            denoised = cv2.fastNlMeansDenoising(gray)
            
            # Apply adaptive thresholding for better text contrast
            thresh = cv2.adaptiveThreshold(
                denoised,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11,
                2
            )
            
            # Convert back to PIL
            processed = Image.fromarray(thresh)
            
            logger.debug("Image preprocessing complete")
            return processed
            
        except Exception as e:
            logger.warning(f"Image preprocessing failed, using original: {e}")
            return image
    
    def extract_structured_data(
        self,
    image: "PILImage",
        patterns: Dict[str, str],
        *,
        lang: str = "eng"
    ) -> Dict[str, Optional[str]]:
        """
        Extract structured data using regex patterns.
        
        Args:
            image: PIL Image to process
            patterns: Dict of {field_name: regex_pattern}
            lang: Tesseract language code
            
        Returns:
            Dict of {field_name: extracted_value}
            
        Example:
            patterns = {
                "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}",
                "phone": r"\\d{3}-\\d{3}-\\d{4}",
                "date": r"\\d{2}/\\d{2}/\\d{4}"
            }
        """
        text = self.extract_text(image, lang=lang)
        
        results: Dict[str, Optional[str]] = {}
        
        for field, pattern in patterns.items():
            match = re.search(pattern, text)
            results[field] = match.group(0) if match else None
        
        logger.debug(f"Extracted {sum(1 for v in results.values() if v)} fields from patterns")
        return results


def create_ocr_engine(tesseract_cmd: Optional[str] = None) -> Optional[TesseractOCR]:
    """
    Factory function to create OCR engine with error handling.
    
    Args:
        tesseract_cmd: Path to tesseract executable
        
    Returns:
        TesseractOCR instance or None if unavailable
    """
    if not TESSERACT_AVAILABLE:
        logger.warning("Tesseract dependencies not available")
        return None
    
    try:
        return TesseractOCR(tesseract_cmd)
    except Exception as e:
        logger.error(f"Failed to initialize Tesseract OCR: {e}")
        return None


# Singleton instance
_ocr_engine: Optional[TesseractOCR] = None


def get_ocr_engine() -> Optional[TesseractOCR]:
    """Get or create the global OCR engine instance."""
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = create_ocr_engine()
    return _ocr_engine
