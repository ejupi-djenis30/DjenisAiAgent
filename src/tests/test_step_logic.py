"""Unit tests for planning telemetry helpers."""

import time
import unittest

try:
    from src.core.agent import StepContext, StepStatus, FailureHandlingOutcome
    from src.core.executor import ActionResult
except Exception as exc:  # pragma: no cover - handled via skip
    StepContext = None  # type: ignore
    StepStatus = None  # type: ignore
    FailureHandlingOutcome = None  # type: ignore
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


if __name__ == "__main__":  # pragma: no cover - manual execution fallback
    unittest.main()
