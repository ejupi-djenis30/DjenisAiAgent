"""Central configuration utilities for DjenisAiAgent."""

from __future__ import annotations

import ipaddress
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

__all__ = ["VERSION", "AgentConfig", "config", "load_config"]

#: Human-readable application version — keep in sync with pyproject.toml
VERSION: str = "0.3.0"


def _load_dotenv(dotenv_path: Path | None) -> None:
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
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a float") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"Environment variable {name} must be finite")
    return parsed


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


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    """Return a normalized, de-duplicated tuple from a comma-separated variable."""

    raw_value = os.getenv(name, default)
    values: list[str] = []
    for value in raw_value.split(","):
        normalized = value.strip()
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)


def _is_exact_hostname_or_ip(value: str, *, allow_ipv6: bool = True) -> bool:
    """Return whether *value* is an exact hostname/IP without URL syntax."""

    if not value or value != value.strip() or len(value) > 253:
        return False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        if ":" in value or "*" in value:
            return False
        labels = value.split(".")
        return all(
            1 <= len(label) <= 63
            and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label) is not None
            for label in labels
        )
    return allow_ipv6 or address.version == 4


_LOCAL_LLM_DOCKER_HOSTS = frozenset({"host.docker.internal", "local-llm", "ollama"})


def _validate_local_llm_endpoint(endpoint: str, backend: str, runtime_mode: str) -> None:
    """Require an exact credential-free endpoint that cannot target the public network."""

    if len(endpoint) > 2_048:
        raise ValueError("DJENIS_LOCAL_LLM_ENDPOINT must not exceed 2048 characters")
    if not endpoint.isascii() or any(character.isspace() for character in endpoint):
        raise ValueError("DJENIS_LOCAL_LLM_ENDPOINT must be an ASCII URL without whitespace")
    parsed = urlparse(endpoint)
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("DJENIS_LOCAL_LLM_ENDPOINT contains an invalid port") from exc
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("DJENIS_LOCAL_LLM_ENDPOINT must be an absolute credential-free HTTP URL")

    normalized_path = parsed.path.rstrip("/")
    expected_path = "" if backend == "ollama" else "/v1"
    if normalized_path != expected_path:
        raise ValueError(
            "DJENIS_LOCAL_LLM_ENDPOINT path must be empty for ollama or /v1 for openai-compatible"
        )

    hostname = parsed.hostname.casefold()
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        if not address.is_loopback:
            raise ValueError("DJENIS_LOCAL_LLM_ENDPOINT must use a loopback IP")
        return
    if hostname == "localhost":
        return
    if runtime_mode == "docker" and hostname in _LOCAL_LLM_DOCKER_HOSTS:
        return
    raise ValueError(
        "DJENIS_LOCAL_LLM_ENDPOINT must use localhost/loopback or a fixed local Docker host"
    )


def _resolve_runtime_mode() -> str:
    requested_mode = os.getenv("DJENIS_RUNTIME_MODE", "auto").strip().lower()
    valid_modes = {"auto", "windows", "docker", "headless"}
    if requested_mode not in valid_modes:
        raise ValueError(
            "Environment variable DJENIS_RUNTIME_MODE must be one of auto, windows, docker, headless"
        )

    if requested_mode != "auto":
        return requested_mode

    if os.getenv("SELENIUM_REMOTE_URL", "").strip():
        return "docker"
    if os.name == "nt":
        return "windows"
    return "headless"


def _resolve_browser_connection_mode() -> str:
    if os.getenv("SELENIUM_REMOTE_URL", "").strip():
        return "remote-selenium"
    return "local-debugger"


