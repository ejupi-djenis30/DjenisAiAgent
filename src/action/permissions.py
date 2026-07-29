"""Operator-controlled permission gates for agent tools."""

from __future__ import annotations

import ipaddress
import os
import shlex
import socket
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


def _resolve_allowlisted_executable(
    requested_value: str,
    configured_values: tuple[str, ...],
    *,
    boundary_name: str,
) -> Path:
    requested = requested_value.strip()
    requested_path = Path(requested).expanduser()
    requested_is_name = requested_path.name == requested
    matches: list[Path] = []

    for entry in configured_values:
        configured_path = Path(entry).expanduser()
        if not configured_path.is_absolute():
            continue
        resolved = configured_path.resolve()
        if requested_is_name:
            matched = os.path.normcase(resolved.name) == os.path.normcase(requested)
        else:
            matched = os.path.normcase(str(requested_path.resolve())) == os.path.normcase(
                str(resolved)
            )
        if matched and resolved not in matches:
            matches.append(resolved)

    if len(matches) != 1:
        raise ToolPermissionError(
            f"{boundary_name} is not allowlisted by one unique absolute path. "
            f"Configure the corresponding DJENIS allowlist explicitly."
        )
    if not matches[0].is_file():
        raise ToolPermissionError(f"The allowlisted {boundary_name.casefold()} does not exist.")
    return matches[0]


def require_allowed_application(app_name: str) -> Path:
    """Resolve an application name/path to one exact operator-configured executable."""

    return _resolve_allowlisted_executable(
        app_name,
        config.allowed_applications,
        boundary_name="Application",
    )


def split_command_arguments(command: str) -> list[str]:
    """Parse one native command line without invoking a shell interpreter."""

    try:
        parts = shlex.split(command.strip(), posix=False)
    except ValueError as exc:
        raise ToolPermissionError(f"Invalid command quoting: {exc}") from exc

    normalized: list[str] = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in {"'", '"'}:
            part = part[1:-1]
        if not part:
            raise ToolPermissionError("Empty command arguments are denied.")
        normalized.append(part)
    return normalized


def require_allowed_shell_command(command: str) -> tuple[Path, list[str]]:
    """Resolve one native invocation to an exact allowlisted executable and arguments."""

    stripped = command.strip()
    if any(marker in stripped for marker in (";", "|", "&", "`", "$(", "\n", "\r")):
        raise ToolPermissionError("Shell pipelines, chaining, and command substitution are denied.")

    parts = split_command_arguments(stripped)
    executable = parts[0] if parts else ""
    if not executable:
        raise ToolPermissionError(
            "Shell command is not allowlisted. Configure DJENIS_ALLOWED_SHELL_COMMANDS."
        )
    resolved = _resolve_allowlisted_executable(
        executable,
        config.allowed_shell_commands,
        boundary_name="Shell executable",
    )
    return resolved, parts[1:]


def _host_resolves_to_public_network(hostname: str, port: int) -> bool:
    """Fail closed unless every resolved address is globally routable."""

    try:
        literal = ipaddress.ip_address(hostname)
        addresses = {literal}
    except ValueError:
        try:
            results = socket.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise ToolPermissionError(
                f"URL host '{hostname}' could not be resolved safely."
            ) from exc
        addresses = set()
        for result in results:
            try:
                addresses.add(ipaddress.ip_address(result[4][0]))
            except (ValueError, IndexError):
                continue

    if not addresses:
        raise ToolPermissionError(f"URL host '{hostname}' resolved to no usable address.")
    return all(address.is_global for address in addresses)


def validate_url_network_policy(url: str) -> None:
    """Validate an HTTP(S) destination without requiring an action capability."""

    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ToolPermissionError("Only absolute http:// or https:// URLs are allowed.")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ToolPermissionError("URL contains an invalid port.") from exc
    hostname = parsed.hostname.rstrip(".").casefold()
    allowed_hosts = {host.rstrip(".").casefold() for host in config.allowed_url_hosts}
    if hostname in allowed_hosts:
        return

    if not _host_resolves_to_public_network(hostname, port):
        raise ToolPermissionError(
            f"URL host '{hostname}' resolves to a private, local, reserved, or otherwise "
            "non-public address. Add the exact host to DJENIS_ALLOWED_URL_HOSTS only when "
            "that network access is intentional."
        )


def require_safe_url(url: str) -> None:
    """Require browser interaction permission and a policy-compliant HTTP(S) URL."""

    require_tier("interact")
    validate_url_network_policy(url)
