"""
Action Registry - Comprehensive action definitions for UI automation.
"""

from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass
from enum import Enum


class ActionCategory(Enum):
    """Categories of actions."""
    APPLICATION = "application"
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    WINDOW = "window"
    NAVIGATION = "navigation"
    SYSTEM = "system"
    VERIFICATION = "verification"


@dataclass
class ActionDefinition:
    """Definition of an action with metadata."""
    name: str
    category: ActionCategory
    description: str
    parameters: List[str]
    examples: List[str]
    aliases: List[str]
    
    def matches(self, action_name: str) -> bool:
        """Check if action name matches this definition."""
        action_lower = action_name.lower().replace("_", " ").replace("-", " ")
        
        # Direct match
        if action_name == self.name or action_name in self.aliases:
            return True
        
        # Fuzzy match
        name_words = self.name.lower().replace("_", " ").split()
        action_words = action_lower.split()
        
        return any(word in action_words for word in name_words)


class ActionRegistry:
    """Registry of all supported actions."""
    
    def __init__(self):
        self.actions: Dict[str, ActionDefinition] = {}
        self._register_default_actions()
    
    def _register_default_actions(self):
        """Register all default actions."""
        
        # Application Actions
        self.register(ActionDefinition(
            name="open_application",
            category=ActionCategory.APPLICATION,
            description="Open or launch an application",
            parameters=["application_name"],
            examples=["open notepad", "launch calculator", "start chrome"],
            aliases=["launch_app", "start_app", "open_app", "launch", "start", "run"]
        ))
        
        self.register(ActionDefinition(
            name="close_application",
            category=ActionCategory.APPLICATION,
            description="Close an application",
            parameters=["application_name"],
            examples=["close notepad", "exit chrome"],
            aliases=["close_app", "exit_app", "quit_app", "close", "exit", "quit"]
        ))
        
        # Keyboard Actions
        self.register(ActionDefinition(
            name="type_text",
            category=ActionCategory.KEYBOARD,
            description="Type text at the current cursor position",
            parameters=["text"],
            examples=["type hello world", "write some text"],
            aliases=["type", "write", "input_text", "enter_text", "input", "write_text"]
        ))
        
        self.register(ActionDefinition(
            name="press_key",
            category=ActionCategory.KEYBOARD,
            description="Press a single key",
            parameters=["key"],
            examples=["press enter", "press escape"],
            aliases=["press", "key_press", "hit_key", "tap"]
        ))
        
        self.register(ActionDefinition(
            name="hotkey",
            category=ActionCategory.KEYBOARD,
            description="Press a combination of keys",
            parameters=["keys"],
            examples=["ctrl+c", "alt+f4", "ctrl+shift+t"],
            aliases=["keyboard_shortcut", "key_combination", "shortcut", "combo"]
        ))
        
        # Mouse Actions
        self.register(ActionDefinition(
            name="click",
            category=ActionCategory.MOUSE,
            description="Click on an element or at coordinates",
            parameters=["target"],
            examples=["click button", "click at 100,200"],
            aliases=["left_click", "mouse_click", "tap"]
        ))
        
        self.register(ActionDefinition(
            name="double_click",
            category=ActionCategory.MOUSE,
            description="Double-click on an element",
            parameters=["target"],
            examples=["double click icon", "double click file"],
            aliases=["dblclick", "double_tap"]
        ))
        
        self.register(ActionDefinition(
            name="right_click",
            category=ActionCategory.MOUSE,
            description="Right-click to open context menu",
            parameters=["target"],
            examples=["right click desktop", "context menu"],
            aliases=["context_click", "right_mouse_click"]
        ))
        
        self.register(ActionDefinition(
            name="drag",
            category=ActionCategory.MOUSE,
            description="Drag from one location to another",
            parameters=["start", "end"],
            examples=["drag file to folder", "drag 100,100 to 200,200"],
            aliases=["drag_and_drop", "move_drag", "drag_to"]
        ))
        
        self.register(ActionDefinition(
            name="scroll",
            category=ActionCategory.MOUSE,
            description="Scroll up or down",
            parameters=["direction", "amount"],
            examples=["scroll down", "scroll up 5 clicks"],
            aliases=["scroll_page", "wheel"]
        ))
        
        self.register(ActionDefinition(
            name="move_mouse",
            category=ActionCategory.MOUSE,
            description="Move mouse to specific coordinates",
            parameters=["x", "y"],
            examples=["move mouse to 100,200", "move cursor to 500,300"],
            aliases=["move_cursor", "mouse_move"]
        ))
        
        self.register(ActionDefinition(
            name="move_mouse_fine",
            category=ActionCategory.MOUSE,
            description="Move mouse one pixel at a time in a direction (up, down, left, right). Used for precise targeting guided by AI vision.",
            parameters=["direction"],
            examples=["move mouse up", "move mouse left", "move mouse down", "move mouse right"],
            aliases=["nudge_mouse", "fine_move", "pixel_move"]
        ))
        
        self.register(ActionDefinition(
            name="get_mouse_position",
            category=ActionCategory.MOUSE,
            description="Get current mouse cursor position",
            parameters=[],
            examples=["get mouse position", "where is cursor"],
            aliases=["mouse_position", "cursor_position", "mouse_location"]
        ))
        
        # Window Actions
        self.register(ActionDefinition(
            name="focus_window",
            category=ActionCategory.WINDOW,
            description="Focus or activate a window",
            parameters=["window_title"],
            examples=["focus notepad", "activate chrome"],
            aliases=["activate_window", "switch_to_window", "bring_to_front", "focus", "activate"]
        ))
        
        self.register(ActionDefinition(
            name="minimize_window",
            category=ActionCategory.WINDOW,
            description="Minimize a window",
            parameters=["window_title"],
            examples=["minimize notepad"],
            aliases=["minimize"]
        ))
        
        self.register(ActionDefinition(
            name="maximize_window",
            category=ActionCategory.WINDOW,
            description="Maximize a window",
            parameters=["window_title"],
            examples=["maximize chrome"],
            aliases=["maximize"]
        ))
        
        # Navigation Actions
        self.register(ActionDefinition(
            name="navigate_to",
            category=ActionCategory.NAVIGATION,
            description="Navigate to a URL or location",
            parameters=["url"],
            examples=["go to google.com", "navigate to youtube"],
            aliases=["go_to", "browse_to", "open_url", "visit"]
        ))
        
        # System Actions
        self.register(ActionDefinition(
            name="wait",
            category=ActionCategory.SYSTEM,
            description="Wait for a specified duration",
            parameters=["seconds"],
            examples=["wait 2 seconds", "pause for 1 second"],
            aliases=["pause", "sleep", "delay"]
        ))
        
        self.register(ActionDefinition(
            name="screenshot",
            category=ActionCategory.SYSTEM,
            description="Take a screenshot",
            parameters=["filename"],
            examples=["take screenshot", "capture screen"],
            aliases=["capture", "screen_capture", "take_screenshot"]
        ))
        
        # Verification Actions
        self.register(ActionDefinition(
            name="verify",
            category=ActionCategory.VERIFICATION,
            description="Verify a condition",
            parameters=["condition"],
            examples=["verify window is open", "check if element exists"],
            aliases=["check", "validate", "confirm", "assert"]
        ))
        
        self.register(ActionDefinition(
            name="find_element",
            category=ActionCategory.VERIFICATION,
            description="Find a UI element",
            parameters=["description"],
            examples=["find button", "locate text field"],
            aliases=["locate", "search_for", "find"]
        ))
        
        # Advanced Actions
        self.register(ActionDefinition(
            name="copy",
            category=ActionCategory.KEYBOARD,
            description="Copy selected content to clipboard",
            parameters=[],
            examples=["copy selected text", "copy"],
            aliases=["copy_text", "ctrl_c"]
        ))
        
        self.register(ActionDefinition(
            name="paste",
            category=ActionCategory.KEYBOARD,
            description="Paste clipboard content",
            parameters=[],
            examples=["paste text", "paste"],
            aliases=["paste_text", "ctrl_v"]
        ))
        
        self.register(ActionDefinition(
            name="cut",
            category=ActionCategory.KEYBOARD,
            description="Cut selected content to clipboard",
            parameters=[],
            examples=["cut selected text", "cut"],
            aliases=["cut_text", "ctrl_x"]
        ))
        
        self.register(ActionDefinition(
            name="select_all",
            category=ActionCategory.KEYBOARD,
            description="Select all content",
            parameters=[],
            examples=["select all", "select everything"],
            aliases=["ctrl_a", "select_everything"]
        ))
        
        self.register(ActionDefinition(
            name="undo",
            category=ActionCategory.KEYBOARD,
            description="Undo last action",
            parameters=[],
            examples=["undo", "undo last action"],
            aliases=["ctrl_z"]
        ))
        
        self.register(ActionDefinition(
            name="redo",
            category=ActionCategory.KEYBOARD,
            description="Redo last undone action",
            parameters=[],
            examples=["redo", "redo action"],
            aliases=["ctrl_y"]
        ))
        
        self.register(ActionDefinition(
            name="save",
            category=ActionCategory.KEYBOARD,
            description="Save current file or document",
            parameters=[],
            examples=["save file", "save document"],
            aliases=["save_file", "ctrl_s"]
        ))
        
        self.register(ActionDefinition(
            name="find_text",
            category=ActionCategory.KEYBOARD,
            description="Open find dialog",
            parameters=[],
            examples=["find text", "open search"],
            aliases=["search", "ctrl_f"]
        ))
        
        self.register(ActionDefinition(
            name="new_tab",
            category=ActionCategory.KEYBOARD,
            description="Open new tab (in browsers)",
            parameters=[],
            examples=["new tab", "open new tab"],
            aliases=["ctrl_t", "create_tab"]
        ))
        
        self.register(ActionDefinition(
            name="close_tab",
            category=ActionCategory.KEYBOARD,
            description="Close current tab",
            parameters=[],
            examples=["close tab", "close current tab"],
            aliases=["ctrl_w"]
        ))
        
        self.register(ActionDefinition(
            name="switch_tab",
            category=ActionCategory.KEYBOARD,
            description="Switch to next or previous tab",
            parameters=["direction"],
            examples=["switch tab next", "switch tab previous"],
            aliases=["next_tab", "previous_tab", "ctrl_tab"]
        ))
        
        self.register(ActionDefinition(
            name="refresh",
            category=ActionCategory.KEYBOARD,
            description="Refresh or reload page",
            parameters=[],
            examples=["refresh page", "reload"],
            aliases=["reload", "f5", "ctrl_r"]
        ))
        
        self.register(ActionDefinition(
            name="zoom_in",
            category=ActionCategory.KEYBOARD,
            description="Zoom in",
            parameters=[],
            examples=["zoom in", "increase zoom"],
            aliases=["ctrl_plus", "increase_zoom"]
        ))
        
        self.register(ActionDefinition(
            name="zoom_out",
            category=ActionCategory.KEYBOARD,
            description="Zoom out",
            parameters=[],
            examples=["zoom out", "decrease zoom"],
            aliases=["ctrl_minus", "decrease_zoom"]
        ))
        
        self.register(ActionDefinition(
            name="fullscreen",
            category=ActionCategory.KEYBOARD,
            description="Toggle fullscreen mode",
            parameters=[],
            examples=["fullscreen", "toggle fullscreen"],
            aliases=["f11", "toggle_fullscreen"]
        ))
        
        self.register(ActionDefinition(
            name="read_text",
            category=ActionCategory.VERIFICATION,
            description="Read text from screen or element",
            parameters=["location"],
            examples=["read text from screen", "read selected text"],
            aliases=["get_text", "extract_text", "ocr"]
        ))
        
        self.register(ActionDefinition(
            name="get_clipboard",
            category=ActionCategory.SYSTEM,
            description="Get current clipboard content",
            parameters=[],
            examples=["get clipboard", "read clipboard"],
            aliases=["read_clipboard", "clipboard_content"]
        ))
        
        self.register(ActionDefinition(
            name="set_clipboard",
            category=ActionCategory.SYSTEM,
            description="Set clipboard content",
            parameters=["text"],
            examples=["set clipboard to hello", "copy to clipboard"],
            aliases=["write_clipboard", "clipboard_write"]
        ))
        
        self.register(ActionDefinition(
            name="run_command",
            category=ActionCategory.SYSTEM,
            description="Run a system command",
            parameters=["command"],
            examples=["run command ipconfig", "execute dir"],
            aliases=["execute", "shell", "cmd"]
        ))
        
        self.register(ActionDefinition(
            name="move_mouse",
            category=ActionCategory.MOUSE,
            description="Move mouse to specific position",
            parameters=["x", "y"],
            examples=["move mouse to 100,200", "move cursor to center"],
            aliases=["move_cursor", "mouse_move"]
        ))
        
        self.register(ActionDefinition(
            name="get_mouse_position",
            category=ActionCategory.MOUSE,
            description="Get current mouse position",
            parameters=[],
            examples=["get mouse position", "where is cursor"],
            aliases=["cursor_position", "mouse_location"]
        ))
        
        self.register(ActionDefinition(
            name="take_screenshot_region",
            category=ActionCategory.SYSTEM,
            description="Take screenshot of specific region",
            parameters=["x", "y", "width", "height"],
            examples=["screenshot region 0,0,500,500"],
            aliases=["capture_region", "screenshot_area"]
        ))
    
    def register(self, action: ActionDefinition):
        """Register a new action."""
        self.actions[action.name] = action
        for alias in action.aliases:
            if alias not in self.actions:
                self.actions[alias] = action
    
    def get_action(self, action_name: str) -> Optional[ActionDefinition]:
        """Get action definition by name."""
        # Direct lookup
        if action_name in self.actions:
            return self.actions[action_name]
        
        # Fuzzy search
        for action in self.actions.values():
            if action.matches(action_name):
                return action
        
        return None
    
    def get_all_actions(self) -> List[ActionDefinition]:
        """Get all unique action definitions."""
        seen = set()
        result = []
        for action in self.actions.values():
            if action.name not in seen:
                seen.add(action.name)
                result.append(action)
        return result
    
    def get_actions_by_category(self, category: ActionCategory) -> List[ActionDefinition]:
        """Get all actions in a category."""
        return [a for a in self.get_all_actions() if a.category == category]
    
    def to_prompt_string(
        self,
        *,
        max_per_category: Optional[int] = None,
        include_examples: bool = True,
    ) -> str:
        """Generate a formatted string describing supported actions."""

        lines = ["Available Actions:"]

        for category in ActionCategory:
            actions = self.get_actions_by_category(category)
            if max_per_category is not None:
                actions = actions[:max(0, max_per_category)]

            if not actions:
                continue

            lines.append("")
            lines.append(f"{category.value.upper()} ACTIONS:")

            for action in actions:
                parameter_text = ", ".join(action.parameters) if action.parameters else "None"
                lines.append(f"  - {action.name}: {action.description}")
                lines.append(f"    Parameters: {parameter_text}")

                if include_examples and action.examples:
                    example = action.examples[0]
                    lines.append(f"    Example: {example}")

        if include_examples:
            example_block = self._build_example_block()
            if example_block:
                lines.append("")
                lines.append(example_block)

        return "\n".join(lines)

    def to_compact_prompt_string(self) -> str:
        """Return a concise list of available action names."""

        action_names = sorted(action.name for action in self.get_all_actions())
        return "Available actions (use exact names):\n- " + ", ".join(action_names)

    def _build_example_block(self, max_examples: int = 6) -> str:
        """Build a detailed examples block demonstrating action usage."""

        examples: List[str] = []
        unique_actions = self.get_all_actions()

        for action in unique_actions:
            if not action.examples:
                continue

            example = action.examples[0]
            parameter_text = ", ".join(action.parameters) if action.parameters else "None"
            examples.append(
                "- Action: {name}\n"
                "  Parameters: {params}\n"
                "  Example: {example}".format(
                    name=action.name,
                    params=parameter_text,
                    example=example,
                )
            )

            if len(examples) >= max_examples:
                break

        if not examples:
            return ""

        header = "Detailed Action Examples (JSON-friendly semantics):"
        return "\n".join([header, *examples])


# Global registry instance
action_registry = ActionRegistry()
