"""Lightweight tests for Enhanced AI Agent components."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Add src to path for direct script execution
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.actions import action_registry
from src.core.agent import EnhancedAIAgent
from src.core.gemini_client import EnhancedGeminiClient
from src.utils.logger import setup_logger

logger = setup_logger("Tests")

RUN_INTEGRATION_TESTS = os.getenv("RUN_AGENT_INTEGRATION_TESTS") == "1"
requires_integration = pytest.mark.skipif(
    not RUN_INTEGRATION_TESTS,
    reason="Set RUN_AGENT_INTEGRATION_TESTS=1 to enable integration tests.",
)


def test_action_registry():
    """Validate registry lookups without side effects."""

    action = action_registry.get_action("open_application")
    assert action is not None
    assert action.name == "open_application"

    alias_action = action_registry.get_action("launch")
    assert alias_action is not None
    assert alias_action.name == "open_application"

    fuzzy_action = action_registry.get_action("open app")
    assert fuzzy_action is not None

    all_actions = action_registry.get_all_actions()
    assert len(all_actions) > 10


@requires_integration
def test_gemini_connection():
    """Integration: ensure Gemini client returns structured plans."""

    client = EnhancedGeminiClient()
    plan = client.generate_task_plan("open notepad and type hello")

    assert isinstance(plan, dict)
    assert "understood" in plan
    assert "steps" in plan

    if not plan.get("understood"):
        pytest.skip("Gemini model could not understand the request in this environment.")

    assert isinstance(plan.get("steps"), list)


@requires_integration
def test_basic_automation():
    """Integration: opening and closing Notepad should complete successfully."""

    agent = EnhancedAIAgent()
    result = agent.execute_task("open notepad")
    assert result.get("success"), f"Automation failed: {result}"

    agent.execute_task("close notepad")


@requires_integration
def test_multi_step_task():
    """Integration: execute a multi-step typing routine."""

    agent = EnhancedAIAgent()
    result = agent.execute_task("open notepad and type 'Enhanced AI Agent Test'")
    assert result.get("success"), f"Task failed: {result}"


@requires_integration
def test_error_recovery():
    """Integration: invalid instructions should fail gracefully."""

    agent = EnhancedAIAgent()
    result = agent.execute_task("click on the purple unicorn button")
    assert not result.get("success"), "Agent unexpectedly succeeded on impossible task"
    assert "error" in result
