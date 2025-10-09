# 🤖 Djenis AI Agent - Intelligent Windows Automation

> An advanced AI-powered automation agent for Windows that understands natural language commands and executes complex multi-step tasks using Google Gemini's vision and reasoning capabilities.

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Platform](https://img.shields.io/badge/platform-Windows-blue)

## 🎯 What is Djenis AI Agent?

Djenis AI Agent is an intelligent automation system that bridges natural language and Windows UI control. Tell it what you want to do in plain English, and it will plan and execute the necessary steps using advanced AI reasoning, computer vision, and precise UI automation.

### Key Capabilities

- **🧠 Natural Language Understanding**: Converts plain English commands into executable automation plans
- **👁️ Visual Intelligence**: Uses Gemini Vision API to analyze screenshots and locate UI elements
- **🎯 Precision Control**: Executes actions using coordinate-based clicking, keyboard shortcuts, and window management
- **🔄 Adaptive Execution**: Self-corrects failures, adjusts strategies, and uses AI feedback to stay on track
- **🖥️ Real-Time Monitoring**: Optional overlay UI shows execution progress, logs, and step details
- **🌍 Cross-Language Support**: Handles UI elements in any language (English, German, Spanish, French, etc.)
- **⚡ 38+ Built-in Actions**: Comprehensive action library for mouse, keyboard, window, and system control

## 🏗️ Architecture Overview

```
User Request (Natural Language)
         ↓
    [Agent Core]
         ├─→ [Gemini Client] → Google Gemini API (Planning & Vision)
         ├─→ [Action Executor] → Translates actions to automation
         ├─→ [UI Engine] → pyautogui, pywinauto, Windows APIs
         └─→ [Overlay UI] → Real-time monitoring (optional)
         
Execution Flow:
1. Parse user request
2. Gemini generates step-by-step plan with reasoning
3. Execute each step with verification
4. If step fails → AI suggests corrections
5. Adapt and continue until goal achieved
```

### Core Components

| Component | Purpose | Technologies |
|-----------|---------|--------------|
| **Enhanced Agent** | Orchestrates execution, manages state, handles failures | Python, dataclasses |
| **Gemini Client** | Interfaces with Google Gemini for planning and vision | google-generativeai, Pillow |
| **Action Executor** | Executes 38+ actions with telemetry | ActionResult, structured logging |
| **UI Automation Engine** | Low-level Windows UI control | pyautogui, pywinauto, win32api |
| **Prompt Builder** | Crafts optimized prompts for Gemini | Chain-of-thought reasoning |
| **Overlay UI** | Real-time monitoring interface | tkinter, transparent overlay |

## ✨ Features

- 🎯 **Natural Language Control**: Execute complex tasks with simple English commands
- 🧠 **AI-Powered Planning**: Gemini generates intelligent, multi-step execution plans with agentic reasoning
- 👁️ **Computer Vision**: Screenshots and visual feedback for adaptive execution
- 🖥️ **Real-Time UI Overlay**: Transparent, always-on-top monitoring interface with toast notifications and step details
- 🔄 **Advanced Error Handling**: Adaptive failure handling with AI consultation and structured retry logic
- 📊 **Structured Telemetry**: ActionResult dataclass with timing, metadata, and execution context
- 🎭 **Agentic Prompting**: Multi-phase reasoning prompts that exploit Gemini's full capabilities
- 🧩 **Context-Rich Prompting**: Injects Windows environment details, action schemas, and fallback strategies with complexity-aware token budgets
- 🪄 **Few-Shot Action Examples**: Supplies Gemini with structured examples of tool usage for higher-precision plans
- 🌍 **AI Window Identification**: Finds windows across languages (Calculator→Rechner/Calculadora/Calculatrice)
- ⚡ **38+ Built-in Actions**: Mouse, keyboard, window management, clipboard, and more
- 🛡️ **Safety Features**: Emergency stop (Ctrl+Shift+Q), timeouts, and screenshot-aware UI
- � **Comprehensive Logging**: Activity logs, step-by-step progress, and error reporting

## 🎮 Demo

```bash
# Simple tasks
python main.py "open calculator"

# Complex multi-step tasks
python main.py "open edge and go to youtube"

# Text editing
python main.py "open notepad, type hello world, save as test.txt"
```

## 🚀 Quick Start

### Prerequisites

- Windows 10/11
- Python 3.8 or higher
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))

