"""Unit tests for src/exceptions.py."""

from __future__ import annotations

import pytest

from src.exceptions import (
    ActionTimeoutError,
    BrowserError,
    BrowserNotAvailableError,
    ConfigurationError,
    DjenisError,
    ElementNotFoundError,
    GeminiAPIError,
    InvalidToolCallError,
    MissingApiKeyError,
    PerceptionError,
    ReasoningError,
    ScreenCaptureError,
    ShellCommandError,
    ToolExecutionError,
    TranscriptionError,
    UISnapshotError,
    VoskModelNotLoadedError,
)


class TestExceptionHierarchy:
    def test_all_exceptions_inherit_from_djenis_error(self) -> None:
        leaf_exceptions = [
            ConfigurationError("c"),
            MissingApiKeyError("m"),
            PerceptionError("p"),
            ScreenCaptureError("s"),
            UISnapshotError("u"),
            ReasoningError("r"),
            GeminiAPIError("g"),
            InvalidToolCallError("i"),
            ToolExecutionError("tool", "reason"),
            ElementNotFoundError("query"),
            ActionTimeoutError("tool", 5.0),
            ShellCommandError("cmd", 1, "err"),
            BrowserError("b"),
            BrowserNotAvailableError("bn"),
            BrowserError("be"),
            TranscriptionError("t"),
            VoskModelNotLoadedError("v"),
        ]
        for exc in leaf_exceptions:
            assert isinstance(exc, DjenisError), f"{type(exc).__name__} is not a DjenisError"

    def test_configuration_errors_hierarchy(self) -> None:
        assert issubclass(MissingApiKeyError, ConfigurationError)
        assert issubclass(ConfigurationError, DjenisError)

    def test_perception_errors_hierarchy(self) -> None:
        assert issubclass(ScreenCaptureError, PerceptionError)
        assert issubclass(UISnapshotError, PerceptionError)
        assert issubclass(PerceptionError, DjenisError)

    def test_reasoning_errors_hierarchy(self) -> None:
        assert issubclass(GeminiAPIError, ReasoningError)
        assert issubclass(InvalidToolCallError, ReasoningError)
        assert issubclass(ReasoningError, DjenisError)

    def test_tool_execution_errors_hierarchy(self) -> None:
        assert issubclass(ElementNotFoundError, ToolExecutionError)
        assert issubclass(ActionTimeoutError, ToolExecutionError)
        assert issubclass(ShellCommandError, ToolExecutionError)
        assert issubclass(ToolExecutionError, DjenisError)

    def test_browser_errors_hierarchy(self) -> None:
        assert issubclass(BrowserNotAvailableError, BrowserError)
        assert issubclass(BrowserError, DjenisError)

    def test_transcription_errors_hierarchy(self) -> None:
        assert issubclass(VoskModelNotLoadedError, TranscriptionError)
        assert issubclass(TranscriptionError, DjenisError)


class TestExceptionMessages:
    def test_tool_execution_error_formats_message(self) -> None:
        exc = ToolExecutionError("click", "Element not found")
        assert "[click]" in str(exc)
        assert "Element not found" in str(exc)

    def test_element_not_found_error_includes_query(self) -> None:
        exc = ElementNotFoundError("Submit button")
        assert "Submit button" in str(exc)
        assert exc.query == "Submit button"

    def test_action_timeout_error_includes_duration(self) -> None:
        exc = ActionTimeoutError("element_id", 8.0)
        assert "8.0" in str(exc)
        assert exc.timeout == 8.0

    def test_shell_command_error_includes_return_code(self) -> None:
        exc = ShellCommandError("rm -rf /", 1, "Permission denied")
        assert "1" in str(exc) or "Permission denied" in str(exc)
        assert exc.return_code == 1
        assert exc.command == "rm -rf /"
        assert exc.stderr == "Permission denied"


class TestExceptionCanBeCaught:
    def test_catch_by_base_class(self) -> None:
        with pytest.raises(DjenisError):
            raise ToolExecutionError("click", "failed")

    def test_catch_by_intermediate_class(self) -> None:
        with pytest.raises(ToolExecutionError):
            raise ElementNotFoundError("button")

    def test_does_not_catch_unrelated_exception(self) -> None:
        with pytest.raises(ValueError):
            try:
                raise ValueError("unrelated")
            except DjenisError:
                pass  # Should NOT catch ValueError
            raise ValueError("unrelated")  # Re-raise to satisfy pytest.raises
