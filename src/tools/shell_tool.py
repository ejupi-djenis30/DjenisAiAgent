import subprocess
from .base_tool import BaseTool

class ShellTool(BaseTool):

    @property
    def name(self) -> str:
        return "execute_shell_command"

    @property
    def description(self) -> str:
        return "Executes a command in the Linux shell and returns its output. Useful for navigating the file system (e.g., 'ls -l'), checking system status, or running scripts. The argument must be a string containing the entire command."

    def execute(self, command: str) -> str:
        print(f"--- Executing Shell Tool: `{command}` ---")
        if not isinstance(command, str):
            return "Error: the provided command is not a text string."

        try:
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout.strip()
            if not output:
                return "Command executed successfully, no output produced."
            return output

        except subprocess.CalledProcessError as e:
            error_message = f"Error during command execution. Error output:\n{e.stderr.strip()}"
            return error_message

        except subprocess.TimeoutExpired:
            return "Error: the command took too long to execute (30-second timeout)."

        except Exception as e:
            return f"An unexpected error occurred: {e}"
