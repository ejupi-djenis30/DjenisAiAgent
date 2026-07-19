"""Operator-controlled permission gates for agent tools."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from src.config import config


class ToolPermissionError(PermissionError):
    """Raised when a tool is outside the operator's configured capability boundary."""


def require_tier(required_tier: str, *, dangerous: bool = False) -> None:
    if not config.permits(required_tier):
        raise ToolPermissionError(
            f"Tool requires permission tier '{required_tier}', current tier is "
            f"'{config.permission_tier}'."
        )
    if dangerous and not config.confirm_dangerous_actions:
        raise ToolPermissionError(
            "Dangerous tools are disabled. The operator must explicitly set "
            "DJENIS_CONFIRM_DANGEROUS_ACTIONS=true at startup."
        )


def resolve_allowed_path(path_value: str) -> Path:
    """Resolve a path and ensure it remains under an operator-approved root."""

    candidate = Path(path_value).expanduser().resolve()
    allowed_roots = [Path(root).expanduser().resolve() for root in config.allowed_paths]
    if not any(candidate == root or candidate.is_relative_to(root) for root in allowed_roots):
        roots = ", ".join(str(root) for root in allowed_roots) or "<none>"
        raise ToolPermissionError(f"Path '{candidate}' is outside allowed roots: {roots}")
    return candidate


def require_allowed_application(app_name: str) -> None:
    """Require an exact executable/name match from the configured application allowlist."""

    requested = app_name.strip()
    requested_name = Path(requested).name.casefold()
    permitted = False
    for entry in config.allowed_applications:
        configured = entry.strip()
        if Path(configured).name == configured:
            permitted = requested_name == configured.casefold()
        else:
            permitted = Path(requested).resolve() == Path(configured).resolve()
        if permitted:
            break
    if not permitted:
        raise ToolPermissionError(
            "Application is not allowlisted. Configure DJENIS_ALLOWED_APPLICATIONS explicitly."
        )


def require_allowed_shell_command(command: str) -> None:
    """Allow a single PowerShell command whose executable/cmdlet is allowlisted."""

    stripped = command.strip()
    if any(marker in stripped for marker in (";", "|", "&", "`", "$(", "\n", "\r")):
        raise ToolPermissionError("Shell pipelines, chaining, and command substitution are denied.")

    match = re.match(r"(?:\"([^\"]+)\"|'([^']+)'|([^\s]+))", stripped)
    executable = next((group for group in match.groups() if group), "") if match else ""
    requested_name = Path(executable).name.casefold()
    permitted = False
    for entry in config.allowed_shell_commands:
        configured = entry.strip()
        if Path(configured).name == configured:
            permitted = requested_name == configured.casefold()
        else:
            permitted = Path(executable).resolve() == Path(configured).resolve()
        if permitted:
            break
    if not executable or not permitted:
        raise ToolPermissionError(
            "Shell command is not allowlisted. Configure DJENIS_ALLOWED_SHELL_COMMANDS "
            "with exact executable or cmdlet names."
        )


def require_safe_url(url: str) -> None:
    """Restrict browser launches to ordinary HTTP(S) URLs."""

    require_tier("interact")
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ToolPermissionError("Only absolute http:// or https:// URLs are allowed.")
