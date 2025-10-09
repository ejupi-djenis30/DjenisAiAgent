"""Configuration management for the AI Agent."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class AgentConfig(BaseModel):
    """Agent configuration settings."""
    
    # API Configuration
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-flash-latest"))
    gemini_max_output_tokens: int = Field(default_factory=lambda: int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "32768")))
    
    # Behavior Configuration
    debug_mode: bool = Field(default_factory=lambda: os.getenv("DEBUG_MODE", "false").lower() == "true")
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    enable_screen_recording: bool = Field(default_factory=lambda: os.getenv("ENABLE_SCREEN_RECORDING", "false").lower() == "true")
    
    # Performance Configuration
    max_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    action_delay: float = Field(default_factory=lambda: float(os.getenv("ACTION_DELAY", "0.5")))
    mouse_tolerance_px: int = Field(default_factory=lambda: int(os.getenv("MOUSE_TOLERANCE_PX", "2")))
    mouse_max_attempts: int = Field(default_factory=lambda: int(os.getenv("MOUSE_MAX_ATTEMPTS", "100")))
    mouse_path_segments: int = Field(default_factory=lambda: int(os.getenv("MOUSE_PATH_SEGMENTS", "2")))
    mouse_curve_jitter: int = Field(default_factory=lambda: int(os.getenv("MOUSE_CURVE_JITTER", "18")))
    mouse_base_duration: float = Field(default_factory=lambda: float(os.getenv("MOUSE_BASE_DURATION", "0.35")))
    mouse_micro_correction_duration: float = Field(default_factory=lambda: float(os.getenv("MOUSE_MICRO_CORRECTION_DURATION", "0.08")))
    api_timeout: int = 30
    screenshot_quality: int = 85
    
    # Paths
    base_dir: Path = Field(default_factory=lambda: Path(__file__).parent)
    logs_dir: Path = Field(default_factory=lambda: Path(__file__).parent / "logs")
    screenshots_dir: Path = Field(default_factory=lambda: Path(__file__).parent / "screenshots")
    
    # Safety
    emergency_stop_key: str = "ctrl+shift+esc"
    max_task_duration: int = 300  # seconds
    no_limit_mode: bool = False
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, **data):
        super().__init__(**data)
        # Create directories
        self.logs_dir.mkdir(exist_ok=True)
        self.screenshots_dir.mkdir(exist_ok=True)
    
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
