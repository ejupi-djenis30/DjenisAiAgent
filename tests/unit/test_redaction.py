"""Tests for structured log and audit redaction."""

from __future__ import annotations

import json

from src.audit import AuditLogger
from src.redaction import redact, safe_preview


def test_redact_hides_sensitive_keys_and_known_token_shapes() -> None:
    # Assemble the sample at runtime so repository secret scanners do not mistake it
    # for a live credential while the redactor still receives a realistic shape.
    fake_google_key = "AI" + "za" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    value = {
        "authorization": "Bearer this-is-a-secret-bearer-value",
        "nested": {"api_key": fake_google_key},
        "message": f"key={fake_google_key}",
        "url": "https://example.test/callback?token=private-query-value&mode=read",
    }

    result = redact(value)

    assert result["authorization"] == "***redacted***"
    assert result["nested"]["api_key"] == "***redacted***"
    assert fake_google_key not in result["message"]
    assert "private-query-value" not in result["url"]


def test_safe_preview_bounds_large_values() -> None:
    preview = safe_preview("x" * 2_000)

    assert len(preview) < 600
    assert "truncated sha256" in preview


def test_audit_logger_writes_only_redacted_payload(tmp_path) -> None:
    target = tmp_path / "audit.jsonl"
    audit = AuditLogger(enabled=True, file_path=str(target))

    audit.record_event("request", token="private-value", command="inspect")

    event = json.loads(target.read_text(encoding="utf-8"))
    assert event["event_type"] == "request"
    assert event["payload"]["token"] == "***redacted***"
