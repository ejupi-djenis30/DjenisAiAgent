"""Tests for the operator-controlled tool boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.action import permissions as permissions_module
from src.action.permissions import (
    ToolPermissionError,
    require_allowed_application,
    require_allowed_shell_command,
    require_safe_url,
    require_tier,
    resolve_allowed_path,
    split_command_arguments,
    validate_url_network_policy,
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
    trusted.parent.mkdir()
    untrusted.parent.mkdir()
    trusted.touch()
    untrusted.touch()
    monkeypatch.setattr(config, "allowed_applications", (str(trusted),))

    assert require_allowed_application(str(trusted)) == trusted
    with pytest.raises(ToolPermissionError, match="not allowlisted"):
        require_allowed_application(str(untrusted))

    assert require_allowed_application("tool.exe") == trusted
    with pytest.raises(ToolPermissionError, match="not allowlisted"):
        require_allowed_application(str(tmp_path / "untrusted" / "tool.exe"))


def test_shell_allowlist_rejects_unlisted_and_compound_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "Get-ChildItem.exe"
    executable.touch()
    monkeypatch.setattr(config, "allowed_shell_commands", (str(executable),))

    resolved, arguments = require_allowed_shell_command("Get-ChildItem.exe -Force")
    assert resolved == executable
    assert arguments == ["-Force"]
    with pytest.raises(ToolPermissionError, match="not allowlisted"):
        require_allowed_shell_command("Get-Process")
    with pytest.raises(ToolPermissionError, match="chaining"):
        require_allowed_shell_command("Get-ChildItem.exe; Get-Process")
    with pytest.raises(ToolPermissionError, match="chaining"):
        require_allowed_shell_command("Get-ChildItem.exe | Out-File result.txt")


def test_native_command_parser_preserves_quoted_arguments_without_shell_evaluation() -> None:
    parsed = split_command_arguments('"C:\\Program Files\\tool.exe" "literal value" --safe')

    assert parsed == ["C:\\Program Files\\tool.exe", "literal value", "--safe"]


def test_url_policy_accepts_only_public_or_explicitly_allowed_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "permission_tier", "interact")
    monkeypatch.setattr(config, "allowed_url_hosts", ())
    monkeypatch.setattr(
        permissions_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )

    require_safe_url("https://example.com/path")
    with pytest.raises(ToolPermissionError):
        require_safe_url("file:///etc/passwd")
    with pytest.raises(ToolPermissionError):
        require_safe_url("https://user:secret@example.com")

    monkeypatch.setattr(
        permissions_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 80))],
    )
    with pytest.raises(ToolPermissionError, match="non-public"):
        require_safe_url("http://service.example")

    monkeypatch.setattr(config, "allowed_url_hosts", ("internal.example",))
    monkeypatch.setattr(
        permissions_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DNS should be bypassed")),
    )
    require_safe_url("https://internal.example/dashboard")
    with pytest.raises(ToolPermissionError, match="invalid port"):
        require_safe_url("https://internal.example:not-a-port")


def test_url_policy_fails_closed_for_metadata_mixed_dns_and_resolution_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "permission_tier", "interact")
    monkeypatch.setattr(config, "allowed_url_hosts", ())

    with pytest.raises(ToolPermissionError, match="non-public"):
        require_safe_url("http://169.254.169.254/latest/meta-data")

    monkeypatch.setattr(
        permissions_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("10.0.0.8", 443)),
        ],
    )
    with pytest.raises(ToolPermissionError, match="non-public"):
        require_safe_url("https://rebind.example")

    monkeypatch.setattr(
        permissions_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    with pytest.raises(ToolPermissionError, match="could not be resolved safely"):
        require_safe_url("https://unresolved.example")

    with pytest.raises(ToolPermissionError, match="invalid port"):
        require_safe_url("https://example.com:not-a-port")


def test_network_policy_can_validate_observation_without_interact_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "permission_tier", "observe")
    monkeypatch.setattr(config, "allowed_url_hosts", ("example.com",))

    validate_url_network_policy("https://example.com/safe")

    with pytest.raises(ToolPermissionError, match="permission tier"):
        require_safe_url("https://example.com/safe")
