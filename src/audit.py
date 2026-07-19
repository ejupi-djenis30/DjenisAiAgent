"""Lightweight JSONL audit logging for task and tool execution."""

from __future__ import annotations

import json
import logging
import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from src.config import config
from src.redaction import redact

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(inner) for key, inner in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    return str(value)


class AuditLogger:
    """Append structured audit events to a JSONL file."""

    def __init__(self, *, enabled: bool, file_path: str, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.enabled = enabled
        self.file_path = Path(file_path)
        self.max_bytes = max_bytes
        self._lock = Lock()

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        if not self.file_path.exists():
            return
        if self.file_path.stat().st_size + incoming_bytes <= self.max_bytes:
            return

        backup = self.file_path.with_suffix(self.file_path.suffix + ".1")
        backup.unlink(missing_ok=True)
        self.file_path.replace(backup)

    def record_event(self, event_type: str, **payload: Any) -> None:
        if not self.enabled:
            return

        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "payload": _json_safe(redact(payload)),
        }

        serialized = json.dumps(event, ensure_ascii=False) + "\n"
        try:
            with self._lock:
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate_if_needed(len(serialized.encode("utf-8")))
                with self.file_path.open("a", encoding="utf-8") as handle:
                    handle.write(serialized)
                with suppress(OSError):  # pragma: no cover - filesystem-specific permissions
                    os.chmod(self.file_path, 0o600)
        except OSError as exc:
            logger.error(
                "Failed to write audit event '%s' to %s: %s", event_type, self.file_path, exc
            )


audit_logger = AuditLogger(
    enabled=config.enable_audit_log,
    file_path=config.audit_log_path,
    max_bytes=config.audit_log_max_bytes,
)