### Installation

#### 🚀 Automated Setup (Recommended)

Run the PowerShell setup script to install everything automatically:

```powershell
# Run as Administrator for best results
.\setup.ps1
```

The setup script will:

- ✅ Check Python installation (3.8+)
- ✅ Install all Python dependencies
- ✅ Download and install Tesseract OCR
- ✅ Configure PATH variables
- ✅ Verify installation

#### 🔧 Manual Installation

1. **Clone the repository:**

```bash
git clone https://github.com/yourusername/DjenisAiAgent.git
cd DjenisAiAgent
```

2. **Install Python dependencies:**

```bash
pip install -r requirements.txt
```

3. **Install Tesseract OCR (Optional for OCR features):**

- Download from: https://github.com/UB-Mannheim/tesseract/wiki
- Install to: `C:\Program Files\Tesseract-OCR`
- Add to PATH: `C:\Program Files\Tesseract-OCR`

4. **Configure your API key:**

Create a `.env` file in the project root directory:

```bash
# Create .env file
cd DjenisAiAgent
notepad .env
```

Add your configuration to the `.env` file:

```env
# Google Gemini API Configuration
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.0-flash-exp

# Debug and Logging
DEBUG_MODE=false
LOG_LEVEL=INFO

# Performance Settings
MAX_RETRIES=3
ACTION_DELAY=0.5

# Safety
EMERGENCY_STOP_KEY=ctrl+shift+q

# Features
ENABLE_SCREEN_RECORDING=false
```

**Get your Gemini API key:**
1. Visit https://makersuite.google.com/app/apikey
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key and paste it in the `.env` file

**Alternative: Direct configuration**

If you prefer, you can edit `src/config/config.py` directly, but using `.env` is recommended for security.

### Usage

**Run with UI Overlay (Recommended):**

```bash
python main.py "your task description"
```

The UI overlay shows:

- 🔵 Current status (Ready/Working/Completed/Failed)
- 📋 Active task description
- ⚡ Progress bar with step counter
- 📜 Real-time activity log
- Keyboard shortcuts: ESC to toggle visibility, Double-click to minimize

**Without UI:**

```bash
python main.py "your task description" --no-ui
```

**Examples:**

```bash
# Open applications
python main.py "open calculator"

# Web navigation
python main.py "open edge and go to youtube"

# Text editing
python main.py "open notepad, type hello world, and save as test.txt"

# Complex multi-step tasks
python main.py "open calculator and make 2 + 2"
```

## 🎨 UI Overlay Features

The transparent overlay window provides:

- **Always-on-Top**: Monitors agent activity without interrupting work
- **Screenshot-Aware**: Automatically hides during screenshot actions
- **Toast Notifications**: Floating, auto-dismissing messages for quick feedback (success/info/warning/error)
- **Step Detail Panel**: Shows current step reasoning and insights from AI
- **Draggable**: Click and drag header to reposition
- **Collapsible**: Double-click header to minimize
- **Keyboard Control**: Press ESC to toggle visibility
- **Beautiful Design**: Dark theme with color-coded status indicators

### UI Components

- 🔵 **Status Indicator**: Current status (Ready/Working/Completed/Failed)
- 📋 **Task Description**: Active task being executed
- ⚡ **Progress Bar**: Visual progress with step counter
- 📜 **Activity Log**: Real-time log of actions performed
- 💬 **Toast Messages**: Transient notifications for important events
- 🔍 **Step Details**: Shows reasoning and context for current step

## ⚙️ Configuration

### Configuration Options

The agent can be configured via `.env` file (recommended) or by editing `src/config/config.py`.

**Configuration via .env file (Recommended):**

Create a `.env` file in the project root with these settings:

