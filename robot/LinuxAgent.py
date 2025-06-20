import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.agent_core import AgentCore

class LinuxAgent:
    ROBOT_LIBRARY_SCOPE = 'SUITE'

    def __init__(self):
        self.agent = AgentCore()

    def execute_task_on_ui(self, objective: str):
        if not objective or not isinstance(objective, str):
            raise ValueError("The objective must be a non-empty string.")

        print(f"--- Received objective: '{objective}' ---")

        self.agent.run_task(user_goal=objective)
