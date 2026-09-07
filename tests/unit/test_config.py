"""Unit tests for src/config.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import AgentConfig, load_config

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestAgentConfigDefaults:
    def test_default_local_model_runtime(self, fake_env: None) -> None:
        cfg = load_config()

        assert cfg.local_llm_backend == "ollama"
        assert cfg.local_llm_endpoint == "http://127.0.0.1:11434"
        assert cfg.local_llm_model == "qwen3-vl:8b"
        assert cfg.local_llm_expected_digest == ""
        assert cfg.local_llm_context_tokens == 65_536
        assert cfg.local_llm_vision_enabled is True
        assert cfg.temperature == 0.0

    def test_default_max_loop_turns(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.max_loop_turns == 50

    def test_default_execution_guard_limits(self) -> None:
        cfg = AgentConfig()

        assert cfg.tool_argument_max_chars == 16_384
        assert cfg.max_repeated_actions == 2
        assert cfg.completion_evidence_min_chars == 12

    def test_default_action_timeout(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.action_timeout == 45

    def test_default_api_timeout(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.api_timeout == 120

    def test_default_task_timeout(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.task_timeout == 900

    def test_default_log_level(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.log_level == "INFO"

    def test_audit_logging_enabled_by_default(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.enable_audit_log is True
        assert cfg.audit_log_path == "logs/agent-audit.jsonl"

    def test_default_stream_max_fps(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.stream_max_fps == 30

    def test_default_local_transcription_disabled(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.enable_local_transcription is False

    def test_default_browser_connection_mode_is_local_debugger(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.browser_connection_mode == "local-debugger"
        assert cfg.uses_remote_selenium() is False

    def test_default_permission_tier_is_observe(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.permission_tier == "observe"
        assert cfg.confirm_dangerous_actions is False

    def test_private_url_hosts_require_explicit_allowlist(self) -> None:
        cfg = AgentConfig()

        assert cfg.allowed_url_hosts == ()


# ---------------------------------------------------------------------------
# Environment overrides
# ---------------------------------------------------------------------------


class TestAgentConfigEnvOverrides:
    def test_max_loop_turns_from_env(self, fake_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DJENIS_MAX_LOOP_TURNS", "25")
        cfg = load_config()
        assert cfg.max_loop_turns == 25

    def test_local_model_settings_from_env(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DJENIS_LOCAL_LLM_BACKEND", "openai-compatible")
        monkeypatch.setenv("DJENIS_LOCAL_LLM_ENDPOINT", "http://localhost:8080/v1")
        monkeypatch.setenv("DJENIS_LOCAL_LLM_MODEL", "local-tool-model")
        monkeypatch.setenv("DJENIS_LOCAL_LLM_VISION", "false")
        cfg = load_config()

        assert cfg.local_llm_backend == "openai-compatible"
        assert cfg.local_llm_endpoint == "http://localhost:8080/v1"
        assert cfg.local_llm_model == "local-tool-model"
        assert cfg.local_llm_vision_enabled is False

    def test_local_context_window_from_env(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DJENIS_LOCAL_LLM_CONTEXT_TOKENS", "131072")

        cfg = load_config()

        assert cfg.local_llm_context_tokens == 131_072

    def test_expected_model_digest_is_normalized_from_env(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DJENIS_LOCAL_LLM_EXPECTED_DIGEST", "A" * 64)

        cfg = load_config()

        assert cfg.local_llm_expected_digest == "a" * 64

    def test_boolean_env_truthy_variants(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for truthy in ("1", "true", "True", "yes", "on"):
            monkeypatch.setenv("DJENIS_VERBOSE_LOGGING", truthy)
            cfg = load_config()
            assert cfg.enable_verbose_logging is True, f"Failed for value: {truthy!r}"

    def test_boolean_env_falsy_variants(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for falsy in ("0", "false", "False", "no", "off"):
            monkeypatch.setenv("DJENIS_VERBOSE_LOGGING", falsy)
            cfg = load_config()
            assert cfg.enable_verbose_logging is False, f"Failed for value: {falsy!r}"

    def test_invalid_int_env_raises(self, fake_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DJENIS_MAX_LOOP_TURNS", "not_an_int")
        with pytest.raises(ValueError, match="must be an integer"):
            load_config()

    def test_invalid_bool_env_raises(self, fake_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DJENIS_VERBOSE_LOGGING", "maybe")
        with pytest.raises(ValueError):
            load_config()

    def test_remote_selenium_env_switches_runtime_capabilities(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SELENIUM_REMOTE_URL", "http://chrome:4444/wd/hub")

        cfg = load_config()

        assert cfg.runtime_mode == "docker"
        assert cfg.browser_connection_mode == "remote-selenium"
        assert cfg.uses_remote_selenium() is True
        assert cfg.supports_native_desktop() is False
        assert cfg.supports_real_browser_media() is False

    def test_invalid_runtime_mode_raises(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DJENIS_RUNTIME_MODE", "invalid")

        with pytest.raises(ValueError, match="DJENIS_RUNTIME_MODE"):
            load_config()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestAgentConfigValidation:
    @pytest.mark.parametrize(
        "model_name", ["", "   ", "local model", "x" * 257, "qwen-cloud:latest"]
    )
    def test_invalid_local_model_name_raises(self, model_name: str) -> None:
        cfg = AgentConfig(local_llm_model=model_name)

        with pytest.raises(ValueError, match="DJENIS_LOCAL_LLM_MODEL"):
            cfg.validate()

    @pytest.mark.parametrize("backend", ["", "openai", "cloud", "OLLAMA"])
    def test_invalid_local_backend_raises(self, backend: str) -> None:
        cfg = AgentConfig(local_llm_backend=backend)

        with pytest.raises(ValueError, match="DJENIS_LOCAL_LLM_BACKEND"):
            cfg.validate()

    @pytest.mark.parametrize("digest", ["abc", "A" * 64, "g" * 64, "a" * 63])
    def test_invalid_expected_model_digest_raises(self, digest: str) -> None:
        cfg = AgentConfig(local_llm_expected_digest=digest)

        with pytest.raises(ValueError, match="DJENIS_LOCAL_LLM_EXPECTED_DIGEST"):
            cfg.validate()

    def test_expected_model_digest_is_ollama_only(self) -> None:
        cfg = AgentConfig(
            local_llm_backend="openai-compatible",
            local_llm_endpoint="http://127.0.0.1:8080/v1",
            local_llm_expected_digest="a" * 64,
        )

        with pytest.raises(ValueError, match="supported only by the ollama backend"):
            cfg.validate()

    @pytest.mark.parametrize(
        "endpoint",
        [
            "https://127.0.0.1:11434",
            "http://user:secret@127.0.0.1:11434",
            "http://8.8.8.8:11434",
            "http://example.com:11434",
            "http://127.0.0.1:11434/api",
            "http://127.0.0.1:11434?query=1",
            "file:///tmp/model",
        ],
    )
    def test_local_endpoint_rejects_nonlocal_or_ambiguous_targets(self, endpoint: str) -> None:
        cfg = AgentConfig(local_llm_endpoint=endpoint)

        with pytest.raises(ValueError, match="DJENIS_LOCAL_LLM_ENDPOINT"):
            cfg.validate()

    def test_openai_compatible_endpoint_requires_v1_path(self) -> None:
        cfg = AgentConfig(
            local_llm_backend="openai-compatible",
            local_llm_endpoint="http://127.0.0.1:8080",
        )

        with pytest.raises(ValueError, match="DJENIS_LOCAL_LLM_ENDPOINT"):
            cfg.validate()

        cfg.local_llm_endpoint = "http://127.0.0.1:8080/v1"
        assert cfg.validate() is True

    def test_fixed_ollama_service_name_is_allowed_only_in_docker(self) -> None:
        cfg = AgentConfig(local_llm_endpoint="http://ollama:11434", runtime_mode="windows")
        with pytest.raises(ValueError, match="DJENIS_LOCAL_LLM_ENDPOINT"):
            cfg.validate()

        cfg.runtime_mode = "docker"
        assert cfg.validate() is True

    @pytest.mark.parametrize("keep_alive", ["", "forever", "10 minutes", "1d"])
    def test_invalid_local_keep_alive_raises(self, keep_alive: str) -> None:
        cfg = AgentConfig(local_llm_keep_alive=keep_alive)

        with pytest.raises(ValueError, match="DJENIS_LOCAL_LLM_KEEP_ALIVE"):
            cfg.validate()

    @pytest.mark.parametrize(
        ("attribute", "value", "environment_name"),
        [
            ("local_llm_context_tokens", 4_095, "DJENIS_LOCAL_LLM_CONTEXT_TOKENS"),
            ("local_llm_context_tokens", 262_145, "DJENIS_LOCAL_LLM_CONTEXT_TOKENS"),
            ("local_llm_response_max_bytes", 1023, "DJENIS_LOCAL_LLM_RESPONSE_MAX_BYTES"),
            ("local_llm_image_max_bytes", 1024, "DJENIS_LOCAL_LLM_IMAGE_MAX_BYTES"),
            ("local_llm_vision_max_dimension", 128, "DJENIS_LOCAL_LLM_VISION_MAX_DIMENSION"),
            ("local_llm_vision_quality", 39, "DJENIS_LOCAL_LLM_VISION_QUALITY"),
        ],
    )
    def test_local_model_resource_bounds_fail_closed(
        self, attribute: str, value: int, environment_name: str
    ) -> None:
        cfg = AgentConfig()
        setattr(cfg, attribute, value)

        with pytest.raises(ValueError, match=environment_name):
            cfg.validate()

    @pytest.mark.parametrize("context_tokens", [4_096, 262_144])
    def test_local_context_window_accepts_documented_boundaries(self, context_tokens: int) -> None:
        cfg = AgentConfig(local_llm_context_tokens=context_tokens)

        assert cfg.validate() is True

    def test_zero_max_loop_turns_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = load_config()
        cfg.max_loop_turns = 0
        with pytest.raises(ValueError, match="DJENIS_MAX_LOOP_TURNS"):
            cfg.validate()

    def test_valid_config_validates(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.validate() is True

    def test_url_host_allowlist_accepts_hosts_not_urls(self, fake_env: None) -> None:
        cfg = load_config()
        cfg.allowed_url_hosts = ("http://internal.example/path",)

        with pytest.raises(ValueError, match="DJENIS_ALLOWED_URL_HOSTS"):
            cfg.validate()

    @pytest.mark.parametrize(
        "host",
        ["*", "example.com:443", "bad host", "-invalid.example", "invalid-.example"],
    )
    def test_url_host_allowlist_rejects_malformed_hosts(
        self,
        fake_env: None,
        host: str,
    ) -> None:
        cfg = load_config()
        cfg.allowed_url_hosts = (host,)

        with pytest.raises(ValueError, match="DJENIS_ALLOWED_URL_HOSTS"):
            cfg.validate()

    @pytest.mark.parametrize("host", ["", "   ", "127.0.0.1:9222", "::1", "*"])
    def test_browser_debugging_host_rejects_malformed_values(
        self,
        fake_env: None,
        host: str,
    ) -> None:
        cfg = load_config()
        cfg.browser_debugging_host = host

        with pytest.raises(ValueError, match="DJENIS_BROWSER_DEBUGGING_HOST"):
            cfg.validate()

    @pytest.mark.parametrize(
        ("attribute", "value", "environment_name"),
        [
            ("log_level", "verbose", "DJENIS_LOG_LEVEL"),
            ("profile", "maximum", "DJENIS_PROFILE"),
            ("screenshot_format", "BMP", "DJENIS_SCREENSHOT_FORMAT"),
            ("browser_debugging_port", 70_000, "DJENIS_BROWSER_DEBUGGING_PORT"),
            ("selenium_remote_url", "file:///tmp/driver", "SELENIUM_REMOTE_URL"),
            (
                "selenium_remote_url",
                "http://selenium:not-a-port/wd/hub",
                "SELENIUM_REMOTE_URL",
            ),
            ("web_host", "", "DJENIS_WEB_HOST"),
            (
                "allowed_applications",
                ("notepad.exe",),
                "DJENIS_ALLOWED_APPLICATIONS",
            ),
            (
                "allowed_shell_commands",
                ("python.exe",),
                "DJENIS_ALLOWED_SHELL_COMMANDS",
            ),
            (
                "web_allowed_origins",
                ("https://operator.example/path",),
                "DJENIS_WEB_ALLOWED_ORIGINS",
            ),
        ],
    )
    def test_structured_configuration_values_fail_closed(
        self,
        fake_env: None,
        attribute: str,
        value: object,
        environment_name: str,
    ) -> None:
        cfg = load_config()
        setattr(cfg, attribute, value)

        with pytest.raises(ValueError, match=environment_name):
            cfg.validate()

    def test_empty_audit_path_raises_when_audit_enabled(self, fake_env: None) -> None:
        cfg = load_config()
        cfg.enable_audit_log = True
        cfg.audit_log_path = ""
        with pytest.raises(ValueError, match="DJENIS_AUDIT_LOG_PATH"):
            cfg.validate()

    def test_completion_contract_limits_are_internally_consistent(self, fake_env: None) -> None:
        cfg = load_config()
        cfg.tool_argument_max_chars = 140
        cfg.completion_evidence_min_chars = 32

        with pytest.raises(ValueError, match="finish_task JSON envelope"):
            cfg.validate()

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    @pytest.mark.parametrize(
        ("attribute", "environment_name"),
        [
            ("screenshot_interval", "DJENIS_SCREENSHOT_INTERVAL"),
            ("api_retry_delay", "DJENIS_API_RETRY_DELAY"),
            ("web_socket_send_timeout", "DJENIS_WEB_SOCKET_SEND_TIMEOUT"),
            ("web_transcription_timeout", "DJENIS_WEB_TRANSCRIPTION_TIMEOUT"),
        ],
    )
    def test_non_finite_float_configuration_is_rejected(
        self,
        fake_env: None,
        attribute: str,
        environment_name: str,
        value: float,
    ) -> None:
        cfg = load_config()
        setattr(cfg, attribute, value)

        with pytest.raises(ValueError, match=environment_name):
            cfg.validate()

    @pytest.mark.parametrize(
        ("attribute", "value", "environment_name"),
        [
            ("max_loop_turns", 201, "DJENIS_MAX_LOOP_TURNS"),
            ("tool_argument_max_chars", 1_048_577, "DJENIS_TOOL_ARGUMENT_MAX_CHARS"),
            ("max_repeated_actions", 11, "DJENIS_MAX_REPEATED_ACTIONS"),
            (
                "completion_evidence_min_chars",
                4_097,
                "DJENIS_COMPLETION_EVIDENCE_MIN_CHARS",
            ),
        ],
    )
    def test_execution_contract_limits_have_safe_upper_bounds(
        self,
        fake_env: None,
        attribute: str,
        value: int,
        environment_name: str,
    ) -> None:
        cfg = load_config()
        setattr(cfg, attribute, value)

        with pytest.raises(ValueError, match=environment_name):
            cfg.validate()

    def test_zero_task_timeout_raises(self, fake_env: None) -> None:
        cfg = load_config()
        cfg.task_timeout = 0
        with pytest.raises(ValueError, match="DJENIS_TASK_TIMEOUT"):
            cfg.validate()

    def test_local_transcription_without_path_raises(self, fake_env: None) -> None:
        cfg = load_config()
        cfg.enable_local_transcription = True
        cfg.vosk_model_path = ""
        with pytest.raises(ValueError, match="VOSK_MODEL_PATH"):
            cfg.validate()

    @pytest.mark.parametrize(
        "attribute,value,environment_name",
        [
            ("transcription_sample_rate", 7_999, "DJENIS_TRANSCRIPTION_SAMPLE_RATE"),
            ("transcription_sample_rate", 48_001, "DJENIS_TRANSCRIPTION_SAMPLE_RATE"),
            ("transcription_max_duration_seconds", 0, "DJENIS_TRANSCRIPTION_MAX_DURATION_SECONDS"),
            (
                "transcription_max_duration_seconds",
                601,
                "DJENIS_TRANSCRIPTION_MAX_DURATION_SECONDS",
            ),
        ],
    )
    def test_transcription_resource_limits_are_validated(
        self, fake_env: None, attribute: str, value: int, environment_name: str
    ) -> None:
        cfg = load_config()
        setattr(cfg, attribute, value)
        with pytest.raises(ValueError, match=environment_name):
            cfg.validate()

    @pytest.mark.parametrize("sample_rate,duration", [(8_000, 1), (48_000, 600)])
    def test_transcription_resource_limit_endpoints_are_accepted(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch, sample_rate: int, duration: int
    ) -> None:
        monkeypatch.setenv("DJENIS_TRANSCRIPTION_SAMPLE_RATE", str(sample_rate))
        monkeypatch.setenv("DJENIS_TRANSCRIPTION_MAX_DURATION_SECONDS", str(duration))
        cfg = load_config()
        assert cfg.transcription_sample_rate == sample_rate
        assert cfg.transcription_max_duration_seconds == duration
        assert cfg.validate()

    def test_zero_browser_debugging_port_raises(self, fake_env: None) -> None:
        cfg = load_config()
        cfg.browser_debugging_port = 0
        with pytest.raises(ValueError, match="DEBUGGING_PORT"):
            cfg.validate()

    def test_web_mode_requires_long_operator_token(self, fake_env: None) -> None:
        cfg = load_config()
        cfg.web_auth_token = "too-short"
        with pytest.raises(ValueError, match="DJENIS_WEB_AUTH_TOKEN"):
            cfg.validate_web()

        cfg.web_auth_token = "valid-test-token-with-32-characters"
        assert cfg.validate_web() is True

    @pytest.mark.parametrize(
        ("attribute", "environment_name"),
        [
            ("web_max_sessions", "DJENIS_WEB_MAX_SESSIONS"),
            ("web_max_connections", "DJENIS_WEB_MAX_CONNECTIONS"),
            ("web_socket_send_timeout", "DJENIS_WEB_SOCKET_SEND_TIMEOUT"),
            ("web_stream_max_clients", "DJENIS_WEB_STREAM_MAX_CLIENTS"),
            (
                "web_transcription_max_concurrency",
                "DJENIS_WEB_TRANSCRIPTION_MAX_CONCURRENCY",
            ),
            ("web_transcription_timeout", "DJENIS_WEB_TRANSCRIPTION_TIMEOUT"),
            ("audit_log_max_bytes", "DJENIS_AUDIT_LOG_MAX_BYTES"),
            ("command_max_chars", "DJENIS_COMMAND_MAX_CHARS"),
            ("observation_max_chars", "DJENIS_OBSERVATION_MAX_CHARS"),
            ("prompt_history_max_chars", "DJENIS_PROMPT_HISTORY_MAX_CHARS"),
            ("ui_tree_max_chars", "DJENIS_UI_TREE_MAX_CHARS"),
            ("tool_argument_max_chars", "DJENIS_TOOL_ARGUMENT_MAX_CHARS"),
            ("max_repeated_actions", "DJENIS_MAX_REPEATED_ACTIONS"),
            (
                "completion_evidence_min_chars",
                "DJENIS_COMPLETION_EVIDENCE_MIN_CHARS",
            ),
            ("shell_output_max_bytes", "DJENIS_SHELL_OUTPUT_MAX_BYTES"),
        ],
    )
    def test_resource_limits_must_be_positive(
        self, fake_env: None, attribute: str, environment_name: str
    ) -> None:
        cfg = load_config()
        setattr(cfg, attribute, 0)

        with pytest.raises(ValueError, match=environment_name):
            cfg.validate()


# ---------------------------------------------------------------------------
# Safe view — API key redaction
# ---------------------------------------------------------------------------


class TestSafeView:
    def test_safe_view_exposes_local_runtime_but_redacts_operator_token(self) -> None:
        cfg = AgentConfig(web_auth_token="operator-secret-token")

        view = cfg.safe_view()

        assert view["local_llm_backend"] == "ollama"
        assert view["local_llm_model"] == "qwen3-vl:8b"
        assert view["web_auth_token"] == "***redacted***"
        assert "operator-secret-token" not in str(view)
        assert not any("api_key" in key.casefold() for key in view)


# ---------------------------------------------------------------------------
# Profile application
# ---------------------------------------------------------------------------


class TestProfileApplication:
    def test_performance_profile_reduces_timeout(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DJENIS_PROFILE", "performance")
        cfg = load_config()
        assert cfg.action_timeout <= 20

    def test_quality_profile_sets_png_format(
        self, fake_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DJENIS_PROFILE", "quality")
        cfg = load_config()
        assert cfg.screenshot_format == "PNG"


# ---------------------------------------------------------------------------
# .env file loading
# ---------------------------------------------------------------------------


class TestDotEnvLoading:
    def test_load_from_custom_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DJENIS_LOCAL_LLM_MODEL", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("DJENIS_LOCAL_LLM_MODEL=local-model-from-file\n")

        cfg = load_config(dotenv_path=env_file)

        assert cfg.local_llm_model == "local-model-from-file"
        assert cfg.config_source == str(env_file)
