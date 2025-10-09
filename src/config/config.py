"""Configuration management for the AI Agent."""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

BASE_DIR = Path(__file__).resolve().parents[2]

# Load environment variables from project root if available, then fall back to defaults
load_dotenv(BASE_DIR / ".env")
load_dotenv()


class AgentConfig(BaseModel):
    """Agent configuration settings."""
    
    # API Configuration
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"))
    gemini_max_output_tokens: int = Field(default_factory=lambda: int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "65536")))
    
    # Behavior Configuration
    debug_mode: bool = Field(default_factory=lambda: os.getenv("DEBUG_MODE", "false").lower() == "true")
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    
    # Performance Configuration
    max_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    action_delay: float = Field(default_factory=lambda: float(os.getenv("ACTION_DELAY", "0.5")))
    mouse_tolerance_px: int = Field(default_factory=lambda: int(os.getenv("MOUSE_TOLERANCE_PX", "2")))
    mouse_max_attempts: int = Field(default_factory=lambda: int(os.getenv("MOUSE_MAX_ATTEMPTS", "100")))
    mouse_path_segments: int = Field(default_factory=lambda: int(os.getenv("MOUSE_PATH_SEGMENTS", "1")))
    mouse_curve_jitter: int = Field(default_factory=lambda: int(os.getenv("MOUSE_CURVE_JITTER", "12")))
    mouse_base_duration: float = Field(default_factory=lambda: float(os.getenv("MOUSE_BASE_DURATION", "0.35")))
    mouse_micro_correction_duration: float = Field(default_factory=lambda: float(os.getenv("MOUSE_MICRO_CORRECTION_DURATION", "0.08")))
    api_timeout: int = 30
    screenshot_quality: int = 100
    screenshot_format: str = Field(default_factory=lambda: os.getenv("SCREENSHOT_FORMAT", "jpeg"))
    screenshot_scale: float = Field(default_factory=lambda: float(os.getenv("SCREENSHOT_SCALE", "1.0")))
    screenshot_max_width: int = Field(default_factory=lambda: int(os.getenv("SCREENSHOT_MAX_WIDTH", "0")))
    screenshot_max_height: int = Field(default_factory=lambda: int(os.getenv("SCREENSHOT_MAX_HEIGHT", "0")))
    screen_focus_size: int = Field(default_factory=lambda: int(os.getenv("SCREEN_FOCUS_SIZE", "420")))
    screen_focus_history: int = Field(default_factory=lambda: int(os.getenv("SCREEN_FOCUS_HISTORY", "3")))
    vision_image_format: str = Field(default_factory=lambda: os.getenv("VISION_IMAGE_FORMAT", "jpeg"))
    vision_image_quality: int = Field(default_factory=lambda: int(os.getenv("VISION_IMAGE_QUALITY", "75")))
    vision_image_scale: float = Field(default_factory=lambda: float(os.getenv("VISION_IMAGE_SCALE", "0.75")))
    vision_image_max_dim: int = Field(default_factory=lambda: int(os.getenv("VISION_IMAGE_MAX_DIM", "1600")))
    
    # Paths
    base_dir: Path = Field(default_factory=lambda: BASE_DIR)
    logs_dir: Path = Field(default_factory=lambda: BASE_DIR / "logs")
    screenshots_dir: Path = Field(default_factory=lambda: BASE_DIR / "screenshots")
    
    # Safety
    emergency_stop_key: str = Field(default_factory=lambda: os.getenv("EMERGENCY_STOP_KEY", "ctrl+shift+q"))
    max_task_duration: int = 300  # seconds
    no_limit_mode: bool = False
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    def __init__(self, **data):
        super().__init__(**data)

        logger = logging.getLogger("AgentConfig")
        if not logger.handlers:
            logging.basicConfig(level=logging.INFO)

        # Validate critical settings immediately, but allow empty keys during development/tests
        if not self.gemini_api_key or self.gemini_api_key == "your_api_key_here":
            logger.warning(
                "GEMINI_API_KEY is not configured; Gemini-powered features will be disabled "
                "until a valid key is provided."
            )
            self.gemini_api_key = ""
        
        # Create directories
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Normalize screenshot settings
        self.screenshot_format = self._normalize_format(self.screenshot_format, fallback="jpeg")
        self.screenshot_quality = self._clamp_int(self.screenshot_quality, minimum=1, maximum=100, default=80)
        self.screenshot_scale = self._clamp_float(self.screenshot_scale, minimum=0.2, maximum=1.0, default=1.0)
        self.screenshot_max_width = max(0, int(self.screenshot_max_width))
        self.screenshot_max_height = max(0, int(self.screenshot_max_height))

        self.vision_image_format = self._normalize_format(self.vision_image_format, fallback="jpeg")
        self.vision_image_quality = self._clamp_int(self.vision_image_quality, minimum=1, maximum=100, default=75)
        self.vision_image_scale = self._clamp_float(self.vision_image_scale, minimum=0.2, maximum=1.0, default=0.75)
        self.vision_image_max_dim = max(0, int(self.vision_image_max_dim))

    @staticmethod
    def _normalize_format(fmt: str, *, fallback: str = "jpeg") -> str:
        fmt_lower = (fmt or "").strip().lower()
        if fmt_lower == "jpg":
            fmt_lower = "jpeg"
        if fmt_lower not in {"png", "jpeg", "webp"}:
            return fallback
        return fmt_lower

    @staticmethod
    def _clamp_int(value: Optional[int], *, minimum: int, maximum: int, default: int) -> int:
        if value is None:
            return default
        try:
            parsed = int(value)
        except Exception:
            return default
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _clamp_float(value: Optional[float], *, minimum: float, maximum: float, default: float) -> float:
        if value is None:
            return default
        try:
            parsed = float(value)
        except Exception:
            return default
        return max(minimum, min(maximum, parsed))
    
    def validate_config(self) -> bool:
        """Validate configuration."""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required. Please set it in .env file.")
        return True

    def apply_no_limit_mode(self) -> None:
        """Elevate operational limits for unrestricted runs."""

        self.no_limit_mode = True
        self.gemini_max_output_tokens = max(self.gemini_max_output_tokens, 1_048_576)
        self.max_retries = max(self.max_retries, 50)
        self.mouse_max_attempts = max(self.mouse_max_attempts, 1_000)
        self.mouse_path_segments = max(self.mouse_path_segments, 10)
        self.max_task_duration = max(self.max_task_duration, 12 * 60 * 60)  # 12 hours
        self.api_timeout = max(self.api_timeout, 600)


# Global configuration instance
config = AgentConfig()
