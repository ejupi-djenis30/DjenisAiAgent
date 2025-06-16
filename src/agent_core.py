import os
import importlib
import inspect
from typing import Dict, List

from src.memory.short_term_memory import ShortTermMemory
from src.perception import screen_analyzer
from src.planning import planner
from src.tools.base_tool import BaseTool

class AgentCore:
    def __init__(self):
        self.memory = ShortTermMemory()
        self.tools = self._load_tools()
        print("\n--- DjenisAiAgent Initialized ---")
        print(f"Tools loaded: {', '.join(self.tools.keys())}")

    def _load_tools(self) -> Dict[str, BaseTool]:
        """Dynamically loads all tool classes from the 'tools' directory."""
        tools = {}
        tools_dir = os.path.join(os.path.dirname(__file__), 'tools')

        for filename in os.listdir(tools_dir):
            # Load all python files that are not __init__ or base_tool
            if filename.endswith('.py') and not filename.startswith('__') and filename != 'base_tool.py':
                module_name = f"src.tools.{filename[:-3]}"
                module = importlib.import_module(module_name)

                # Find all classes in the module that are subclasses of BaseTool
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
                        tool_instance = obj()
                        tools[tool_instance.name] = tool_instance
        return tools

    def run(self):
        """The main loop of the agent."""
        while True:
            user_goal = input("\nWhat is your objective? (type 'exit' to quit)\n> ").strip()

            if user_goal.lower() in ["exit", "quit"]:
                print("--- DjenisAiAgent Terminated ---")
                break

            if not user_goal:
                print("Objective cannot be empty. Please try again.")
                continue

            self.memory.clear()

            # Step limit to prevent infinite loops
            max_steps = 10
            for step in range(1, max_steps + 1):
                print(f"\n===== Starting Step {step}/{max_steps} =====")

                screen_b64 = screen_analyzer.analyze_screen()
                if not screen_b64:
                    print("Could not analyze the screen. Aborting the task.")
                    break

                history = self.memory.get_formatted_history()
                available_tools_list = list(self.tools.values())

                planner_response = planner.get_next_step(
                    user_goal, history, screen_b64, available_tools_list
                )

                if "error" in planner_response:
                    print(f"Planner Error: {planner_response['error']}")
                    break # Abort task if planner fails

                thought = planner_response.get("thought", "No thought recorded.")
                tool_choice = planner_response.get("tool", {})
                tool_name = tool_choice.get("name")
                tool_args = tool_choice.get("args", {})

                print(f"Agent's Thought: {thought}")

                if not tool_name:
                    print("The Planner did not choose a tool. The task may be finished.")
                    break

                # Execute the chosen tool
                if tool_name in self.tools:
                    tool_to_execute = self.tools[tool_name]
                    result = tool_to_execute.execute(**tool_args)
                else:
                    result = f"Error: Tool '{tool_name}' not found."

                print(f"Tool Result: {result}")

                self.memory.add_turn(thought, tool_name, tool_args, result)

                # Check if the task is completed
                if tool_name == "task_completed":
                    print("Agent has concluded the task.")
                    break

            else: # Executed only if the for loop finishes without a 'break'
                print(f"\nReached the limit of {max_steps} steps for this objective.")
