from typing import List, Dict, Any

class ShortTermMemory:

    def __init__(self):
        self.history: List[Dict[str, Any]] = []

    def add_turn(self, thought: str, tool_name: str, tool_args: Dict[str, Any], tool_result: str) -> None:
        turn_data = {
            "thought": thought,
            "action": {
                "name": tool_name,
                "args": tool_args
            },
            "result": tool_result
        }
        self.history.append(turn_data)

    def get_formatted_history(self) -> str:
        if not self.history:
            return "No previous actions in memory."

        formatted_string = "This is the history of recent actions:\n\n"
        for i, turn in enumerate(self.history):
            formatted_string += f"--- Start Turn {i+1} ---\n"
            formatted_string += f"Thought: {turn['thought']}\n"
            formatted_string += f"Action: I used the tool '{turn['action']['name']}' with arguments {turn['action']['args']}\n"
            formatted_string += f"Result: {turn['result']}\n"
            formatted_string += f"--- End Turn {i+1} ---\n\n"

        return formatted_string.strip()

    def clear(self) -> None:
        self.history = []
