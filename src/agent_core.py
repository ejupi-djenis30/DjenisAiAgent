import os
import inspect
import importlib
from typing import Dict, List, Any

from src import config
from src.memory.short_term_memory import ShortTermMemory
from src.planning import planner
from src.tools.base_tool import BaseTool
from src.abstractions.display_adapter import DisplayAdapter

class AgentCore:
    def __init__(self):
        self.memory = ShortTermMemory()
        self.display_adapter = DisplayAdapter()
        self.platform_agnostic_tools = self._load_platform_agnostic_tools()
        self.tool_definitions = self._get_all_tool_definitions()

        print("\n--- DjenisAiAgent Initialized ---")
        print(f"Session Type: {self.display_adapter.session_type.upper()}")
        loaded_tools = [tool['name'] for tool in self.tool_definitions]
        print(f"Tools loaded: {', '.join(loaded_tools)}")

    def _load_platform_agnostic_tools(self) -> Dict[str, BaseTool]:
        tools: Dict[str, BaseTool] = {}
        tools_dir = os.path.join(os.path.dirname(__file__), 'tools')
        excluded_files = {'__init__.py', 'base_tool.py', 'gui_tool.py', 'wayland_input.py'}

        for filename in os.listdir(tools_dir):
            if filename.endswith('.py') and filename not in excluded_files:
                module_name = f"src.tools.{filename[:-3]}"
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
                        tool_instance = obj()
                        tools[tool_instance.name] = tool_instance
        return tools

    def _get_all_tool_definitions(self) -> List[Dict[str, str]]:
        definitions: List[Dict[str, str]] = []
        for tool in self.platform_agnostic_tools.values():
            definitions.append({"name": tool.name, "description": tool.description})

        input_controller = self.display_adapter.input
        for name, method in inspect.getmembers(input_controller, predicate=inspect.ismethod):
            if not name.startswith('_'):
                doc = inspect.getdoc(method) or f"Executes the '{name}' GUI action."
                definitions.append({"name": name, "description": doc})
        return definitions

    def _execute_action(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        try:
            if tool_name in self.platform_agnostic_tools:
                tool_to_execute = self.platform_agnostic_tools[tool_name]
                return tool_to_execute.execute(**tool_args)

            if hasattr(self.display_adapter.input, tool_name):
                method_to_call = getattr(self.display_adapter.input, tool_name)
                return method_to_call(**tool_args)

            return f"Error: Tool or action '{tool_name}' not found."
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"

    def run_task(self, user_goal: str):
        if not user_goal:
            print("Objective cannot be empty. Aborting task.")
            return

        self.memory.clear()
        max_steps = config.MAX_STEPS

        for step in range(1, max_steps + 1):
            print(f"\n===== Starting Step {step}/{max_steps} for objective: '{user_goal}' =====")

            # Perception
            screen_b64 = self.display_adapter.screen.capture_and_process()
            if not screen_b64:
                print("Critical Error: Could not capture or process the screen. Aborting task.")
                break

            # Memory / Context
            history = self.memory.get_formatted_history()

            # Reasoning
            planner_response = planner.get_next_step(
                user_goal, history, screen_b64, self.tool_definitions
            )

            if "error" in planner_response:
                print(f"Planner Error: {planner_response['error']}. Aborting task.")
                break

            thought = planner_response.get("thought", "No thought recorded.")
            tool_call = planner_response.get("tool_call")

            print(f"Agent's Thought: {thought}")

            if not tool_call or not isinstance(tool_call, dict):
                print("Planner did not return a valid tool call. The task may be finished or stuck.")
                break

            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})

            if not tool_name:
                print("The Planner did not choose a tool name. The task may be finished or stuck.")
                break

            # Action
            result = self._execute_action(tool_name, tool_args)
            print(f"Action Result: {result}")

            # Memory Update
            self.memory.add_turn(thought, tool_name, tool_args, result)

            if tool_name == "task_completed":
                print(f"Agent has concluded the task with reason: {tool_args.get('reason', 'N/A')}")
                break
        else:
            print(f"\nReached the step limit of {max_steps} for this objective without completion.")
