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
    
    # Behavior Configuration
    debug_mode: bool = Field(default_factory=lambda: os.getenv("DEBUG_MODE", "false").lower() == "true")
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    enable_screen_recording: bool = Field(default_factory=lambda: os.getenv("ENABLE_SCREEN_RECORDING", "false").lower() == "true")
    
    # Performance Configuration
    max_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    action_delay: float = Field(default_factory=lambda: float(os.getenv("ACTION_DELAY", "0.5")))
    api_timeout: int = 30
    screenshot_quality: int = 85
    
    # Paths
    base_dir: Path = Field(default_factory=lambda: Path(__file__).parent)
    logs_dir: Path = Field(default_factory=lambda: Path(__file__).parent / "logs")
    screenshots_dir: Path = Field(default_factory=lambda: Path(__file__).parent / "screenshots")
    
    # Safety
    emergency_stop_key: str = "ctrl+shift+esc"
    max_task_duration: int = 300  # seconds
    
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


# Global configuration instance
config = AgentConfig()
