"""Custom exception hierarchy for DjenisAiAgent.

All project-specific exceptions inherit from DjenisError so callers can
catch the entire family with a single ``except DjenisError`` clause, or
handle individual error types with more granular clauses.
"""

from __future__ import annotations


class DjenisError(Exception):
    """Base exception for all DjenisAiAgent errors."""


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


class ConfigurationError(DjenisError):
    """Raised when the agent configuration is invalid or incomplete."""


class MissingApiKeyError(ConfigurationError):
    """Raised when a required API key is absent or is a placeholder value."""


# ---------------------------------------------------------------------------
# Perception errors
# ---------------------------------------------------------------------------


class PerceptionError(DjenisError):
    """Raised when screen capture or UI tree construction fails."""


class ScreenCaptureError(PerceptionError):
    """Raised when a screenshot cannot be taken."""


class UISnapshotError(PerceptionError):
    """Raised when the UI element tree cannot be built."""


# ---------------------------------------------------------------------------
# Reasoning errors
# ---------------------------------------------------------------------------


class ReasoningError(DjenisError):
    """Raised when the AI reasoning step encounters an unrecoverable error."""


class GeminiAPIError(ReasoningError):
    """Raised when the Gemini API call fails after all retries are exhausted."""


class InvalidToolCallError(ReasoningError):
    """Raised when the model returns a tool call that cannot be dispatched."""


# ---------------------------------------------------------------------------
# Action / tool execution errors
# ---------------------------------------------------------------------------


class ToolExecutionError(DjenisError):
    """Raised when an action tool fails to execute the requested operation."""

    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"[{tool_name}] {reason}")


class ElementNotFoundError(ToolExecutionError):
    """Raised when a UI element cannot be located by any available strategy."""

    def __init__(self, query: str) -> None:
        super().__init__("element_lookup", f"Element not found: {query!r}")
        self.query = query


class ActionTimeoutError(ToolExecutionError):
    """Raised when a tool operation exceeds its allowed time budget."""

    def __init__(self, tool_name: str, timeout: float) -> None:
        super().__init__(tool_name, f"Operation timed out after {timeout}s")
        self.timeout = timeout


class ShellCommandError(ToolExecutionError):
    """Raised when a shell command exits with a non-zero return code."""

    def __init__(self, command: str, return_code: int, stderr: str) -> None:
        super().__init__("run_shell_command", f"Exit code {return_code}: {stderr}")
        self.command = command
        self.return_code = return_code
        self.stderr = stderr


# ---------------------------------------------------------------------------
# Browser errors
# ---------------------------------------------------------------------------


class BrowserError(DjenisError):
    """Raised when a browser automation operation fails."""


class BrowserNotAvailableError(BrowserError):
    """Raised when no browser driver can be initialised."""


class BrowserElementError(BrowserError):
    """Raised when a browser element cannot be found or interacted with."""


# ---------------------------------------------------------------------------
# Transcription errors
# ---------------------------------------------------------------------------


class TranscriptionError(DjenisError):
    """Raised when audio transcription fails."""


class VoskModelNotLoadedError(TranscriptionError):
    """Raised when the Vosk model has not been loaded yet."""
