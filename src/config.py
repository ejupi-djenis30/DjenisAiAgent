"""Central configuration utilities for DjenisAiAgent."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

__all__ = ["AgentConfig", "load_config", "config"]


def _load_dotenv(dotenv_path: Optional[Path]) -> None:
    """Load environment variables without overriding existing process values."""

    if dotenv_path is None:
        load_dotenv(override=False)
    else:
        load_dotenv(dotenv_path=dotenv_path, override=False)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a float") from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    truthy = {"1", "true", "t", "yes", "y", "on"}
    falsy = {"0", "false", "f", "no", "n", "off"}
    normalized = value.strip().lower()
    if normalized in truthy:
        return True
    if normalized in falsy:
        return False
    raise ValueError(
        f"Environment variable {name} must be boolean-like (one of {sorted(truthy | falsy)})"
    )


@dataclass
class AgentConfig:
    """Configuration container with environment overrides and validation."""

    # Gemini API Configuration (secret accessed lazily for safety)
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model_name: str = field(
        default_factory=lambda: os.getenv("DJENIS_GEMINI_MODEL", "gemini-1.5-pro-latest")
    )

    # Agent Behavior Parameters
    max_loop_turns: int = field(default_factory=lambda: _env_int("DJENIS_MAX_LOOP_TURNS", 50))
    action_timeout: int = field(default_factory=lambda: _env_int("DJENIS_ACTION_TIMEOUT", 30))
    screenshot_interval: float = field(
        default_factory=lambda: _env_float("DJENIS_SCREENSHOT_INTERVAL", 0.2)
    )

    # Model Parameters
    temperature: float = field(default_factory=lambda: _env_float("DJENIS_TEMPERATURE", 0.5))
    max_tokens: int = field(default_factory=lambda: _env_int("DJENIS_MAX_TOKENS", 60096))

    # Logging Configuration
    log_level: str = field(default_factory=lambda: os.getenv("DJENIS_LOG_LEVEL", "INFO"))
    enable_verbose_logging: bool = field(
        default_factory=lambda: _env_bool("DJENIS_VERBOSE_LOGGING", False)
    )

    # Screen Capture Settings
    screenshot_quality: int = field(
        default_factory=lambda: _env_int("DJENIS_SCREENSHOT_QUALITY", 100)
    )
    screenshot_format: str = field(
        default_factory=lambda: os.getenv("DJENIS_SCREENSHOT_FORMAT", "PNG")
    )
    stream_resize_factor: float = field(
        default_factory=lambda: _env_float("DJENIS_STREAM_RESIZE_FACTOR", 1.0)
    )
    stream_frame_quality: int = field(
        default_factory=lambda: _env_int("DJENIS_STREAM_FRAME_QUALITY", 88)
    )
    stream_max_fps: int = field(
        default_factory=lambda: _env_int("DJENIS_STREAM_MAX_FPS", 20)
    )
    perception_downscale: float = field(
        default_factory=lambda: _env_float("DJENIS_PERCEPTION_DOWNSCALE", 1.0)
    )

    # Miscellaneous
    config_source: str = field(default="environment", init=False)

    # Local transcription settings
    enable_local_transcription: bool = field(
        default_factory=lambda: _env_bool("DJENIS_LOCAL_TRANSCRIPTION", False)
    )
    vosk_model_path: str = field(
        default_factory=lambda: os.getenv("DJENIS_VOSK_MODEL_PATH", "")
    )
    transcription_sample_rate: int = field(
        default_factory=lambda: _env_int("DJENIS_TRANSCRIPTION_SAMPLE_RATE", 16000)
    )

    # Performance profile
    profile: str = field(default_factory=lambda: os.getenv("DJENIS_PROFILE", "default").lower())

    def validate(self) -> bool:
        """Validate configuration settings and ensure secrets are present."""

        if not self.gemini_api_key or self.gemini_api_key == "YOUR_API_KEY_HERE":
            raise ValueError(
                "GEMINI_API_KEY not set or using placeholder. Update .env or environment variables."
            )

        if self.max_loop_turns <= 0:
            raise ValueError("DJENIS_MAX_LOOP_TURNS must be greater than 0")

        if self.action_timeout <= 0:
            raise ValueError("DJENIS_ACTION_TIMEOUT must be greater than 0")

        if not 1 <= self.screenshot_quality <= 100:
            raise ValueError("DJENIS_SCREENSHOT_QUALITY must be between 1 and 100")

        if not 50 <= self.stream_frame_quality <= 100:
            raise ValueError("DJENIS_STREAM_FRAME_QUALITY must be between 50 and 100")

        if not 1 <= self.stream_max_fps <= 60:
            raise ValueError("DJENIS_STREAM_MAX_FPS must be between 1 and 60")

        if not 0.2 <= self.stream_resize_factor <= 1.0:
            raise ValueError("DJENIS_STREAM_RESIZE_FACTOR must be between 0.2 and 1.0")

        if not 0.3 <= self.perception_downscale <= 1.0:
            raise ValueError("DJENIS_PERCEPTION_DOWNSCALE must be between 0.3 and 1.0")

        if self.enable_local_transcription and not self.vosk_model_path.strip():
            raise ValueError(
                "DJENIS_LOCAL_TRANSCRIPTION è abilitato ma DJENIS_VOSK_MODEL_PATH non è impostato"
            )

        return True

    def safe_view(self) -> Dict[str, Any]:
        """Return a sanitized view of the configuration for logging/debugging."""

        data = asdict(self)
        if "gemini_api_key" in data:
            data["gemini_api_key"] = "***redacted***"
        return data

    def apply_profile(self) -> None:
        """Apply performance presets for ultra-fast or quality-focused modes."""

        profile = self.profile.strip().lower()

        if profile in {"performance", "turbo", "fast"}:
            self.screenshot_interval = min(self.screenshot_interval, 0.5)
            self.action_timeout = min(self.action_timeout, 20)
            self.stream_resize_factor = min(self.stream_resize_factor, 0.75)
            self.stream_frame_quality = max(self.stream_frame_quality, 92)
            self.stream_max_fps = max(self.stream_max_fps, 15)
            self.perception_downscale = min(self.perception_downscale, 0.85)
            self.screenshot_quality = max(self.screenshot_quality, 92)
            self.screenshot_format = "JPEG"
        elif profile in {"quality", "hires"}:
            self.screenshot_interval = max(self.screenshot_interval, 1.0)
            self.stream_resize_factor = 1.0
            self.stream_frame_quality = max(self.stream_frame_quality, 95)
            self.perception_downscale = 1.0
            self.screenshot_quality = max(self.screenshot_quality, 95)
            self.screenshot_format = "PNG"


def load_config(dotenv_path: Optional[os.PathLike[str]] = None) -> AgentConfig:
    """Load configuration from the environment, optionally pointing to a specific .env file."""

    path = Path(dotenv_path) if dotenv_path is not None else None
    _load_dotenv(path)
    config_obj = AgentConfig()
    config_obj.apply_profile()
    if path is not None:
        config_obj.config_source = str(path)
    return config_obj


# Global configuration instance loaded from the default environment
config = load_config()
