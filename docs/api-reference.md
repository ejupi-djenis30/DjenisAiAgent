# 📚 API Reference

## Core Components

### AgentCore

Main orchestrator that coordinates all agent components.

```python
from src.agent_core import AgentCore

# Initialize agent
config = {
    "general": {"debug_mode": False},
    "gemini": {"api_key": "your-key"},
    "perception": {"ocr_enabled": True}
}
agent = AgentCore(config)

# Execute task
result = agent.execute_task("Open Calculator")

# Control agent
agent.pause()
agent.resume()
agent.stop()

# Get status
status = agent.get_status()
```

#### Methods

- `__init__(config: Dict[str, Any])` - Initialize agent with configuration
- `execute_task(task: str) -> Dict[str, Any]` - Execute a natural language task
- `pause()` - Pause agent execution
- `resume()` - Resume agent execution
- `stop()` - Stop agent completely
- `get_status() -> Dict[str, str]` - Get current agent status

### Configuration Manager

```python
from src.config import Config

# Load configuration
config = Config("config/default_config.json")
settings = config.settings

# Get specific setting
api_key = config.get("gemini.api_key")

# Update setting
config.update("perception.ocr_enabled", False)

# Save configuration
config.save()
```

## Perception System

### Screen Capture

```python
from src.perception.win11_capture import Win11Capture

capture = Win11Capture()

# Capture screenshot
screenshot = capture.capture_screen()

# Capture specific region
region = capture.capture_region(x=100, y=100, width=500, height=400)

# Save screenshot
capture.save_screenshot(screenshot, "screenshot.png")
```

### Screen Analyzer

```python
from src.perception.screen_analyzer import ScreenAnalyzer

analyzer = ScreenAnalyzer(config)

# Analyze screenshot
analysis = analyzer.analyze(screenshot)

# Detect UI elements
elements = analyzer.detect_elements(screenshot)

# Perform OCR
text = analyzer.extract_text(screenshot)
```

## Memory System

### Short-term Memory

```python
from src.memory.short_term_memory import ShortTermMemory

memory = ShortTermMemory(max_items=100)

# Store observation
memory.add("button_location", {"x": 100, "y": 200})

# Retrieve
location = memory.get("button_location")

# Check if exists
if memory.has("button_location"):
    print("Found in memory")

# Clear memory
memory.clear()
```

### Task Memory

```python
from src.memory.task_memory import TaskMemory

task_memory = TaskMemory("data/task_memory")

# Store task result
task_memory.store_task({
    "task": "Open Calculator",
    "success": True,
    "steps": ["clicked_start", "clicked_calculator"],
    "timestamp": "2025-10-02T10:30:00"
})

# Retrieve recent tasks
recent = task_memory.get_recent(limit=10)

# Search tasks
calculator_tasks = task_memory.search("Calculator")
```

## Tools System

### GUI Tool

```python
from src.tools.gui_tool import GUITool

gui = GUITool(config)

# Click at coordinates
gui.click(x=500, y=300)

# Double click
gui.double_click(x=500, y=300)

# Right click
gui.right_click(x=500, y=300)

# Type text
gui.type_text("Hello World")

# Press key
gui.press_key("enter")

# Scroll
gui.scroll(direction="down", amount=3)
```

### File System Tool

```python
from src.tools.file_system_tool import FileSystemTool

fs = FileSystemTool()

# Read file
content = fs.read_file("path/to/file.txt")

# Write file
fs.write_file("path/to/file.txt", "content")

# List directory
files = fs.list_directory("path/to/dir")

# Check if exists
if fs.exists("path/to/file.txt"):
    print("File exists")
```

## Gemini AI Client

```python
from src.gemini.client import GeminiClient

client = GeminiClient(api_key="your-key")

# Send text prompt
response = client.generate_text("Explain this screenshot")

# Send image with prompt
response = client.analyze_image(
    image=screenshot,
    prompt="What UI elements do you see?"
)

# Get structured response
action = client.get_action_decision(
    screenshot=screenshot,
    task="Open Calculator",
    context={"previous_actions": ["clicked_start"]}
)
```

## Planning System

```python
from src.planning.planner import Planner

planner = Planner(config)

# Create task plan
plan = planner.create_plan("Open Notepad and type Hello")

# Execute plan
results = planner.execute_plan(plan)

# Get next action
action = planner.get_next_action(plan, current_state)
```