@dataclass
class AgentConfig:
    """Configuration container with environment overrides and validation."""

    # Local inference. No credential or cloud endpoint is accepted.
    local_llm_backend: str = field(
        default_factory=lambda: os.getenv("DJENIS_LOCAL_LLM_BACKEND", "ollama").strip().lower()
    )
    local_llm_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "DJENIS_LOCAL_LLM_ENDPOINT", "http://127.0.0.1:11434"
        ).strip()
    )
    local_llm_model: str = field(
        default_factory=lambda: os.getenv("DJENIS_LOCAL_LLM_MODEL", "qwen3-vl:8b").strip()
    )
    local_llm_expected_digest: str = field(
        default_factory=lambda: os.getenv("DJENIS_LOCAL_LLM_EXPECTED_DIGEST", "").strip().lower()
    )
    local_llm_vision_enabled: bool = field(
        default_factory=lambda: _env_bool("DJENIS_LOCAL_LLM_VISION", True)
    )
    local_llm_keep_alive: str = field(
        default_factory=lambda: os.getenv("DJENIS_LOCAL_LLM_KEEP_ALIVE", "10m").strip()
    )
    local_llm_seed: int = field(default_factory=lambda: _env_int("DJENIS_LOCAL_LLM_SEED", 0))
    local_llm_context_tokens: int = field(
        default_factory=lambda: _env_int("DJENIS_LOCAL_LLM_CONTEXT_TOKENS", 65_536)
    )
    local_llm_response_max_bytes: int = field(
        default_factory=lambda: _env_int("DJENIS_LOCAL_LLM_RESPONSE_MAX_BYTES", 1_048_576)
    )
    local_llm_image_max_bytes: int = field(
        default_factory=lambda: _env_int("DJENIS_LOCAL_LLM_IMAGE_MAX_BYTES", 5 * 1024 * 1024)
    )
    local_llm_vision_max_dimension: int = field(
        default_factory=lambda: _env_int("DJENIS_LOCAL_LLM_VISION_MAX_DIMENSION", 1_600)
    )
    local_llm_vision_quality: int = field(
        default_factory=lambda: _env_int("DJENIS_LOCAL_LLM_VISION_QUALITY", 80)
    )

    # Agent Behavior Parameters
    max_loop_turns: int = field(default_factory=lambda: _env_int("DJENIS_MAX_LOOP_TURNS", 50))
    action_timeout: int = field(default_factory=lambda: _env_int("DJENIS_ACTION_TIMEOUT", 45))
    screenshot_interval: float = field(
        default_factory=lambda: _env_float("DJENIS_SCREENSHOT_INTERVAL", 0.1)
    )

    # Model Parameters
    temperature: float = field(default_factory=lambda: _env_float("DJENIS_TEMPERATURE", 0.0))
    max_tokens: int = field(default_factory=lambda: _env_int("DJENIS_MAX_TOKENS", 4096))

    # API Timeout and Retry Configuration
    api_timeout: int = field(default_factory=lambda: _env_int("DJENIS_API_TIMEOUT", 120))
    api_max_retries: int = field(default_factory=lambda: _env_int("DJENIS_API_MAX_RETRIES", 3))
    api_retry_delay: float = field(
        default_factory=lambda: _env_float("DJENIS_API_RETRY_DELAY", 2.0)
    )
    task_timeout: int = field(default_factory=lambda: _env_int("DJENIS_TASK_TIMEOUT", 900))
    command_max_chars: int = field(
        default_factory=lambda: _env_int("DJENIS_COMMAND_MAX_CHARS", 4096)
    )
    observation_max_chars: int = field(
        default_factory=lambda: _env_int("DJENIS_OBSERVATION_MAX_CHARS", 16_384)
    )
    prompt_history_max_chars: int = field(
        default_factory=lambda: _env_int("DJENIS_PROMPT_HISTORY_MAX_CHARS", 65_536)
    )
    ui_tree_max_chars: int = field(
        default_factory=lambda: _env_int("DJENIS_UI_TREE_MAX_CHARS", 65_536)
    )
    tool_argument_max_chars: int = field(
        default_factory=lambda: _env_int("DJENIS_TOOL_ARGUMENT_MAX_CHARS", 16_384)
    )
    max_repeated_actions: int = field(
        default_factory=lambda: _env_int("DJENIS_MAX_REPEATED_ACTIONS", 2)
    )
    completion_evidence_min_chars: int = field(
        default_factory=lambda: _env_int("DJENIS_COMPLETION_EVIDENCE_MIN_CHARS", 12)
    )

    # Logging Configuration
    log_level: str = field(default_factory=lambda: os.getenv("DJENIS_LOG_LEVEL", "INFO"))
    enable_verbose_logging: bool = field(
        default_factory=lambda: _env_bool("DJENIS_VERBOSE_LOGGING", False)
    )
    enable_audit_log: bool = field(
        default_factory=lambda: _env_bool("DJENIS_ENABLE_AUDIT_LOG", True)
    )
    audit_log_path: str = field(
        default_factory=lambda: os.getenv("DJENIS_AUDIT_LOG_PATH", "logs/agent-audit.jsonl")
    )
    audit_log_max_bytes: int = field(
        default_factory=lambda: _env_int("DJENIS_AUDIT_LOG_MAX_BYTES", 10 * 1024 * 1024)
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
        default_factory=lambda: _env_int("DJENIS_STREAM_FRAME_QUALITY", 80)
    )
    stream_max_fps: int = field(default_factory=lambda: _env_int("DJENIS_STREAM_MAX_FPS", 30))
    perception_downscale: float = field(
        default_factory=lambda: _env_float("DJENIS_PERCEPTION_DOWNSCALE", 1.0)
    )

    # Miscellaneous
    config_source: str = field(default="environment", init=False)

    # Local transcription settings
    enable_local_transcription: bool = field(
        default_factory=lambda: _env_bool("DJENIS_LOCAL_TRANSCRIPTION", False)
    )
    vosk_model_path: str = field(default_factory=lambda: os.getenv("DJENIS_VOSK_MODEL_PATH", ""))
    transcription_sample_rate: int = field(
        default_factory=lambda: _env_int("DJENIS_TRANSCRIPTION_SAMPLE_RATE", 16000)
    )

    # Shell command timeout (seconds)
    shell_timeout: int = field(default_factory=lambda: _env_int("DJENIS_SHELL_TIMEOUT", 60))
    shell_output_max_bytes: int = field(
        default_factory=lambda: _env_int("DJENIS_SHELL_OUTPUT_MAX_BYTES", 1_048_576)
    )

    # UI snapshot maximum traversal depth
    snapshot_depth: int = field(default_factory=lambda: _env_int("DJENIS_SNAPSHOT_DEPTH", 4))

    # Locator LRU cache capacity
    locator_cache_size: int = field(
        default_factory=lambda: _env_int("DJENIS_LOCATOR_CACHE_SIZE", 64)
    )

    # Maximum clipboard content size in bytes (safety limit)
    clipboard_max_bytes: int = field(
        default_factory=lambda: _env_int("DJENIS_CLIPBOARD_MAX_BYTES", 1_048_576)  # 1 MiB
    )

    # Performance profile
    profile: str = field(default_factory=lambda: os.getenv("DJENIS_PROFILE", "default").lower())
    runtime_mode: str = field(default_factory=_resolve_runtime_mode)
    browser_connection_mode: str = field(default_factory=_resolve_browser_connection_mode)
    selenium_remote_url: str = field(default_factory=lambda: os.getenv("SELENIUM_REMOTE_URL", ""))
    browser_debugging_host: str = field(
        default_factory=lambda: os.getenv("DJENIS_BROWSER_DEBUGGING_HOST", "127.0.0.1")
    )
    browser_debugging_port: int = field(
        default_factory=lambda: _env_int("DJENIS_BROWSER_DEBUGGING_PORT", 9222)
    )

    # Web security. Web mode deliberately refuses to start without an operator token.
    web_host: str = field(default_factory=lambda: os.getenv("DJENIS_WEB_HOST", "127.0.0.1"))
    web_auth_token: str = field(default_factory=lambda: os.getenv("DJENIS_WEB_AUTH_TOKEN", ""))
    web_allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: _env_csv("DJENIS_WEB_ALLOWED_ORIGINS")
    )
    web_session_ttl: int = field(default_factory=lambda: _env_int("DJENIS_WEB_SESSION_TTL", 3600))
    web_rate_limit_per_minute: int = field(
        default_factory=lambda: _env_int("DJENIS_WEB_RATE_LIMIT_PER_MINUTE", 60)
    )
    web_login_rate_limit_per_minute: int = field(
        default_factory=lambda: _env_int("DJENIS_WEB_LOGIN_RATE_LIMIT_PER_MINUTE", 10)
    )
    web_upload_max_bytes: int = field(
        default_factory=lambda: _env_int("DJENIS_WEB_UPLOAD_MAX_BYTES", 5 * 1024 * 1024)
    )
    web_session_cookie_secure: bool = field(
        default_factory=lambda: _env_bool("DJENIS_WEB_SESSION_COOKIE_SECURE", False)
    )
    web_max_sessions: int = field(default_factory=lambda: _env_int("DJENIS_WEB_MAX_SESSIONS", 32))
    web_max_connections: int = field(
        default_factory=lambda: _env_int("DJENIS_WEB_MAX_CONNECTIONS", 8)
    )
    web_socket_send_timeout: float = field(
        default_factory=lambda: _env_float("DJENIS_WEB_SOCKET_SEND_TIMEOUT", 5.0)
    )
    web_stream_max_clients: int = field(
        default_factory=lambda: _env_int("DJENIS_WEB_STREAM_MAX_CLIENTS", 2)
    )
    web_transcription_max_concurrency: int = field(
        default_factory=lambda: _env_int("DJENIS_WEB_TRANSCRIPTION_MAX_CONCURRENCY", 1)
    )
    web_transcription_timeout: float = field(
        default_factory=lambda: _env_float("DJENIS_WEB_TRANSCRIPTION_TIMEOUT", 60.0)
    )

    # Tool permissions. Observe-only is the safe default.
    permission_tier: str = field(
        default_factory=lambda: os.getenv("DJENIS_PERMISSION_TIER", "observe").strip().lower()
    )
    confirm_dangerous_actions: bool = field(
        default_factory=lambda: _env_bool("DJENIS_CONFIRM_DANGEROUS_ACTIONS", False)
    )
    allowed_paths: tuple[str, ...] = field(
        default_factory=lambda: _env_csv("DJENIS_ALLOWED_PATHS", os.getcwd())
    )
    allowed_applications: tuple[str, ...] = field(
        default_factory=lambda: _env_csv("DJENIS_ALLOWED_APPLICATIONS")
    )
    allowed_shell_commands: tuple[str, ...] = field(
        default_factory=lambda: _env_csv("DJENIS_ALLOWED_SHELL_COMMANDS")
    )
    allowed_url_hosts: tuple[str, ...] = field(
        default_factory=lambda: _env_csv("DJENIS_ALLOWED_URL_HOSTS")
    )

    def validate(self) -> bool:
        """Validate local inference, safety, and resource settings."""

        if self.local_llm_backend not in {"ollama", "openai-compatible"}:
            raise ValueError("DJENIS_LOCAL_LLM_BACKEND must be ollama or openai-compatible")
        if (
            not self.local_llm_model
            or len(self.local_llm_model) > 256
            or any(character.isspace() for character in self.local_llm_model)
        ):
            raise ValueError(
                "DJENIS_LOCAL_LLM_MODEL must be a non-empty identifier without whitespace"
            )
        if re.search(
            r"(?:^|[-:/.])cloud(?:$|[-:/.])",
            self.local_llm_model.casefold(),
        ):
            raise ValueError("DJENIS_LOCAL_LLM_MODEL must not select a cloud model")
        if self.local_llm_expected_digest:
            if self.local_llm_backend != "ollama":
                raise ValueError(
                    "DJENIS_LOCAL_LLM_EXPECTED_DIGEST is supported only by the ollama backend"
                )
            if re.fullmatch(r"[0-9a-f]{64}", self.local_llm_expected_digest) is None:
                raise ValueError(
                    "DJENIS_LOCAL_LLM_EXPECTED_DIGEST must be a lowercase SHA-256 digest"
                )
        _validate_local_llm_endpoint(
            self.local_llm_endpoint,
            self.local_llm_backend,
            self.runtime_mode,
        )
        if re.fullmatch(r"(?:0|-?\d+(?:ns|us|µs|ms|s|m|h))", self.local_llm_keep_alive) is None:
            raise ValueError("DJENIS_LOCAL_LLM_KEEP_ALIVE must be 0 or a duration such as 10m")
        if not 4_096 <= self.local_llm_context_tokens <= 262_144:
            raise ValueError("DJENIS_LOCAL_LLM_CONTEXT_TOKENS must be between 4096 and 262144")
        if not 1_024 <= self.local_llm_response_max_bytes <= 4 * 1024 * 1024:
            raise ValueError("DJENIS_LOCAL_LLM_RESPONSE_MAX_BYTES must be between 1024 and 4194304")
        if not 64 * 1024 <= self.local_llm_image_max_bytes <= 20 * 1024 * 1024:
            raise ValueError("DJENIS_LOCAL_LLM_IMAGE_MAX_BYTES must be between 65536 and 20971520")
        if not 256 <= self.local_llm_vision_max_dimension <= 4_096:
            raise ValueError("DJENIS_LOCAL_LLM_VISION_MAX_DIMENSION must be between 256 and 4096")
        if not 40 <= self.local_llm_vision_quality <= 95:
            raise ValueError("DJENIS_LOCAL_LLM_VISION_QUALITY must be between 40 and 95")

        for name, value in (
            ("DJENIS_SCREENSHOT_INTERVAL", self.screenshot_interval),
            ("DJENIS_TEMPERATURE", self.temperature),
            ("DJENIS_API_RETRY_DELAY", self.api_retry_delay),
            ("DJENIS_STREAM_RESIZE_FACTOR", self.stream_resize_factor),
            ("DJENIS_PERCEPTION_DOWNSCALE", self.perception_downscale),
            ("DJENIS_WEB_SOCKET_SEND_TIMEOUT", self.web_socket_send_timeout),
            ("DJENIS_WEB_TRANSCRIPTION_TIMEOUT", self.web_transcription_timeout),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")

        if not 1 <= self.max_loop_turns <= 200:
            raise ValueError("DJENIS_MAX_LOOP_TURNS must be between 1 and 200")

        if self.action_timeout <= 0:
            raise ValueError("DJENIS_ACTION_TIMEOUT must be greater than 0")

        if self.screenshot_interval < 0:
            raise ValueError("DJENIS_SCREENSHOT_INTERVAL cannot be negative")

        if not 0 <= self.temperature <= 2:
            raise ValueError("DJENIS_TEMPERATURE must be between 0 and 2")

        if self.log_level.strip().upper() not in {
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        }:
            raise ValueError("DJENIS_LOG_LEVEL must be a standard Python logging level")

        if self.profile.strip().lower() not in {
            "default",
            "performance",
            "turbo",
            "fast",
            "quality",
            "hires",
        }:
            raise ValueError("DJENIS_PROFILE is not a supported performance profile")

        if self.max_tokens <= 0:
            raise ValueError("DJENIS_MAX_TOKENS must be greater than 0")

        if self.api_timeout <= 0:
            raise ValueError("DJENIS_API_TIMEOUT must be greater than 0")

        if not 1 <= self.api_max_retries <= 10:
            raise ValueError("DJENIS_API_MAX_RETRIES must be between 1 and 10")

        if self.api_retry_delay < 0:
            raise ValueError("DJENIS_API_RETRY_DELAY cannot be negative")

        if not 1 <= self.screenshot_quality <= 100:
            raise ValueError("DJENIS_SCREENSHOT_QUALITY must be between 1 and 100")

        if self.screenshot_format.strip().upper() not in {"PNG", "JPEG"}:
            raise ValueError("DJENIS_SCREENSHOT_FORMAT must be PNG or JPEG")

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
                "DJENIS_VOSK_MODEL_PATH must be set when DJENIS_LOCAL_TRANSCRIPTION is enabled"
            )

        if self.shell_timeout <= 0:
            raise ValueError("DJENIS_SHELL_TIMEOUT must be greater than 0")

        if self.shell_output_max_bytes <= 0:
            raise ValueError("DJENIS_SHELL_OUTPUT_MAX_BYTES must be greater than 0")

        if self.task_timeout <= 0:
            raise ValueError("DJENIS_TASK_TIMEOUT must be greater than 0")

        for name, bounded_size in (
            ("DJENIS_COMMAND_MAX_CHARS", self.command_max_chars),
            ("DJENIS_OBSERVATION_MAX_CHARS", self.observation_max_chars),
            ("DJENIS_PROMPT_HISTORY_MAX_CHARS", self.prompt_history_max_chars),
            ("DJENIS_UI_TREE_MAX_CHARS", self.ui_tree_max_chars),
            ("DJENIS_TOOL_ARGUMENT_MAX_CHARS", self.tool_argument_max_chars),
            ("DJENIS_MAX_REPEATED_ACTIONS", self.max_repeated_actions),
            ("DJENIS_COMPLETION_EVIDENCE_MIN_CHARS", self.completion_evidence_min_chars),
        ):
            if bounded_size <= 0:
                raise ValueError(f"{name} must be greater than 0")
        if self.tool_argument_max_chars > 1_048_576:
            raise ValueError("DJENIS_TOOL_ARGUMENT_MAX_CHARS must not exceed 1048576")
        if self.max_repeated_actions > 10:
            raise ValueError("DJENIS_MAX_REPEATED_ACTIONS must not exceed 10")
        if self.completion_evidence_min_chars > 4_096:
            raise ValueError("DJENIS_COMPLETION_EVIDENCE_MIN_CHARS must not exceed 4096")
        if self.tool_argument_max_chars < self.completion_evidence_min_chars + 128:
            raise ValueError(
                "DJENIS_TOOL_ARGUMENT_MAX_CHARS must leave room for completion evidence "
                "and the finish_task JSON envelope"
            )

        if self.snapshot_depth <= 0:
            raise ValueError("DJENIS_SNAPSHOT_DEPTH must be greater than 0")

        if self.locator_cache_size <= 0:
            raise ValueError("DJENIS_LOCATOR_CACHE_SIZE must be greater than 0")

        if self.clipboard_max_bytes <= 0:
            raise ValueError("DJENIS_CLIPBOARD_MAX_BYTES must be greater than 0")

        if self.enable_audit_log and not self.audit_log_path.strip():
            raise ValueError("DJENIS_AUDIT_LOG_PATH must be set when audit logging is enabled")

        if self.audit_log_max_bytes <= 0:
            raise ValueError("DJENIS_AUDIT_LOG_MAX_BYTES must be greater than 0")

        if self.runtime_mode not in {"windows", "docker", "headless"}:
            raise ValueError("DJENIS_RUNTIME_MODE resolved to an unsupported value")

        if self.browser_connection_mode not in {"local-debugger", "remote-selenium"}:
            raise ValueError("Browser connection mode resolved to an unsupported value")

        if self.selenium_remote_url.strip():
            selenium_url = urlparse(self.selenium_remote_url)
            try:
                _ = selenium_url.port
            except ValueError as exc:
                raise ValueError("SELENIUM_REMOTE_URL contains an invalid port") from exc
            if (
                selenium_url.scheme not in {"http", "https"}
                or not selenium_url.hostname
                or selenium_url.username
                or selenium_url.password
            ):
                raise ValueError(
                    "SELENIUM_REMOTE_URL must be an absolute credential-free HTTP(S) URL"
                )

        if not 1 <= self.browser_debugging_port <= 65_535:
            raise ValueError("DJENIS_BROWSER_DEBUGGING_PORT must be between 1 and 65535")
        if not _is_exact_hostname_or_ip(self.browser_debugging_host, allow_ipv6=False):
            raise ValueError(
                "DJENIS_BROWSER_DEBUGGING_HOST must be an exact hostname or IPv4 address"
            )

        if self.permission_tier not in {"observe", "interact", "system"}:
            raise ValueError("DJENIS_PERMISSION_TIER must be one of observe, interact, or system")

        for name, executable_paths in (
            ("DJENIS_ALLOWED_APPLICATIONS", self.allowed_applications),
            ("DJENIS_ALLOWED_SHELL_COMMANDS", self.allowed_shell_commands),
        ):
            if any(not Path(entry).expanduser().is_absolute() for entry in executable_paths):
                raise ValueError(f"{name} entries must be absolute executable paths")

        for host in self.allowed_url_hosts:
            if not _is_exact_hostname_or_ip(host):
                raise ValueError(
                    "DJENIS_ALLOWED_URL_HOSTS entries must be exact hostnames or IP addresses"
                )

        if not self.web_host.strip():
            raise ValueError("DJENIS_WEB_HOST cannot be empty")
        for origin in self.web_allowed_origins:
            parsed_origin = urlparse(origin)
            try:
                _ = parsed_origin.port
            except ValueError as exc:
                raise ValueError("DJENIS_WEB_ALLOWED_ORIGINS contains an invalid port") from exc
            if (
                parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.hostname
                or parsed_origin.username
                or parsed_origin.password
                or parsed_origin.path not in {"", "/"}
                or parsed_origin.params
                or parsed_origin.query
                or parsed_origin.fragment
            ):
                raise ValueError(
                    "DJENIS_WEB_ALLOWED_ORIGINS entries must be exact credential-free HTTP(S) origins"
                )

        for name, value in (
            ("DJENIS_WEB_SESSION_TTL", self.web_session_ttl),
            ("DJENIS_WEB_RATE_LIMIT_PER_MINUTE", self.web_rate_limit_per_minute),
            (
                "DJENIS_WEB_LOGIN_RATE_LIMIT_PER_MINUTE",
                self.web_login_rate_limit_per_minute,
            ),
            ("DJENIS_WEB_UPLOAD_MAX_BYTES", self.web_upload_max_bytes),
            ("DJENIS_WEB_MAX_SESSIONS", self.web_max_sessions),
            ("DJENIS_WEB_MAX_CONNECTIONS", self.web_max_connections),
            ("DJENIS_WEB_STREAM_MAX_CLIENTS", self.web_stream_max_clients),
            (
                "DJENIS_WEB_TRANSCRIPTION_MAX_CONCURRENCY",
                self.web_transcription_max_concurrency,
            ),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be greater than 0")

        for name, positive_float in (
            ("DJENIS_WEB_SOCKET_SEND_TIMEOUT", self.web_socket_send_timeout),
            ("DJENIS_WEB_TRANSCRIPTION_TIMEOUT", self.web_transcription_timeout),
        ):
            if positive_float <= 0:
                raise ValueError(f"{name} must be greater than 0")

        return True

    def validate_web(self) -> bool:
        """Validate the additional controls required before exposing web mode."""

        self.validate()
        if len(self.web_auth_token) < 24:
            raise ValueError(
                "DJENIS_WEB_AUTH_TOKEN must contain at least 24 characters in web mode"
            )
        return True

    def safe_view(self) -> dict[str, Any]:
        """Return a sanitized view of the configuration for logging/debugging."""

        data = asdict(self)
        redacted_value = "***" + "redacted" + "***"
        if "web_auth_token" in data:
            data["web_auth_token"] = redacted_value
        return data

    def permits(self, required_tier: str) -> bool:
        """Return whether the configured operator tier includes the requested capability."""

        ranks = {"observe": 0, "interact": 1, "system": 2}
        return ranks.get(self.permission_tier, -1) >= ranks.get(required_tier, 99)

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

    def uses_remote_selenium(self) -> bool:
        """Return True when browser automation is expected to use a remote Selenium endpoint."""

        return self.browser_connection_mode == "remote-selenium"

    def supports_native_desktop(self) -> bool:
        """Return True when the runtime is expected to have direct access to the host desktop."""

        return self.runtime_mode == "windows" and not self.uses_remote_selenium()

    def supports_real_browser_media(self) -> bool:
        """Return True when browser media flows can rely on a real host browser session."""

        return self.browser_connection_mode == "local-debugger" and self.runtime_mode == "windows"


def load_config(dotenv_path: os.PathLike[str] | None = None) -> AgentConfig:
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
