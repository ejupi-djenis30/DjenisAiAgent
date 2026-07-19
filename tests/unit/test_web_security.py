"""Focused tests for bounded web sessions and resource state."""

from __future__ import annotations

import asyncio

import pytest

from src.config import config
from src.runtime_state import create_runtime_state
from src.web_security import WebSecurity


def test_session_store_evicts_oldest_entry_at_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "web_max_sessions", 2)
    monkeypatch.setattr(config, "web_session_ttl", 60)
    security = WebSecurity()

    first = security.create_session()
    second = security.create_session()
    third = security.create_session()

    assert security.session_is_valid(first) is False
    assert security.session_is_valid(second) is True
    assert security.session_is_valid(third) is True


@pytest.mark.asyncio
async def test_command_reservation_rejects_running_and_cancelling_states() -> None:
    runtime = create_runtime_state()

    assert await runtime.reserve_command_slot() is True
    assert await runtime.reserve_command_slot() is False
    await runtime.set_agent_state("cancelling")
    assert await runtime.reserve_command_slot() is False
    await runtime.set_agent_state("idle")
    assert await runtime.reserve_command_slot() is True


def test_stream_and_transcription_slots_are_bounded() -> None:
    runtime = create_runtime_state()

    assert runtime.reserve_stream_slot(1) is True
    assert runtime.reserve_stream_slot(1) is False
    runtime.release_stream_slot()
    assert runtime.reserve_stream_slot(1) is True

    assert runtime.reserve_transcription_slot(1) is True
    assert runtime.reserve_transcription_slot(1) is False
    runtime.release_transcription_slot()
    assert runtime.reserve_transcription_slot(1) is True

    # Keep static analysis honest about the queue type used by the async runtime.
    assert isinstance(runtime.command_queue, asyncio.Queue)
