from .base_tool import BaseTool

class TaskCompletedTool(BaseTool):
    """
    A tool to be called when the main objective has been successfully completed.
    """

    @property
    def name(self) -> str:
        """The name of the tool."""
        return "task_completed"

    @property
    def description(self) -> str:
        """A description of the tool's purpose and arguments."""
        return "Call this tool when the main objective has been successfully completed. The 'reason' argument should explain why you consider the task finished."

    def execute(self, reason: str) -> str:
        """
        Marks the task as completed.

        Args:
            reason: A string explaining why the task is considered complete.

        Returns:
            A confirmation string indicating the task is complete.
        """
        print(f"--- Executing Task Completed Tool ---")
        return f"Task marked as completed. Reason: {reason}"
