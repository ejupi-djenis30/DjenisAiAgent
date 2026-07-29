"""
Shared pytest fixtures and configuration.

This conftest is the root conftest for all test suites.
Platform-specific fixtures (pywinauto, pyautogui) are skipped gracefully
on non-Windows platforms so that unit tests can run in CI (Linux).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

IS_WINDOWS = sys.platform == "win32"


def _disable_pytest_current_symlinks_on_windows() -> None:
    """Avoid best-effort temp aliases that locked-down Windows cannot traverse."""
    if not IS_WINDOWS:
        return

    import _pytest.pathlib as pytest_pathlib

    def skip_current_symlink(
        _root: Path,
        _target: str | Path,
        _link_to: str | Path,
    ) -> None:
        return

    force_symlink: Callable[[Path, str | Path, str | Path], None] = skip_current_symlink
    pytest_pathlib._force_symlink = force_symlink


def pytest_configure(config: pytest.Config) -> None:
    _disable_pytest_current_symlinks_on_windows()
    config.addinivalue_line("markers", "windows_only: test requires Windows OS")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip Windows-only tests when running on non-Windows platforms."""
    if not IS_WINDOWS:
        skip_mark = pytest.mark.skip(reason="Requires Windows OS")
        for item in items:
            if item.get_closest_marker("windows_only"):
                item.add_marker(skip_mark)


# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set deterministic local-only defaults for configuration tests."""
    monkeypatch.setattr("src.config.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("DJENIS_LOCAL_LLM_BACKEND", "ollama")
    monkeypatch.setenv("DJENIS_LOCAL_LLM_ENDPOINT", "http://127.0.0.1:11434")
    monkeypatch.setenv("DJENIS_LOCAL_LLM_MODEL", "qwen3-vl:8b")
    monkeypatch.delenv("DJENIS_LOCAL_LLM_EXPECTED_DIGEST", raising=False)
    monkeypatch.delenv("DJENIS_LOCAL_LLM_CONTEXT_TOKENS", raising=False)
    monkeypatch.delenv("DJENIS_MAX_LOOP_TURNS", raising=False)
    monkeypatch.delenv("DJENIS_ACTION_TIMEOUT", raising=False)
    monkeypatch.delenv("DJENIS_PROFILE", raising=False)
    monkeypatch.delenv("DJENIS_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("SELENIUM_REMOTE_URL", raising=False)
    monkeypatch.delenv("DJENIS_BROWSER_DEBUGGING_HOST", raising=False)
    monkeypatch.delenv("DJENIS_BROWSER_DEBUGGING_PORT", raising=False)
