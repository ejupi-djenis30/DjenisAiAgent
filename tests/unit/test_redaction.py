"""Tests for structured log and audit redaction."""

from __future__ import annotations

import io
import json
import logging

from src.audit import AuditLogger
from src.redaction import RedactingFormatter, bounded_text, redact, safe_preview


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


def test_audit_logger_rotates_before_the_configured_size_limit(tmp_path) -> None:
    target = tmp_path / "audit.jsonl"
    audit = AuditLogger(enabled=True, file_path=str(target), max_bytes=180)

    audit.record_event("first", value="a" * 100)
    audit.record_event("second", value="b" * 100)

    backup = tmp_path / "audit.jsonl.1"
    assert backup.is_file()
    assert '"event_type": "first"' in backup.read_text(encoding="utf-8")
    assert '"event_type": "second"' in target.read_text(encoding="utf-8")


def test_redaction_covers_url_credentials_jwts_and_common_token_names() -> None:
    jwt = "eyJheader12345.eyJpayload12345.signature12345"
    url_with_credentials = "https://" + "operator" + ":" + "private-pass" + "@example.test"
    value = (
        f"{url_with_credentials} "
        "access_token=access-value refresh-token=refresh-value "
        f"authorization={jwt}"
    )

    preview = safe_preview(value)

    assert "private-pass" not in preview
    assert "access-value" not in preview
    assert "refresh-value" not in preview
    assert jwt not in preview


def test_redacting_formatter_filters_full_rendered_log_records() -> None:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(RedactingFormatter("%(levelname)s %(message)s"))
    logger = logging.getLogger("tests.redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info("request failed: access_token=%s", "private-value")

    rendered = output.getvalue()
    assert "private-value" not in rendered
    assert "***redacted***" in rendered


def test_bounded_text_never_exceeds_requested_context_limit() -> None:
    bounded = bounded_text("x" * 1_000, 120)

    assert len(bounded) == 120
    assert "truncated" in bounded
    assert len(bounded_text("short", 120)) == 5
