"""Shared runtime state for the web server and agent loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from threading import Event
from typing import Literal

AgentState = Literal["idle", "running", "finished", "error", "cancelling"]


@dataclass
class WebRuntimeState:
    """Own the mutable runtime state used by FastAPI web mode."""

    command_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    status_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    task_cancel_event: Event = field(default_factory=Event)
    command_queue_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
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
            if self._agent_state == "running":
                return False
            self._agent_state = "running"
            return True


def create_runtime_state() -> WebRuntimeState:
    """Create a fresh runtime state object.

    This helper makes tests deterministic by allowing them to replace the
    process-wide runtime context with a fresh instance.
    """

    return WebRuntimeState()
