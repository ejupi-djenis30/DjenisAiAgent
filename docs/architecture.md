# Architecture Overview

This document provides a high-level overview of the DjenisAiAgent architecture and how its components work together.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                           │
│  (Tkinter GUI / CLI)                                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Core                                │
│  - Task Coordination                                            │
│  - State Management                                             │
│  - Component Integration                                        │
└─┬───────────────────────────────────────────────────────────┬───┘
  │                                                             │
  ├──────────────┬──────────────┬──────────────┬───────────────┤
  ▼              ▼              ▼              ▼               ▼
┌──────┐    ┌────────┐    ┌─────────┐    ┌────────┐    ┌────────┐
│Memory│    │Percept.│    │Gemini AI│    │Planning│    │ Tools  │
│System│    │ Engine │    │ Client  │    │ System │    │ Engine │
└──────┘    └────────┘    └─────────┘    └────────┘    └────────┘
```

## Core Components

### 1. Agent Core (`agent_core.py`)

The central orchestrator that coordinates all other components.

**Responsibilities:**

- Initialize and manage component lifecycle
- Coordinate task execution flow
- Maintain agent state (running, paused, stopped)
- Handle errors and recovery
- Provide status updates to UI

**Key Methods:**

- `execute_task()`: Main task execution loop
- `pause()` / `resume()`: Control agent execution
- `get_status()`: Report current state

### 2. Perception Engine (`perception/`)

Analyzes the screen to understand the current UI state.

**Components:**

- **Screen Capture** (`win11_capture.py`): Takes screenshots
- **Screen Analyzer** (`screen_analyzer.py`): Processes images
- **Enhanced Analyzer** (`enhanced_screen_analyzer.py`): Advanced analysis

**Capabilities:**

- Screenshot capture
- UI element detection
- OCR text recognition
- Pattern matching
- Layout analysis

### 3. Gemini AI Client (`gemini/`)

Interfaces with Google's Gemini AI for intelligent decision-making.

**Components:**

- **Client** (`client.py`): API communication
- **Prompt Manager** (`prompt_manager.py`): Prompt templates and formatting

**Functions:**

- Interpret user commands
- Analyze screenshots
- Make action decisions
- Generate natural language responses

### 4. Memory System (`memory/`)

Manages different types of memory for context-aware behavior.

**Types:**

- **Short-term Memory** (`short_term_memory.py`): Recent actions and observations
- **Task Memory** (`task_memory.py`): Task history and results
- **UI Memory** (`ui_memory.py`): Learned UI patterns and element locations

**Benefits:**

- Faster element recognition
- Context-aware decisions
- Learning from past interactions

### 5. Planning System (`planning/`)

Breaks down complex tasks into executable steps.

**Components:**

- **Planner** (`planner.py`): Task decomposition logic
- **Schemas** (`schemas.py`): Task and action definitions

**Process:**

1. Parse user command
2. Break into sub-tasks
3. Prioritize actions
4. Generate execution plan

### 6. Tools Engine (`tools/`)

Provides capabilities for interacting with the system.

**Available Tools:**

- **GUI Tool** (`gui_tool.py`): Click, type, scroll
- **Input Controller** (`win11_input.py`): Low-level input
- **File System Tool** (`file_system_tool.py`): File operations
- **PowerShell Tool** (`powershell_tool.py`): Run commands
- **Task Completed Tool** (`task_completed_tool.py`): Signal completion

### 7. User Interface (`ui/`)

Provides user interaction capabilities.

**Components:**

- **Agent UI** (`agent_ui.py`): Main GUI window

**Features:**

- Start/stop/pause controls
- Task input
- Status monitoring
- Screenshot preview
- Log viewing

## Data Flow

### Typical Task Execution Flow:

1. **Task Input**

   ```
   User → UI → Agent Core
   ```

2. **Understanding**

   ```
   Agent Core → Gemini AI Client
   ↓
   Interprets task and creates plan
   ```

3. **Perception**

   ```
   Agent Core → Perception Engine
   ↓
   Captures and analyzes screen
   ```

4. **Planning**

   ```
   AI Response + Screen Analysis → Planning System
   ↓
   Generates action sequence
   ```

5. **Execution**

   ```
   Planning System → Tools Engine
   ↓
   Performs actions (click, type, etc.)
   ```

6. **Memory Update**

   ```
   Action Results → Memory System
   ↓
   Updates context for future decisions
   ```

7. **Status Report**
   ```
   Agent Core → UI
   ↓
   Shows progress and results
   ```

## Key Design Patterns

### 1. Component-Based Architecture

Each major feature is isolated in its own module with clear interfaces.

### 2. Abstraction Layers

Abstract interfaces (`abstractions/`) allow for platform-specific implementations.

### 3. Configuration-Driven

Behavior is controlled through JSON configuration files.

### 4. Event-Driven UI

The GUI uses threading to remain responsive during long operations.

### 5. Memory-Enhanced Processing

Past interactions inform future decisions through the memory system.

## Extensibility

The architecture supports extension through:

1. **New Tools**: Add tools to the `tools/` directory
2. **Custom Analyzers**: Implement new perception methods
3. **Memory Types**: Add specialized memory components
4. **UI Extensions**: Modify or extend the interface
5. **Platform Support**: Implement abstractions for other platforms

## Configuration

The system is configured through:

- `config/default_config.json`: General settings
- `config/credentials.json`: API keys and secrets
- `config/prompt_templates.json`: AI prompt templates
- `data/ui_patterns.json`: UI element patterns

## Error Handling

The system employs multiple error handling strategies:

1. **Graceful Degradation**: Continue with limited functionality
2. **Retry Logic**: Attempt failed operations again
3. **Fallback Mechanisms**: Use alternative approaches
4. **Error Logging**: Detailed logs for debugging
5. **User Notification**: Clear error messages in UI

## Performance Considerations

- **Lazy Loading**: Components initialized only when needed
- **Caching**: Screen analyses and patterns cached in memory
- **Async Operations**: Non-blocking UI and API calls
- **Resource Management**: Proper cleanup of screenshots and temporary files

## Security

- **Credential Isolation**: API keys in separate gitignored file
- **Input Validation**: Sanitize user commands
- **Limited Permissions**: Runs with user privileges only
- **Audit Logging**: All actions logged for review

## Future Enhancements

Planned architectural improvements:

1. Plugin system for third-party extensions
2. Distributed execution for multi-machine setups
3. Web-based UI alternative
4. Advanced ML models for element detection
5. Cross-platform support (macOS, Linux)
