# DjenisAiAgent - MCP Server Agent

## Overview

DjenisAiAgent is a Model Context Protocol (MCP) server agent designed to automate UI tasks on Windows 11 (with Linux support planned) using Google's Gemini AI. The agent can capture the screen, analyze UI elements, and execute actions based on AI-powered decisions.

This project combines computer vision, AI decision making, and UI automation to create an intelligent assistant that can perform various tasks on your computer by "seeing" the screen and controlling the mouse and keyboard.

## Features

- **Screen Analysis**: Captures and analyzes screen content using computer vision techniques
- **AI Decision Making**: Uses Gemini AI to interpret screen content and decide actions
- **UI Automation**: Controls mouse and keyboard to interact with applications
- **MCP Integration**: Implements the Model Context Protocol for standardized AI agent communication
- **Modular Architecture**: Cleanly separated components for perception, memory, planning, and tools
- **Extensible Tools**: Framework for adding new capabilities and integrations
- **User Interface**: Simple GUI for sending commands and viewing agent status

## Project Structure

```
DjenisAiAgent/
├── src/                  # Source code
│   ├── agent_core.py     # Main agent implementation
│   ├── config.py         # Configuration management
│   ├── main.py           # Application entry point
│   ├── abstractions/     # Abstract interfaces
│   ├── gemini/           # Gemini AI integration
│   ├── memory/           # Agent memory components
│   ├── perception/       # Screen analysis and UI detection
│   ├── planning/         # Task planning and execution
│   ├── tools/            # Action tools (input, MCP, etc.)
│   └── ui/               # User interface components
├── tests/                # Unit and integration tests
├── config/               # Configuration files
│   ├── default_config.json
│   ├── credentials.json.template
│   └── prompt_templates.json
├── data/                 # Runtime data (created on first run)
│   ├── screenshots/      # Captured screenshots
│   └── task_memory/      # Persisted task data
├── requirements.txt      # Dependencies
└── README.md             # This file
```

## Requirements

- Python 3.9+
- Windows 11 (for Windows UI automation)
- Google Gemini API key
- Tesseract OCR (optional, for text recognition)
- Dependencies listed in requirements.txt

## Setup Instructions

1. Clone the repository:

   ```
   git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
   cd DjenisAiAgent
   ```

2. Create and activate a virtual environment:

   ```
   python -m venv venv
   .\venv\Scripts\activate  # Windows
   source venv/bin/activate  # Linux/Mac
   ```

3. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

4. Set up your Gemini API key:

   - Copy `config/credentials.json.template` to `config/credentials.json`
   - Add your Gemini API key to the file
   - Alternatively, set the `GEMINI_API_KEY` environment variable

5. (Optional) Install Tesseract OCR for text recognition:
   - Download and install from https://github.com/UB-Mannheim/tesseract/wiki
   - Add Tesseract to your PATH

## Usage

1. Start the agent:

   ```
   python -m src.main
   ```

2. For debugging mode:

   ```
   python -m src.main --debug
   ```

3. To use a custom configuration:
   ```
   python -m src.main --config path/to/config.json
   ```

## Configuration

The agent can be configured via JSON files in the `config` directory:

- `default_config.json`: Default settings
- `credentials.json`: API keys and other secrets
- `prompt_templates.json`: Templates for AI prompts

Key configuration options:

- `general.debug_mode`: Enable debug logging
- `gemini.api_key`: Gemini API key (if not using environment variable)
- `gemini.model_name`: Gemini model to use
- `tools.input.safety_delay`: Delay between input actions for safety

## Development

### Running Tests

```
python -m pytest tests/
```

### Adding New Tools

1. Create a new tool class in `src/tools/`
2. Register action handlers in `AgentCore._register_actions()`
3. Update prompt templates to include new actions

## License

[MIT License](LICENSE)

## Acknowledgments

- Google Gemini for AI capabilities
- OpenCV for computer vision functionality
- PyAutoGUI for UI automation

## Future Plans

- Linux support
- More sophisticated task planning
- Advanced UI element detection
- Custom action tools
- Web browser integration

2. Navigate to the project directory.
3. Install the required dependencies using the command:
   ```
   pip install -r requirements.txt
   ```
4. Configure the agent by editing the `config/default_config.json` file and filling in the necessary credentials in `config/credentials.json.template`.

## Usage

To run the MCP Server Agent in headless mode:

```
python src/main.py
```

To run with the graphical user interface:

```
python launch_ui.py
```

### User Interface Commands

The GUI provides an interactive way to control the agent:

- Type any text command in the input field and press Enter to send a request to the agent
- Use the "Pausa" button to pause/resume agent execution
- Use the "Screenshot" button to take and analyze a screenshot
- Special commands:
  - `exit` or `quit`: Close the application
  - `pause`: Toggle pause state
  - `screenshot`: Take a screenshot

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
