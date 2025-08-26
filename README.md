# DjenisAiAgent - Intelligent UI Automation Agent

## Overview

DjenisAiAgent is an advanced automation assistant that uses Google's Gemini AI to interact with user interfaces on Windows 11. The agent captures screenshots, analyzes UI elements using computer vision, and performs actions based on AI-driven decisions.

By combining computer vision, artificial intelligence, and UI automation, DjenisAiAgent can navigate applications, recognize interface elements, and execute tasks autonomously - essentially "seeing" your screen and controlling the mouse and keyboard like a human would.

## Key Features

- **AI-Powered Interface Analysis**: Uses Gemini AI models to understand screen content and context
- **Computer Vision**: Detects buttons, text fields, and other UI elements using advanced image processing
- **Optical Character Recognition (OCR)**: Reads text from screen elements using Tesseract
- **UI Pattern Recognition**: Identifies common UI components using visual pattern matching
- **Task Memory**: Remembers previous actions and context for better decision making
- **Graphical User Interface**: Easy-to-use control panel for monitoring and commanding the agent
- **Extensible Architecture**: Modular design allows for adding new capabilities and integrations

## Project Structure

```
DjenisAiAgent/
├── src/                      # Source code
│   ├── agent_core.py         # Main agent implementation
│   ├── config.py             # Configuration management
│   ├── main.py               # Application entry point
│   ├── abstractions/         # Abstract interfaces
│   ├── gemini/               # Gemini AI integration
│   ├── memory/               # Memory management components
│   ├── perception/           # Screen analysis and UI detection
│   ├── planning/             # Task planning and execution
│   ├── tools/                # Action tools (input, automation)
│   └── ui/                   # User interface components
├── tests/                    # Unit and integration tests
├── config/                   # Configuration files
│   ├── default_config.json         # Main configuration (without sensitive data)
│   ├── default_config.json.template # Template for configuration
│   ├── credentials.json           # User's private API keys (git-ignored)
│   ├── credentials.json.template  # Template for credentials
│   └── prompt_templates.json      # AI prompt structures
├── data/                     # Runtime data (created on first run)
│   ├── screenshots/          # Captured screenshots
│   ├── task_memory/          # Persisted task data
│   ├── ui_memory/            # UI interaction history
│   └── ui_patterns.json      # UI element pattern definitions
├── launch_ui.py              # Start the graphical interface
├── requirements.txt          # Python dependencies
└── README.md                 # This documentation
```

## Requirements

- **Python 3.9+**
- **Windows 11** (required for Windows UI automation features)
- **Google Gemini API Key** (for AI capabilities)
- **Tesseract OCR** (optional, for text recognition in screenshots)

## Installation

### 1. Set Up Python Environment

```powershell
# Clone the repository
git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
cd DjenisAiAgent

# Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys

For security reasons, API keys are not stored in the main configuration files that might be committed to the repository. You have two options:

**Option A: Using credentials.json**

```powershell
# Copy the template
Copy-Item config/credentials.json.template config/credentials.json

# Edit the file and add your API key
# The file should look like:
# {
#   "username": "",
#   "password": "",
#   "api_key": "YOUR_GEMINI_API_KEY_HERE",
#   "token": ""
# }
```

**Option B: Using Environment Variables**

```powershell
# PowerShell
$env:GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# Command Prompt
set GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
```

### 3. Install Tesseract OCR (Optional)

For text recognition capabilities:

1. Download Tesseract OCR from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)
2. During installation, ensure "Add to PATH" is selected
3. Verify installation:
   ```powershell
   tesseract --version
   ```

## Usage

### Running the Agent

There are two main ways to run the DjenisAiAgent:

#### 1. With the Graphical User Interface (Recommended)

```powershell
# Run the UI version
python launch_ui.py
```

This launches a user-friendly interface where you can:

- Monitor the agent's status and activities
- Send commands via the text input
- Take screenshots for analysis
- Pause/resume agent operations

#### 2. Command Line Mode

```powershell
# Basic usage
python src/main.py

# With debug mode enabled
python src/main.py --debug

# With a custom configuration file
python src/main.py --config path/to/custom/config.json
```

### Special Commands

When using the UI, you can type these commands:

- `screenshot` - Capture the screen and analyze it
- `pause` - Toggle pause/resume of the agent
- `exit` or `quit` - Close the application

### Common Error Solutions

- **"Gemini API key not found"**: Check your credentials.json file or environment variable
- **"OCR initialization failed"**: Make sure Tesseract is installed and in your PATH
- **"UI patterns could not be loaded"**: Verify data/ui_patterns.json exists and is valid JSON

## Configuration System

The agent uses a multi-layered configuration system for flexibility and security:

### Core Configuration Files

- **default_config.json**: Contains non-sensitive settings
  - UI parameters
  - Memory settings
  - Detection thresholds
  - Model parameters
- **credentials.json**: Contains sensitive data (git-ignored)
  - API keys
  - Usernames/passwords
  - Access tokens
- **prompt_templates.json**: Contains AI prompt structures
  - Task instructions
  - System prompts
  - Response formatting

### Key Configuration Options

| Setting                           | Description                    | Default              |
| --------------------------------- | ------------------------------ | -------------------- |
| `general.debug_mode`              | Enable detailed logging        | `false`              |
| `general.log_level`               | Log verbosity level            | `"INFO"`             |
| `perception.ocr_enabled`          | Enable text recognition        | `true`               |
| `perception.ui_detection_enabled` | Enable UI element detection    | `true`               |
| `gemini.model_name`               | Gemini AI model to use         | `"gemini-2.5-flash"` |
| `memory.max_items`                | Maximum memory items to retain | `100`                |

## Advanced Topics

### Running Tests

```powershell
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_perception.py
```

### Extending the Agent

The modular architecture makes it easy to extend functionality:

1. **Add UI Patterns**: Extend data/ui_patterns.json with new element definitions
2. **Create Custom Tools**: Implement new tools in src/tools/
3. **Enhance Perception**: Add detection methods in src/perception/

## Troubleshooting

### Common Issues

- **Agent not finding UI elements**: Try adjusting `perception.element_confidence_threshold`
- **Slow performance**: Reduce screenshot frequency or disable advanced OCR
- **Memory leaks**: Adjust `memory.max_items` and `memory.expiry_seconds`

## License

This project is licensed under the MIT License.

## Acknowledgments

- Google Gemini for AI models
- OpenCV for computer vision capabilities
- PyAutoGUI and PyWinAuto for UI automation
- Tesseract for OCR capabilities

## Roadmap

- Linux support (currently Windows-only)
- Advanced task planning with multi-step reasoning
- Web browser integration
- Custom action tool framework
- Neural network-based UI element recognition

## Security Notes

This project uses API keys and potentially sensitive data. To maintain security:

1. **Never commit API keys to version control**

   - The `.gitignore` file excludes `credentials.json` and `default_config.json`
   - Use environment variables in CI/CD pipelines

2. **Use the template system properly**

   - Copy `credentials.json.template` → `credentials.json` and add your keys
   - Copy `default_config.json.template` → `default_config.json` if needed

3. **Check configuration files before commits**
   - Run `git diff --staged` before committing to ensure no keys are included

## Contributing

Contributions are welcome! To contribute to DjenisAiAgent:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`python -m pytest tests/`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Contact

- Project Owner: [ejupi-djenis30](https://github.com/ejupi-djenis30)
- Repository: [DjenisAiAgent](https://github.com/ejupi-djenis30/DjenisAiAgent)

## Disclaimer

This software is provided as-is. Always test automation in a safe environment before using in production systems.
