import os
import inspect
import importlib
from typing import Dict, List, Any

from src.memory.short_term_memory import ShortTermMemory
from src.planning import planner
from src.tools.base_tool import BaseTool

from src.perception.screen_analyzer import analyze_screen
from src.tools.gui_tool import X11InputController

class AgentCore:
    def __init__(self):
        self.memory = ShortTermMemory()
        self.session_type = self._get_session_type()

        self._initialize_controllers()

        self.tools = self._load_platform_agnostic_tools()
        self.tool_definitions = self._get_all_tool_definitions()

        print("\n--- DjenisAiAgent Initialized ---")
        print(f"Session Type: {self.session_type}")
        print(f"Tools loaded: {', '.join([tool['name'] for tool in self.tool_definitions])}")

    def _get_session_type(self) -> str:
        session_type = os.environ.get("XDG_SESSION_TYPE", "x11").lower()
        if "wayland" in session_type:
            return "wayland"
        return "x11"

    def _initialize_controllers(self):
        if self.session_type == "wayland":
            # These imports will be used when Wayland backends are created
            # from src.perception.wayland_capture import WaylandScreenCapture
            # from src.input_backends.wayland_controller import WaylandInputController
            # self.screen_capture = WaylandScreenCapture()
            # self.input_controller = WaylandInputController()
            raise NotImplementedError("Wayland backend is not yet implemented.")
        else: # Default to x11
            self.screen_capture_function = analyze_screen
            self.input_controller = X11InputController()

    def _load_platform_agnostic_tools(self) -> Dict[str, BaseTool]:
        tools = {}
        tools_dir = os.path.join(os.path.dirname(__file__), 'tools')
        excluded_files = ['__init__.py', 'base_tool.py', 'gui_tool.py']

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
        definitions = []
        for name, tool in self.tools.items():
            definitions.append({"name": tool.name, "description": tool.description})

        # Generate definitions from the input controller's methods
        for name, method in inspect.getmembers(self.input_controller, predicate=inspect.ismethod):
            if not name.startswith('_'):
                # A simple way to describe GUI actions
                description = f"Executes the '{name}' GUI action. Arguments: {inspect.getfullargspec(method).args[1:]}"
                if name == "mouse_click":
                    description = "Executes a mouse click at a specific screen coordinate (x, y). Arguments: 'x: int', 'y: int', 'button: str' (optional, default 'left')."
                elif name == "type_text":
                    description = "Types the provided text into the currently active window. Argument: 'text: str'."
                elif name == "mouse_move":
                    description = "Moves the mouse cursor to a specific screen coordinate (x, y). Arguments: 'x: int', 'y: int'."
                elif name == "press_hotkey":
                    description = "Simulates pressing a combination of keys (e.g., ['ctrl', 'c']). Argument: 'keys: List[str]'."

                definitions.append({"name": name, "description": description})
        return definitions

    def run(self):
        while True:
            user_goal = input("\nWhat is your objective? (type 'exit' to quit)\n> ").strip()
            if user_goal.lower() in ["exit", "quit"]:
                print("--- DjenisAiAgent Terminated ---")
                break
            if not user_goal:
                print("Objective cannot be empty. Please try again.")
                continue

            self.memory.clear()
            max_steps = 15
            for step in range(1, max_steps + 1):
                print(f"\n===== Starting Step {step}/{max_steps} =====")

                screen_b64 = self.screen_capture_function()
                if not screen_b64:
                    print("Could not analyze the screen. Aborting the task.")
                    break

                history = self.memory.get_formatted_history()

                # We need to re-create the tool classes for the planner description
                class TempTool(BaseTool):
                    def __init__(self, name, description):
                        self._name = name
                        self._description = description
                    @property
                    def name(self) -> str: return self._name
                    @property
                    def description(self) -> str: return self._description
                    def execute(self): pass

                planner_tools = [TempTool(d['name'], d['description']) for d in self.tool_definitions]

                planner_response = planner.get_next_step(
                    user_goal, history, screen_b64, planner_tools
                )

                if "error" in planner_response:
                    print(f"Planner Error: {planner_response['error']}")
                    break

                thought = planner_response.get("thought", "No thought recorded.")
                tool_call = planner_response.get("tool_call", {})
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("args", {})

                print(f"Agent's Thought: {thought}")

                if not tool_name:
                    print("The Planner did not choose a tool. The task may be finished or stuck.")
                    break

                result = ""
                if tool_name in self.tools:
                    tool_to_execute = self.tools[tool_name]
                    result = tool_to_execute.execute(**tool_args)
                elif hasattr(self.input_controller, tool_name):
                    method_to_call = getattr(self.input_controller, tool_name)
                    result = method_to_call(**tool_args)
                else:
                    result = f"Error: Tool or action '{tool_name}' not found."

                print(f"Action Result: {result}")
                self.memory.add_turn(thought, tool_name, tool_args, result)

                if tool_name == "task_completed":
                    print("Agent has concluded the task.")
                    break
            else:
                print(f"\nReached the limit of {max_steps} steps for this objective.")
