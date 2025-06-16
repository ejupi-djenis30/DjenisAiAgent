import os
from .base_tool import BaseTool

class ListFilesTool(BaseTool):
    @property
    def name(self) -> str:
        return "list_files_in_directory"

    @property
    def description(self) -> str:
        return "Lists files and folders in a specific directory. Argument: 'directory_path: str'."

    def execute(self, directory_path: str = ".") -> str:
        print(f"--- Executing File System Tool: List files in `{directory_path}` ---")
        try:
            if not os.path.isdir(directory_path):
                return f"Error: The path '{directory_path}' is not a valid directory."

            files = os.listdir(directory_path)
            if not files:
                return f"The directory '{directory_path}' is empty."
            return "\n".join(files)
        except FileNotFoundError:
            return f"Error: The directory '{directory_path}' was not found."
        except PermissionError:
            return f"Error: Insufficient permissions to access the directory '{directory_path}'."
        except Exception as e:
            return f"An unexpected error occurred: {e}"

class ReadFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "read_file_content"

    @property
    def description(self) -> str:
        return "Reads the entire content of a text file and returns it as a string. Argument: 'file_path: str'."

    def execute(self, file_path: str) -> str:
        print(f"--- Executing File System Tool: Read file `{file_path}` ---")
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except FileNotFoundError:
            return f"Error: The file '{file_path}' was not found."
        except PermissionError:
            return f"Error: Insufficient permissions to read the file '{file_path}'."
        except UnicodeDecodeError:
            return f"Error: The file '{file_path}' does not appear to be a valid text file (UTF-8)."
        except Exception as e:
            return f"An unexpected error occurred: {e}"

class WriteFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "write_content_to_file"

    @property
    def description(self) -> str:
        return "Writes or overwrites a file with the provided text content. If the file does not exist, it is created. Arguments: 'file_path: str', 'content: str'."

    def execute(self, file_path: str, content: str) -> str:
        print(f"--- Executing File System Tool: Write to file `{file_path}` ---")
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            return f"Content successfully written to file '{file_path}'."
        except PermissionError:
            return f"Error: Insufficient permissions to write to the file '{file_path}'."
        except Exception as e:
            return f"An unexpected error occurred while writing the file: {e}"
