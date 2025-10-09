"""Unit tests for planning telemetry helpers."""

import time
import unittest
from collections import deque
from typing import Any, cast

from src.config.config import AgentConfig, config

try:
    from src.core.agent import StepContext, StepStatus, FailureHandlingOutcome, EnhancedAIAgent
    from src.core.executor import ActionResult
except Exception as exc:  # pragma: no cover - handled via skip
    StepContext = None  # type: ignore
    StepStatus = None  # type: ignore
    FailureHandlingOutcome = None  # type: ignore
    EnhancedAIAgent = None  # type: ignore
    ActionResult = None  # type: ignore
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(IMPORT_ERROR is not None, f"Optional dependencies missing: {IMPORT_ERROR}")
class StepContextBehaviourTest(unittest.TestCase):
    """Validate step context bookkeeping."""

    def test_step_context_state_transitions(self):
        assert StepContext is not None and StepStatus is not None and ActionResult is not None

        ctx = StepContext(index=1, raw={"action": "click", "target": "button"})
        self.assertEqual(ctx.status, StepStatus.PENDING)
        self.assertEqual(ctx.attempts, 0)

        ctx.begin()
        self.assertEqual(ctx.status, StepStatus.RUNNING)
        self.assertEqual(ctx.attempts, 1)

        result = ActionResult(
            action="click",
            target="button",
            parameters={},
            success=False,
            started_at=time.time(),
            finished_at=time.time(),
            error="test failure",
        )

        ctx.complete(result)
        self.assertEqual(ctx.status, StepStatus.FAILED)
        self.assertIs(ctx.last_result, result)

        ctx.add_note("retry scheduled")
        self.assertEqual(ctx.adaptive_notes[-1], "retry scheduled")

    def test_failure_handling_outcome_truthiness(self):
        assert FailureHandlingOutcome is not None
        resolved = FailureHandlingOutcome(resolved=True, added_steps=2)
        self.assertTrue(resolved)
        self.assertEqual(resolved.added_steps, 2)

        unresolved = FailureHandlingOutcome(resolved=False)
        self.assertFalse(unresolved)

    def test_recovery_injection_precedes_original_step(self):
        assert StepContext is not None and EnhancedAIAgent is not None

        agent = object.__new__(EnhancedAIAgent)

        step_cls = cast(Any, StepContext)

        original_ctx = step_cls(index=1, raw={"action": "original"})
        remaining = deque([original_ctx])
        created_contexts = []

        def _new_context(payload):
            ctx = step_cls(index=len(created_contexts) + 2, raw=payload)
            created_contexts.append(ctx)
            return ctx

        recovery_steps = [
            {"action": "recover_first", "target": "t1"},
            {"action": "recover_second", "target": "t2"},
        ]

        agent._inject_steps(recovery_steps, remaining, _new_context)

        ordered_actions = [ctx.raw["action"] for ctx in list(remaining)]
        self.assertEqual(ordered_actions[0], "recover_first")
        self.assertEqual(ordered_actions[1], "recover_second")
        self.assertEqual(ordered_actions[2], "original")


class ConfigModeBehaviourTest(unittest.TestCase):
    """Validate configuration overrides for no-limit mode."""

    def test_no_limit_mode_lifts_ceiling_values(self):
        factory = config.model_dump if hasattr(config, "model_dump") else config.dict  # type: ignore[attr-defined]
        baseline = factory()
        local_cfg = AgentConfig(**baseline)

        local_cfg.gemini_max_output_tokens = 1024
        local_cfg.max_retries = 1
        local_cfg.mouse_max_attempts = 5
        local_cfg.mouse_path_segments = 2
        local_cfg.max_task_duration = 60
        local_cfg.api_timeout = 30

        local_cfg.apply_no_limit_mode()

        self.assertTrue(local_cfg.no_limit_mode)
        self.assertGreaterEqual(local_cfg.gemini_max_output_tokens, 1_048_576)
        self.assertGreaterEqual(local_cfg.max_retries, 50)
        self.assertGreaterEqual(local_cfg.mouse_max_attempts, 1_000)
        self.assertGreaterEqual(local_cfg.mouse_path_segments, 10)
        self.assertGreaterEqual(local_cfg.max_task_duration, 12 * 60 * 60)
        self.assertGreaterEqual(local_cfg.api_timeout, 600)


if __name__ == "__main__":  # pragma: no cover - manual execution fallback
    unittest.main()
