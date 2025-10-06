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
    
    def to_prompt_string(self) -> str:
        """Generate a formatted string for prompting."""
        lines = ["Available Actions:\n"]
        
        for category in ActionCategory:
            actions = self.get_actions_by_category(category)
            if actions:
                lines.append(f"\n{category.value.upper()} ACTIONS:")
                for action in actions:
                    lines.append(f"  - {action.name}: {action.description}")
                    if action.examples:
                        lines.append(f"    Examples: {', '.join(action.examples[:2])}")
        
        return "\n".join(lines)


# Global registry instance
action_registry = ActionRegistry()
