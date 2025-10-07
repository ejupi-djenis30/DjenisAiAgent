# AI Agent for Windows UI Automation 🤖

An intelligent AI agent powered by Google Gemini that automates Windows UI tasks through natural language commands. Features real-time monitoring UI, advanced error handling, and 38+ built-in actions.

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## ✨ Features

- 🎯 **Natural Language Control**: Execute complex tasks with simple English commands
- 🧠 **AI-Powered Planning**: Gemini generates intelligent, multi-step execution plans
- 👁️ **Computer Vision**: Screenshots and visual feedback for adaptive execution
- 🖥️ **Real-Time UI Overlay**: Transparent, always-on-top monitoring interface
- 🔄 **Advanced Error Handling**: 3-tier fallback system with exponential backoff
- ⚡ **38+ Built-in Actions**: Mouse, keyboard, window management, clipboard, and more
- 🛡️ **Safety Features**: Emergency stop (Ctrl+Shift+Q), timeouts, and screenshot-aware UI
- 📊 **Comprehensive Logging**: Activity logs, step-by-step progress, and error reporting

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

Edit `config.py` and set your Gemini API key:

```python
GEMINI_API_KEY = "your_api_key_here"
```

Get your API key from: https://makersuite.google.com/app/apikey

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
- **Draggable**: Click and drag header to reposition
- **Collapsible**: Double-click header to minimize
- **Keyboard Control**: Press ESC to toggle visibility
- **Beautiful Design**: Dark theme with color-coded status indicators

## ⚙️ Configuration

Edit `config.py` to customize:

```python
# Gemini API
GEMINI_API_KEY = "your_key_here"
GEMINI_MODEL = "gemini-flash-latest"

# Performance
max_retries = 3
action_delay = 0.5
max_task_duration = 300  # seconds

# Features
enable_screen_recording = True
enable_ocr = False  # Requires Tesseract
```

## 🛡️ Safety Features

- **Emergency Stop**: Press `Ctrl+Shift+Q` to abort execution immediately
- **Task Timeout**: Automatic timeout after 300 seconds (configurable)
- **Fail-safe**: Move mouse to screen corners to trigger PyAutoGUI failsafe
- **Exponential Backoff**: Intelligent retry delays (1s, 1.5s, 2.25s)
- **3-Tier Window Focus**: Exact match → Regex → Process name fallback

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
├── src/
│   └── core/
│       ├── agent.py              # Main orchestration
│       ├── gemini_client.py      # AI planning & vision
│       ├── executor.py           # Action execution
│       ├── actions.py            # Action registry (38+ actions)
│       ├── prompts.py            # Prompt templates
│       └── ui_overlay.py         # Monitoring UI
├── ui_automation.py              # Low-level automation
├── config.py                     # Configuration
├── logger.py                     # Logging system
├── main.py                       # Entry point
└── requirements.txt              # Dependencies
```

## 🎯 How It Works

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
