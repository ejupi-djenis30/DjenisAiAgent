"""Unit tests for src/config.py."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from src.config import AgentConfig, load_config


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestAgentConfigDefaults:
    def test_default_gemini_model(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.gemini_model_name == "gemini-1.5-pro-latest"

    def test_default_max_loop_turns(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.max_loop_turns == 50

    def test_default_action_timeout(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.action_timeout == 45

    def test_default_api_timeout(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.api_timeout == 120

    def test_default_log_level(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.log_level == "INFO"

    def test_default_stream_max_fps(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.stream_max_fps == 30

    def test_default_local_transcription_disabled(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.enable_local_transcription is False


# ---------------------------------------------------------------------------
# Environment overrides
# ---------------------------------------------------------------------------


class TestAgentConfigEnvOverrides:
    def test_max_loop_turns_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        monkeypatch.setenv("DJENIS_MAX_LOOP_TURNS", "25")
        cfg = load_config()
        assert cfg.max_loop_turns == 25

    def test_gemini_model_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        monkeypatch.setenv("DJENIS_GEMINI_MODEL", "gemini-2.0-flash")
        cfg = load_config()
        assert cfg.gemini_model_name == "gemini-2.0-flash"

    def test_boolean_env_truthy_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        for truthy in ("1", "true", "True", "yes", "on"):
            monkeypatch.setenv("DJENIS_VERBOSE_LOGGING", truthy)
            cfg = load_config()
            assert cfg.enable_verbose_logging is True, f"Failed for value: {truthy!r}"

    def test_boolean_env_falsy_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        for falsy in ("0", "false", "False", "no", "off"):
            monkeypatch.setenv("DJENIS_VERBOSE_LOGGING", falsy)
            cfg = load_config()
            assert cfg.enable_verbose_logging is False, f"Failed for value: {falsy!r}"

    def test_invalid_int_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        monkeypatch.setenv("DJENIS_MAX_LOOP_TURNS", "not_an_int")
        with pytest.raises(ValueError, match="must be an integer"):
            load_config()

    def test_invalid_bool_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        monkeypatch.setenv("DJENIS_VERBOSE_LOGGING", "maybe")
        with pytest.raises(ValueError):
            load_config()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestAgentConfigValidation:
    def test_missing_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        cfg = AgentConfig()
        cfg.gemini_api_key = ""
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            cfg.validate()

    def test_placeholder_api_key_raises(self) -> None:
        cfg = AgentConfig()
        cfg.gemini_api_key = "YOUR_API_KEY_HERE"
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            cfg.validate()

    def test_zero_max_loop_turns_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        cfg = load_config()
        cfg.max_loop_turns = 0
        with pytest.raises(ValueError, match="DJENIS_MAX_LOOP_TURNS"):
            cfg.validate()

    def test_valid_config_validates(self, fake_env: None) -> None:
        cfg = load_config()
        assert cfg.validate() is True

    def test_local_transcription_without_path_raises(self, fake_env: None) -> None:
        cfg = load_config()
        cfg.enable_local_transcription = True
        cfg.vosk_model_path = ""
        with pytest.raises(ValueError, match="VOSK_MODEL_PATH"):
            cfg.validate()


# ---------------------------------------------------------------------------
# Safe view — API key redaction
# ---------------------------------------------------------------------------


class TestSafeView:
    def test_api_key_is_redacted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key-12345")
        cfg = load_config()
        view = cfg.safe_view()
        assert view["gemini_api_key"] == "***redacted***"
        assert "super-secret-key-12345" not in str(view)


# ---------------------------------------------------------------------------
# Profile application
# ---------------------------------------------------------------------------


class TestProfileApplication:
    def test_performance_profile_reduces_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        monkeypatch.setenv("DJENIS_PROFILE", "performance")
        cfg = load_config()
        # performance profile caps action_timeout at 20
        assert cfg.action_timeout <= 20

    def test_quality_profile_sets_png_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        monkeypatch.setenv("DJENIS_PROFILE", "quality")
        cfg = load_config()
        assert cfg.screenshot_format == "PNG"


# ---------------------------------------------------------------------------
# .env file loading
# ---------------------------------------------------------------------------


class TestDotEnvLoading:
    def test_load_from_custom_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("GEMINI_API_KEY=from_file\n")
        cfg = load_config(dotenv_path=env_file)
        assert cfg.gemini_api_key == "from_file"
        assert cfg.config_source == str(env_file)