```env
# Google Gemini API Configuration
GEMINI_API_KEY=your_actual_api_key_here
GEMINI_MODEL=gemini-2.0-flash-exp

# Debug and Logging
DEBUG_MODE=false          # Set to true for verbose logging
LOG_LEVEL=INFO            # Options: DEBUG, INFO, WARNING, ERROR

# Performance Settings
MAX_RETRIES=3             # Number of retry attempts for failed actions
ACTION_DELAY=0.5          # Delay between actions in seconds

# Safety
EMERGENCY_STOP_KEY=ctrl+shift+q  # Keyboard shortcut to cancel execution

# Features
ENABLE_SCREEN_RECORDING=false  # Save before/after screenshots for each action
SCREEN_FOCUS_SIZE=420          # Focus crop dimension (pixels) for AI corrections
SCREEN_FOCUS_HISTORY=3         # How many focus crops to reuse per step
SCREEN_RECORDING_DELAY=0.2     # Delay (s) before capturing after-action screenshot
```

### Available Gemini Models

You can use different Gemini models by changing the `GEMINI_MODEL` setting:

- **`gemini-2.0-flash-exp`** - Latest experimental flash model (fastest, recommended)
- **`gemini-1.5-flash-latest`** - Stable flash model (good balance)
- **`gemini-1.5-pro-latest`** - Most capable model (slower but best reasoning)
- **`gemini-1.0-pro`** - Legacy pro model

**Example:**
```env
GEMINI_MODEL=gemini-2.0-flash-exp
```

### Full Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `GEMINI_API_KEY` | *(required)* | Your Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.0-flash-exp` | Gemini model to use |
| `DEBUG_MODE` | `false` | Enable verbose debug logging |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `MAX_RETRIES` | `3` | Max retry attempts for failed actions |
| `ACTION_DELAY` | `0.5` | Delay between actions (seconds) |
| `EMERGENCY_STOP_KEY` | `ctrl+shift+q` | Keyboard shortcut to cancel execution |
| `ENABLE_SCREEN_RECORDING` | `false` | Save screenshots before/after each action |
| `SCREEN_FOCUS_SIZE` | `420` | Square pixel size for focus crops shared with AI |
| `SCREEN_FOCUS_HISTORY` | `3` | Number of recent focus crops retained for reasoning |
| `SCREEN_RECORDING_DELAY` | `0.2` | Delay after an action before the "after" capture |

### Advanced Configuration

For advanced users, you can modify `src/config/config.py` directly:

```python
# API Configuration
api_timeout: int = 30              # Gemini API timeout (seconds)
screenshot_quality: int = 85        # Screenshot JPEG quality (0-100)

# Safety
emergency_stop_key: str = "ctrl+shift+q"
max_task_duration: int = 300        # Maximum task duration (seconds)

# Paths
logs_dir: Path = Path("logs")       # Directory for log files
screenshots_dir: Path = Path("screenshots")  # Directory for screenshots
```

## 🛡️ Safety Features

- **Emergency Stop**: Press `Ctrl+Shift+Q` to abort execution immediately (configurable via `EMERGENCY_STOP_KEY`)
- **Task Timeout**: Automatic timeout after 300 seconds (configurable)
- **Fail-safe**: Move mouse to screen corners to trigger PyAutoGUI failsafe
- **Exponential Backoff**: Intelligent retry delays (1s, 1.5s, 2.25s)
- **5-Tier Window Focus**: Exact → Regex → Process → Win32 → AI identification

## 🌍 AI-Powered Window Identification

The agent uses Gemini AI as a final fallback to identify windows even when their titles don't match due to language differences:

```
User Request: "focus calculator window"
System Language: German

Standard Methods Fail:
  ❌ Exact Match: "Calculator" ≠ "Rechner"
  ❌ Regex: ".*Calculator.*" doesn't match
  ❌ Process: Multiple instances found
  ❌ Win32 Substring: "calculator" not in "rechner"

AI Fallback Activates:
  🤖 Analyzes all open windows
  🧠 Recognizes "Rechner" = "Calculator" (German)
  ✅ Successfully focuses window!
```

**Supported:** All languages (DE, ES, FR, IT, PT, RU, ZH, JA, KO, etc.). Internals are handled in `src/automation/ui_automation.py` by the `focus_window` routine, which progressively escalates from exact title matches to AI-assisted fallbacks.

## 🏗️ Architecture

