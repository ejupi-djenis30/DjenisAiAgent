"""Tests for the operator-controlled tool boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.action.permissions import (
    ToolPermissionError,
    require_allowed_application,
    require_allowed_shell_command,
    require_safe_url,
    require_tier,
    resolve_allowed_path,
    split_command_arguments,
)
from src.config import config


def test_tier_and_dangerous_confirmation_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "permission_tier", "interact")
    monkeypatch.setattr(config, "confirm_dangerous_actions", True)
    with pytest.raises(ToolPermissionError, match="system"):
        require_tier("system", dangerous=True)

    monkeypatch.setattr(config, "permission_tier", "system")
    monkeypatch.setattr(config, "confirm_dangerous_actions", False)
    with pytest.raises(ToolPermissionError, match="explicitly"):
        require_tier("system", dangerous=True)

    monkeypatch.setattr(config, "confirm_dangerous_actions", True)
    require_tier("system", dangerous=True)


def test_allowed_path_resists_sibling_prefixes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "approved"
    sibling = tmp_path / "approved-copy"
    allowed.mkdir()
    sibling.mkdir()
    monkeypatch.setattr(config, "allowed_paths", (str(allowed),))

    assert resolve_allowed_path(str(allowed / "file.txt")) == allowed / "file.txt"
    with pytest.raises(ToolPermissionError, match="outside allowed roots"):
        resolve_allowed_path(str(sibling / "file.txt"))


def test_application_allowlist_distinguishes_exact_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = tmp_path / "trusted" / "tool.exe"
    untrusted = tmp_path / "other" / "tool.exe"
    monkeypatch.setattr(config, "allowed_applications", (str(trusted),))

    require_allowed_application(str(trusted))
    with pytest.raises(ToolPermissionError, match="not allowlisted"):
        require_allowed_application(str(untrusted))

    monkeypatch.setattr(config, "allowed_applications", ("notepad.exe",))
    require_allowed_application("notepad.exe")
    with pytest.raises(ToolPermissionError, match="not allowlisted"):
        require_allowed_application(str(tmp_path / "untrusted" / "notepad.exe"))


def test_shell_allowlist_rejects_unlisted_and_compound_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "allowed_shell_commands", ("Get-ChildItem",))

    require_allowed_shell_command("Get-ChildItem -Force")
    with pytest.raises(ToolPermissionError, match="not allowlisted"):
        require_allowed_shell_command("Get-Process")
    with pytest.raises(ToolPermissionError, match="chaining"):
        require_allowed_shell_command("Get-ChildItem; Get-Process")
    with pytest.raises(ToolPermissionError, match="chaining"):
        require_allowed_shell_command("Get-ChildItem | Out-File result.txt")


def test_native_command_parser_preserves_quoted_arguments_without_shell_evaluation() -> None:
    parsed = split_command_arguments('"C:\\Program Files\\tool.exe" "literal value" --safe')

    assert parsed == ["C:\\Program Files\\tool.exe", "literal value", "--safe"]


def test_url_policy_accepts_http_but_rejects_credentials_and_active_schemes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "permission_tier", "interact")

    require_safe_url("https://example.com/path")
    with pytest.raises(ToolPermissionError):
        require_safe_url("file:///etc/passwd")
    with pytest.raises(ToolPermissionError):
        require_safe_url("https://user:secret@example.com")