## Utility Functions

### Logging

```python
import logging

logger = logging.getLogger("AgentCore")

logger.info("Information message")
logger.warning("Warning message")
logger.error("Error message")
logger.debug("Debug message")
```

### Error Handling

```python
from src.exceptions import (
    AgentError,
    PerceptionError,
    ActionError,
    ConfigurationError
)

try:
    agent.execute_task("task")
except PerceptionError as e:
    logger.error(f"Perception failed: {e}")
except ActionError as e:
    logger.error(f"Action failed: {e}")
except AgentError as e:
    logger.error(f"Agent error: {e}")
```

## Configuration Options

### General Settings

```python
{
    "general": {
        "debug_mode": false,        # Enable debug logging
        "log_level": "INFO",        # Logging level
        "max_retries": 3            # Max retry attempts
    }
}
```

### Perception Settings

```python
{
    "perception": {
        "screenshot_dir": "data/screenshots",
        "ocr_enabled": true,
        "ui_detection_enabled": true,
        "element_confidence_threshold": 0.8,
        "screenshot_quality": 95
    }
}
```

### Gemini Settings

```python
{
    "gemini": {
        "api_key": "your-key",
        "model_name": "gemini-pro-vision",
        "temperature": 0.7,
        "max_tokens": 2048,
        "timeout": 30
    }
}
```

### Memory Settings

```python
{
    "memory": {
        "max_items": 100,
        "expiry_seconds": 3600,
        "task_storage_dir": "data/task_memory",
        "ui_storage_dir": "data/ui_memory"
    }
}
```

### Tool Settings

```python
{
    "tools": {
        "input": {
            "safety_delay": 0.1,     # Delay between actions (seconds)
            "typing_speed": 0.05     # Delay between keystrokes
        }
    }
}
```

## Events and Callbacks

```python
# Register event callbacks
agent.on("task_started", lambda task: print(f"Started: {task}"))
agent.on("task_completed", lambda result: print(f"Done: {result}"))
agent.on("error", lambda error: print(f"Error: {error}"))

# Unregister callback
agent.off("task_started", callback_function)
```

## Best Practices

### Configuration Management

1. Use environment variables for sensitive data
2. Keep configuration files in gitignored locations
3. Use configuration templates for distribution
4. Validate configuration on startup

### Error Handling

1. Always use try-except blocks
2. Log errors with context
3. Provide user-friendly error messages
4. Implement graceful degradation

### Performance

1. Cache frequently accessed data
2. Use lazy loading for heavy components
3. Implement request throttling for API calls
4. Clean up resources properly

### Security

1. Never log sensitive data
2. Validate all user inputs
3. Use parameterized queries
4. Keep dependencies updated

## Examples

### Complete Usage Example

```python
import logging
from src.agent_core import AgentCore
from src.config import Config

# Setup logging
logging.basicConfig(level=logging.INFO)

# Load configuration
config = Config("config/default_config.json")

# Initialize agent
agent = AgentCore(config.settings)

# Register callbacks
agent.on("task_completed", lambda r: print(f"✓ Task done: {r}"))
agent.on("error", lambda e: print(f"✗ Error: {e}"))

# Execute tasks
try:
    result1 = agent.execute_task("Take a screenshot")
    result2 = agent.execute_task("Open Calculator")
    result3 = agent.execute_task("Calculate 25 * 4")

    print("All tasks completed successfully!")
except Exception as e:
    print(f"Task execution failed: {e}")
finally:
    agent.stop()
```

### Custom Tool Example

```python
from src.tools.base_tool import BaseTool

class CustomTool(BaseTool):
    """Custom tool for specific actions."""

    def __init__(self, config):
        super().__init__(config)
        self.name = "custom_tool"

    def execute(self, action: str, params: Dict) -> Dict:
        """Execute custom action."""
        if action == "custom_action":
            return self._custom_action(params)
        return {"success": False, "error": "Unknown action"}

    def _custom_action(self, params: Dict) -> Dict:
        """Implement your custom action."""
        # Your implementation here
        return {"success": True, "result": "Done"}

# Register custom tool
agent.register_tool("custom", CustomTool(config))

# Use custom tool
result = agent.execute_tool("custom", "custom_action", {"param": "value"})
```

For more examples, see the `tests/` directory in the repository.
