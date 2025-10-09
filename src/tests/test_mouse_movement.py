"""Unit tests for enhanced mouse movement logic."""

import unittest
from unittest.mock import patch

from src.automation.ui_automation import UIAutomationEngine, MouseMoveTelemetry


class MouseMovementTests(unittest.TestCase):
    """Validate telemetry-driven mouse movement helpers."""

    @patch("src.automation.ui_automation.pyautogui.moveRel")
    @patch("src.automation.ui_automation.pyautogui.moveTo")
    @patch("src.automation.ui_automation.pyautogui.size", return_value=(1920, 1080))
    def test_move_mouse_precise_succeeds_first_attempt(
        self,
        _mock_size,
        mock_move_to,
        mock_move_rel,
    ) -> None:
        """Mouse should reach target within tolerance on first attempt."""

        engine = UIAutomationEngine()

        positions = iter([(10, 10), (200, 200)])

        def fake_position() -> tuple[int, int]:
            try:
                return next(positions)
            except StopIteration:
                return (200, 200)

        engine.get_mouse_position = fake_position  # type: ignore[assignment]

        telemetry = engine.move_mouse_precise(
            200,
            200,
            tolerance=3,
            max_attempts=2,
            base_duration=0.1,
            path_segments=0,
        )

        self.assertIsInstance(telemetry, MouseMoveTelemetry)
        self.assertTrue(telemetry.success)
        self.assertEqual(telemetry.attempts, 1)
        self.assertEqual(telemetry.final_position, (200, 200))
        mock_move_to.assert_called()
        mock_move_rel.assert_not_called()

    @patch("src.automation.ui_automation.pyautogui.moveRel")
    @patch("src.automation.ui_automation.pyautogui.moveTo")
    @patch("src.automation.ui_automation.pyautogui.size", return_value=(1920, 1080))
    def test_move_mouse_precise_applies_micro_correction(
        self,
        _mock_size,
        mock_move_to,
        mock_move_rel,
    ) -> None:
        """Residual offset should trigger micro correction flow."""

        engine = UIAutomationEngine()

        positions = iter([(0, 0), (198, 198), (200, 200)])

        def fake_position() -> tuple[int, int]:
            try:
                return next(positions)
            except StopIteration:
                return (200, 200)

        engine.get_mouse_position = fake_position  # type: ignore[assignment]

        telemetry = engine.move_mouse_precise(
            200,
            200,
            tolerance=1,
            max_attempts=2,
            base_duration=0.1,
            path_segments=0,
        )

        self.assertTrue(telemetry.success)
        self.assertGreaterEqual(len(telemetry.corrections_applied), 1)
        mock_move_rel.assert_called()
        final_correction = telemetry.corrections_applied[-1]
        self.assertIn("post_correction_offset", final_correction)
        self.assertEqual(telemetry.final_position, (200, 200))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
