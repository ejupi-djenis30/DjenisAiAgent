"""Small, dependency-free redaction helpers for logs and audit events."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|credential|password|secret|session|token)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
)
_INLINE_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|authorization|cookie|credential|password|secret|session|token)"
    r"\s*[:=]\s*)[^\s&,;]+"
)
_MAX_LOG_STRING = 512


def _redact_string(value: str) -> str:
    redacted = _INLINE_SECRET.sub(r"\1***redacted***", value)
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        redacted = pattern.sub("***redacted***", redacted)

    if len(redacted) <= _MAX_LOG_STRING:
        return redacted

    digest = hashlib.sha256(redacted.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{redacted[:_MAX_LOG_STRING]}… [truncated sha256:{digest}]"


def redact(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact likely secrets and cap user-controlled log payloads."""

    if key and _SENSITIVE_KEY.search(key):
        return "***redacted***"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Mapping):
        return {
            str(inner_key): redact(inner, key=str(inner_key)) for inner_key, inner in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [redact(item) for item in value]
    if isinstance(value, bytes | bytearray):
        return f"<binary payload: {len(value)} bytes>"
    return _redact_string(str(value))


def safe_preview(value: Any) -> str:
    """Return a redacted one-line representation suitable for application logs."""

    return str(redact(value)).replace("\r", " ").replace("\n", " ")