The agent uses a modular, layered architecture:

```
┌─────────────────────────────────────────────────────┐
│                  User Interface                      │
│            (CLI + Transparent Overlay)               │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│              Enhanced AI Agent                       │
│  • Task orchestration                                │
│  • Error handling & retries                          │
│  • History tracking                                  │
└────┬───────────────┬──────────────────┬─────────────┘
     │               │                  │
┌────▼─────┐  ┌─────▼──────┐  ┌────────▼──────┐
│ Gemini   │  │  Action    │  │   UI          │
│ Client   │  │  Executor  │  │   Overlay     │
│          │  │            │  │               │
│ • Plans  │  │ • Registry │  │ • Status      │
│ • Vision │  │ • 38+      │  │ • Progress    │
│ • Adapt  │  │   Actions  │  │ • Logs        │
└──────────┘  └─────┬──────┘  └───────────────┘
                    │
          ┌─────────▼─────────┐
          │  UI Automation    │
          │  • PyAutoGUI      │
          │  • PyWinAuto      │
          │  • Win32 API      │
          │  • Clipboard      │
          └───────────────────┘
```

### 📁 Project Structure

```
DjenisAiAgent/
├── main.py                       # Entry point
├── requirements.txt              # Dependencies
├── setup.ps1                     # Automated setup script
├── .env.example                  # Environment template
├── README.md                     # This file
├── LICENSE                       # MIT License
├── CONTRIBUTING.md               # Contribution guidelines
├── logs/                         # Log files
├── screenshots/                  # Screenshot storage
└── src/                          # Source code
    ├── __init__.py
    ├── config/                   # Configuration
    │   ├── __init__.py
    │   └── config.py            # Settings and API keys
    ├── utils/                    # Utilities
    │   ├── __init__.py
    │   └── logger.py            # Logging system
    ├── automation/               # Low-level automation
    │   ├── __init__.py
    │   └── ui_automation.py     # PyAutoGUI, PyWinAuto, Win32 API
    ├── core/                     # Core agent logic
    │   ├── __init__.py
    │   ├── agent.py             # Main orchestration with telemetry
    │   ├── gemini_client.py     # AI planning & vision
    │   ├── executor.py          # Action execution with ActionResult
    │   ├── actions.py           # Action registry (38+ actions)
    │   ├── prompts.py           # Agentic prompt templates
    │   └── ui_overlay.py        # Monitoring UI with toasts
    └── tests/                    # Test suite
        ├── __init__.py
        ├── test_agent.py        # Agent tests
        ├── test_ai_window_focus.py  # Window identification tests
        └── test_setup.py        # Setup verification
```

## �️ Architecture & Recent Improvements

### Structured Telemetry System

The agent now uses a structured telemetry system for better tracking and debugging:

```python
@dataclass
class ActionResult:
    """Complete execution result with timing and metadata."""
    success: bool
    message: str
    started_at: datetime
    finished_at: datetime
    duration: float
    metadata: Dict[str, Any]
    action_suggestion: Optional[str] = None  # Suggests similar actions for unknown commands
```

### Execution Context Tracking

Each step maintains its own execution context for adaptive behavior:

```python
@dataclass
class StepContext:
    """Tracks state and history for a single execution step."""
    step: Dict[str, Any]
    retry_count: int = 0
    last_error: Optional[str] = None
    reasoning_notes: List[str] = field(default_factory=list)
    verification_result: Optional[Dict[str, Any]] = None
    status: StepStatus = StepStatus.PENDING
```

### Adaptive Failure Handling

The agent now features intelligent failure recovery:

1. **Structured Retries**: Tracks attempts with exponential backoff
2. **AI Consultation**: Asks Gemini for corrective strategies after failures
3. **Corrective Steps**: Can inject new steps based on AI recommendations
4. **Post-Success Verification**: Validates task completion after successful execution
5. **Partial Success Detection**: Recognizes and reports partial completions

### Enhanced Agentic Prompting

All prompts now leverage multi-phase reasoning for better decision-making:

#### Task Planning
- **UNDERSTAND** → Analyze task requirements and constraints
- **STRATEGIZE** → Plan action sequence with failure modes
- **VALIDATE** → Verify plan completeness and alternatives
- **REFLECT** → Self-critique and adjust

