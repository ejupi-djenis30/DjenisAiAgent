"""Small, dependency-free redaction helpers for logs and audit events."""

from __future__ import annotations

import hashlib
import logging
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
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox(?:a|b|p|r|s)-[A-Za-z0-9-]{12,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)
_INLINE_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|authorization|cookie|credential|password|passwd|private[_-]?key|"
    r"client[_-]?secret|access[_-]?token|refresh[_-]?token|session|token)"
    r"\s*[:=]\s*)[^\s&,;]+"
)
_URL_CREDENTIALS = re.compile(r"(?i)(https?://[^\s:/@]+:)[^\s@]+(@)")
_MAX_LOG_STRING = 512


def _redact_string(value: str) -> str:
    redacted = redact_text(value)

    if len(redacted) <= _MAX_LOG_STRING:
        return redacted

    digest = hashlib.sha256(redacted.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{redacted[:_MAX_LOG_STRING]}… [truncated sha256:{digest}]"


def redact_text(value: str) -> str:
    """Redact common credential shapes without truncating the surrounding log record."""

    redacted = _URL_CREDENTIALS.sub(r"\1***redacted***\2", value)
    redacted = _INLINE_SECRET.sub(r"\1***redacted***", redacted)
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        redacted = pattern.sub("***redacted***", redacted)
    return redacted


class RedactingFormatter(logging.Formatter):
    """Apply the same secret filters to every rendered application log record."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


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


def bounded_text(value: Any, max_chars: int) -> str:
    """Return text within a hard context bound and include a non-reversible fingerprint."""

    text = str(value)
    if len(text) <= max_chars:
        return text
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    marker = f"\n… [truncated; original chars={len(text)} sha256:{digest}]"
    if len(marker) >= max_chars:
        return marker[:max_chars]
    keep = max(0, max_chars - len(marker))
    return text[:keep] + marker
