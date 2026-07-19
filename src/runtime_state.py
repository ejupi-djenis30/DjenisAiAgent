"""Shared runtime state for the web server and agent loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Literal

AgentState = Literal["idle", "running", "finished", "error", "cancelling"]


@dataclass
class WebRuntimeState:
    """Own the mutable runtime state used by FastAPI web mode."""

    # The web API admits one task at a time; a small finite queue also leaves room for
    # deterministic cancellation/drain handling and internal tests without unbounded growth.
    command_queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=8))
    status_queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    task_cancel_event: Event = field(default_factory=Event)
    command_queue_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    resource_lock: Lock = field(default_factory=Lock)
    active_streams: int = 0
    active_transcriptions: int = 0
    _agent_state: AgentState = "idle"

    @property
    def agent_state(self) -> AgentState:
        return self._agent_state

    @agent_state.setter
    def agent_state(self, state: AgentState) -> None:
        self._agent_state = state

    async def get_agent_state(self) -> AgentState:
        async with self.state_lock:
            return self._agent_state

    async def set_agent_state(self, state: AgentState) -> AgentState:
        async with self.state_lock:
            self._agent_state = state
            return self._agent_state

    async def reserve_command_slot(self) -> bool:
        """Atomically switch to running if the agent is currently idle-like."""

        async with self.state_lock:
            if self._agent_state != "idle":
                return False
            self._agent_state = "running"
            return True

    def reserve_stream_slot(self, limit: int) -> bool:
        """Reserve one bounded desktop-stream worker slot."""

        with self.resource_lock:
            if self.active_streams >= limit:
                return False
            self.active_streams += 1
            return True

    def release_stream_slot(self) -> None:
        with self.resource_lock:
            self.active_streams = max(0, self.active_streams - 1)

    def reserve_transcription_slot(self, limit: int) -> bool:
        """Reserve one bounded CPU-heavy transcription worker slot."""

        with self.resource_lock:
            if self.active_transcriptions >= limit:
                return False
            self.active_transcriptions += 1
            return True

    def release_transcription_slot(self) -> None:
        with self.resource_lock:
            self.active_transcriptions = max(0, self.active_transcriptions - 1)


def create_runtime_state() -> WebRuntimeState:
    """Create a fresh runtime state object.

    This helper makes tests deterministic by allowing them to replace the
    process-wide runtime context with a fresh instance.
    """

    return WebRuntimeState()