#### Screen Analysis
- **SYSTEMATIC SCAN** → Identify all UI elements methodically
- **CONTEXT AWARENESS** → Understand element relationships
- **ACTIONABLE INSIGHTS** → Extract automation-relevant information

#### Element Location
- **MULTI-STRATEGY** → Try multiple location methods
- **SPATIAL REASONING** → Understand element positioning
- **CONFIDENCE SCORING** → Rate location certainty

#### Verification
- **COMPREHENSIVE COMPARISON** → Before/after state analysis
- **PARTIAL SUCCESS DETECTION** → Recognize incomplete outcomes
- **NEXT-STEP RECOMMENDATIONS** → Suggest recovery actions

#### Next Action Decision
- **GOAL DECOMPOSITION** → Break down complex objectives
- **STATE ASSESSMENT** → Evaluate current progress
- **RISK EVALUATION** → Anticipate potential failures
- **ALTERNATIVE PATHS** → Plan fallback strategies

## �🎯 How It Works

1. **📝 Understanding**: Gemini parses your natural language request
2. **🧠 Planning**: AI generates a detailed, multi-step execution plan
3. **⚡ Execution**: Agent performs actions using:
   - Computer vision (Gemini Vision API)
   - OCR text recognition (optional, requires Tesseract)
   - Windows UI Automation (PyWinAuto)
   - Direct input simulation (PyAutoGUI)
   - Win32 API fallbacks
4. **🔄 Adaptation**: Real-time feedback and error recovery with exponential backoff
5. **📊 Monitoring**: Live updates via transparent overlay UI

### Action Registry (38+ Actions)

**Window Management:**

- `open_application`, `close_application`, `focus_window`, `minimize_window`, `maximize_window`, `resize_window`, `move_window`, `get_window_position`, `get_window_size`

**Mouse Control:**

- `click`, `double_click`, `right_click`, `move_to`, `drag`, `scroll`, `scroll_up`, `scroll_down`, `get_mouse_position`, `get_pixel_color`

**Keyboard Input:**

- `type_text`, `press_key`, `hotkey`, `press_enter`, `press_tab`, `press_backspace`, `press_escape`, `press_delete`

**Clipboard:**

- `copy`, `paste`, `cut`, `copy_text`, `paste_text`, `get_clipboard`, `set_clipboard`

**Screen & Vision:**

- `take_screenshot`, `take_screenshot_region`, `read_text`, `find_element`, `find_image`

**Navigation:**

- `navigate_to`, `go_back`, `go_forward`, `refresh`, `zoom_in`, `zoom_out`, `zoom_reset`, `open_new_tab`, `close_tab`, `switch_tab`

**System:**

- `wait`, `get_screen_info`, `verify_action`

4. **Verification**: Confirms each step and the final result
5. **Adaptation**: Retries failed steps with alternative approaches

## Supported Actions

- Open applications
- Click elements (buttons, links, icons)
- Type text
- Press keyboard shortcuts
- Scroll pages
- Drag and drop
- Focus windows
- Read screen content
- Verify results

## Limitations

- Requires visible UI elements (can't interact with minimized windows)
- Performance depends on screen resolution and application responsiveness
- Some applications may have anti-automation measures
- API costs apply for Gemini usage

## Troubleshooting

**Agent can't find elements:**

- Ensure the target window is visible and not minimized
- Try making the target element larger or more prominent
- Check screen resolution settings

**Actions are too fast/slow:**

- Adjust `ACTION_DELAY` in `.env`
- Use `--debug` flag for detailed logs

**API errors:**

- Verify your Gemini API key is valid
- Check your API quota and billing
- Ensure internet connectivity

## Development

```bash
# Install in development mode
pip install -e .

# Run with debug logging
python main.py --debug "your command"

# Check logs
ls logs/
```

## License

MIT License - see [LICENSE](LICENSE) file for details

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines

## Disclaimer

This tool automates UI interactions on your computer. Use responsibly and at your own risk. Always review what the agent will do before allowing execution on sensitive systems or data.

---

**Made with ❤️ using Google Gemini**
