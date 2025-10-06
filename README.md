# AI Agent for Windows UI Automation

An intelligent AI agent that uses Google Gemini and the Model Context Protocol (MCP) to perform automated UI tasks on Windows through natural language commands.

## Features

- 🤖 **Natural Language Control**: Describe tasks in plain English
- 🎯 **Smart Task Planning**: AI-powered step-by-step execution plans
- 👁️ **Computer Vision**: Uses Gemini's vision capabilities to understand screens
- 🔄 **Adaptive Execution**: Automatically retries and adjusts based on feedback
- 🛡️ **Safe Operation**: Emergency stop hotkey and timeout protection
- 📊 **Real-time Feedback**: Visual progress indicators and logging
- ⚡ **High Performance**: Optimized for speed and precision

## Quick Start

### Prerequisites

- Windows 10/11
- Python 3.8+
- Google Gemini API key

### Installation

1. Clone the repository:

```bash
git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
cd DjenisAiAgent
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure your API key:

```bash
# Copy the example .env file
copy .env.example .env

# Edit .env and add your Gemini API key
GEMINI_API_KEY=your_api_key_here
```

### Usage

**Interactive Mode:**

```bash
python main.py --interactive
```

**Single Command:**

```bash
python main.py "open notepad and type hello world"
```

**Examples:**

```bash
# Open applications
python main.py "open calculator"

# Perform calculations
python main.py "open calculator and calculate 25 times 4"

# Web browsing
python main.py "open chrome and search for python tutorials"

# File operations
python main.py "open notepad, type hello world, and save as test.txt"

# Multiple steps
python main.py "open word, create a new document, and type a letter"
```

## Configuration

Edit the `.env` file to customize behavior:

```ini
# API Configuration
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-flash-latest

# Performance
MAX_RETRIES=3
ACTION_DELAY=0.5

# Debugging
DEBUG_MODE=false
LOG_LEVEL=INFO
```

## Safety Features

- **Emergency Stop**: Press `Ctrl+Shift+Q` to abort execution
- **Task Timeout**: Automatic timeout after 300 seconds (configurable)
- **Fail-safe**: Move mouse to screen corner to stop PyAutoGUI
- **Logging**: All actions are logged for review

## Architecture

```
┌──────────────┐
│ User Request │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Gemini AI Brain  │ ◄── Task planning & reasoning
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Execution Engine │ ◄── Step-by-step execution
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ UI Automation    │ ◄── Mouse, keyboard, vision
└──────────────────┘
```

### Core Components

- **`agent.py`**: Main orchestration and task execution
- **`gemini_client.py`**: Gemini API integration for AI reasoning
- **`ui_automation.py`**: Low-level UI control (mouse, keyboard, vision)
- **`config.py`**: Configuration management
- **`logger.py`**: Logging and output formatting

## How It Works

1. **Understanding**: The agent uses Gemini to parse your natural language request
2. **Planning**: Creates a detailed step-by-step execution plan
3. **Execution**: Performs UI automation using multiple techniques:
   - Text recognition (OCR)
   - Image matching
   - AI vision for element location
   - Windows UI Automation API
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
