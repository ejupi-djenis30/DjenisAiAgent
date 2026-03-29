"""
Shared pytest fixtures and configuration.

This conftest is the root conftest for all test suites.
Platform-specific fixtures (pywinauto, pyautogui) are skipped gracefully
on non-Windows platforms so that unit tests can run in CI (Linux).
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

IS_WINDOWS = sys.platform == "win32"


def pytest_configure(config: pytest.Config) -> None:
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
def mock_gemini_client() -> Generator[MagicMock, None, None]:
    """Return a mock google.genai Client context manager instance."""
    with patch("google.genai.client.Client") as mock_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_cls.return_value = mock_client
        yield mock_client


@pytest.fixture()
def fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set minimum required environment variables for config loading."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key-fake")
    monkeypatch.delenv("DJENIS_GEMINI_MODEL", raising=False)
    monkeypatch.delenv("DJENIS_MAX_LOOP_TURNS", raising=False)
