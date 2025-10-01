# DjenisAiAgent - Intelligent UI Automation Agent# DjenisAiAgent - Intelligent UI Automation Agent

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[![Platform: Windows 11](https://img.shields.io/badge/platform-Windows%2011-blue.svg)](https://www.microsoft.com/windows)[![Platform: Windows 11](https://img.shields.io/badge/platform-Windows%2011-blue.svg)](https://www.microsoft.com/windows)

## 🎯 Overview## Overview

DjenisAiAgent is an advanced automation assistant that leverages Google's Gemini AI to interact with Windows 11 user interfaces autonomously. By combining computer vision, artificial intelligence, and UI automation, the agent can "see" your screen, understand context, and control the mouse and keyboard like a human operator.DjenisAiAgent is an advanced automation assistant that uses Google's Gemini AI to interact with user interfaces on Windows 11. The agent captures screenshots, analyzes UI elements using computer vision, and performs actions based on AI-driven decisions.

DjenisAiAgent is an advanced automation assistant that uses Google's Gemini AI to interact with user interfaces on Windows 11. The agent captures screenshots, analyzes UI elements using computer vision, and performs actions based on AI-driven decisions.

**Key Capabilities:**

- 🤖 AI-powered decision making using Google GeminiBy combining computer vision, artificial intelligence, and UI automation, DjenisAiAgent can navigate applications, recognize interface elements, and execute tasks autonomously - essentially "seeing" your screen and controlling the mouse and keyboard like a human would.

- 👁️ Computer vision for UI element detectionBy combining computer vision, artificial intelligence, and UI automation, DjenisAiAgent can navigate applications, recognize interface elements, and execute tasks autonomously - essentially "seeing" your screen and controlling the mouse and keyboard like a human would.

- 🔤 Optical Character Recognition (OCR) with Tesseract

- 🧠 Context-aware task memory system## Key Features

- 🖥️ User-friendly graphical control interface

- 🔧 Extensible, modular architecture## Key Features

## ⚡ Quick Start- **AI-Powered Interface Analysis**: Uses Gemini AI models to understand screen content and context

- **Computer Vision**: Detects buttons, text fields, and other UI elements using advanced image processing

````powershell- **Optical Character Recognition (OCR)**: Reads text from screen elements using Tesseract

# Clone and setup- **UI Pattern Recognition**: Identifies common UI components using visual pattern matching

git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git- **Task Memory**: Remembers previous actions and context for better decision making

cd DjenisAiAgent- **Graphical User Interface**: Easy-to-use control panel for monitoring and commanding the agent

.\setup.ps1- **Extensible Architecture**: Modular design allows for adding new capabilities and integrations

- **AI-Powered Interface Analysis**: Uses Gemini AI models to understand screen content and context

# Add your Gemini API key to config/credentials.json- **Computer Vision**: Detects buttons, text fields, and other UI elements using advanced image processing

# Then launch- **Optical Character Recognition (OCR)**: Reads text from screen elements using Tesseract

python launch_ui.py- **UI Pattern Recognition**: Identifies common UI components using visual pattern matching

```- **Task Memory**: Remembers previous actions and context for better decision making

- **Graphical User Interface**: Easy-to-use control panel for monitoring and commanding the agent

📖 **For detailed instructions, see [QUICKSTART.md](QUICKSTART.md)**- **Extensible Architecture**: Modular design allows for adding new capabilities and integrations



## 📋 Table of Contents## Project Structure



- [Features](#-features)```

- [Requirements](#-requirements)DjenisAiAgent/

- [Installation](#-installation)├── src/                      # Source code

- [Configuration](#-configuration)│   ├── agent_core.py         # Main agent implementation

- [Usage](#-usage)│   ├── config.py             # Configuration management

- [Project Structure](#-project-structure)│   ├── main.py               # Application entry point

- [Documentation](#-documentation)│   ├── abstractions/         # Abstract interfaces

- [Development](#-development)│   ├── gemini/               # Gemini AI integration

- [Testing](#-testing)│   ├── memory/               # Memory management components

- [Contributing](#-contributing)│   ├── perception/           # Screen analysis and UI detection

- [License](#-license)│   ├── planning/             # Task planning and execution

│   ├── tools/                # Action tools (input, automation)

## ✨ Features│   └── ui/                   # User interface components

├── tests/                    # Unit and integration tests

### Core Capabilities├── config/                   # Configuration files

- **AI-Powered Analysis**: Gemini AI interprets screen content and makes intelligent decisions│   ├── default_config.json         # Main configuration (without sensitive data)

- **Computer Vision**: Advanced image processing detects buttons, text fields, and UI components│   ├── default_config.json.template # Template for configuration

- **OCR Integration**: Tesseract reads text from screen elements with high accuracy│   ├── credentials.json           # User's private API keys (git-ignored)

- **Pattern Recognition**: Identifies and remembers common UI patterns for faster interaction│   ├── credentials.json.template  # Template for credentials

- **Task Memory**: Maintains context across sessions for smarter automation│   └── prompt_templates.json      # AI prompt structures

- **GUI Control Panel**: Monitor status, view screenshots, and control the agent in real-time├── data/                     # Runtime data (created on first run)

│   ├── screenshots/          # Captured screenshots

### Technical Features│   ├── task_memory/          # Persisted task data

- Modular, extensible architecture│   ├── ui_memory/            # UI interaction history

- Configurable perception thresholds│   └── ui_patterns.json      # UI element pattern definitions

- Safety delays and error recovery├── launch_ui.py              # Start the graphical interface

- Comprehensive logging system├── requirements.txt          # Python dependencies

- Screenshot capture and analysis└── README.md                 # This documentation

- Multi-step task planning├── src/                      # Source code

│   ├── agent_core.py         # Main agent implementation

## 📦 Requirements│   ├── config.py             # Configuration management

│   ├── main.py               # Application entry point

### System Requirements│   ├── abstractions/         # Abstract interfaces

- **OS**: Windows 11 (required for UI automation features)│   ├── gemini/               # Gemini AI integration

- **Python**: 3.9 or higher (3.13 supported)│   ├── memory/               # Memory management components

- **RAM**: 4GB minimum, 8GB recommended│   ├── perception/           # Screen analysis and UI detection

- **Storage**: 500MB for installation + space for screenshots│   ├── planning/             # Task planning and execution

│   ├── tools/                # Action tools (input, automation)

### API & Services│   └── ui/                   # User interface components

- **Google Gemini API Key** - [Get one here](https://makersuite.google.com/app/apikey)├── tests/                    # Unit and integration tests

- **Tesseract OCR** (optional) - [Download here](https://github.com/UB-Mannheim/tesseract/wiki)├── config/                   # Configuration files

│   ├── default_config.json         # Main configuration (without sensitive data)

## 🚀 Installation│   ├── default_config.json.template # Template for configuration

│   ├── credentials.json           # User's private API keys (git-ignored)

### Automated Setup (Recommended)│   ├── credentials.json.template  # Template for credentials

│   └── prompt_templates.json      # AI prompt structures

```powershell├── data/                     # Runtime data (created on first run)

# Clone the repository│   ├── screenshots/          # Captured screenshots

git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git│   ├── task_memory/          # Persisted task data

cd DjenisAiAgent│   ├── ui_memory/            # UI interaction history

│   └── ui_patterns.json      # UI element pattern definitions

# Run automated setup├── launch_ui.py              # Start the graphical interface

.\setup.ps1├── requirements.txt          # Python dependencies

```└── README.md                 # This documentation

````

The setup script will:

- ✅ Verify Python version## Requirements

- ✅ Create virtual environment

- ✅ Install all dependencies- **Python 3.9+**

- ✅ Set up configuration files- **Windows 11** (required for Windows UI automation features)

- ✅ Create necessary directories- **Google Gemini API Key** (for AI capabilities)

- **Tesseract OCR** (optional, for text recognition in screenshots)

### Manual Setup

## Installation

````powershell

# Create virtual environment### 1. Set Up Python Environment

python -m venv venv

.\venv\Scripts\Activate.ps1```powershell

# Clone the repository

# Install dependenciesgit clone https://github.com/ejupi-djenis30/DjenisAiAgent.git

pip install -r requirements.txtcd DjenisAiAgent



# Copy configuration templates# Create and activate a virtual environment

Copy-Item config\credentials.json.template config\credentials.jsonpython -m venv venv

Copy-Item config\default_config.json.template config\default_config.json.\venv\Scripts\activate

````

# Install dependencies

### Development Installationpip install -r requirements.txt

````

```powershell

# Install with development dependencies### 2. Configure API Keys

pip install -r requirements.txt

pip install -r requirements-dev.txtFor security reasons, API keys are not stored in the main configuration files that might be committed to the repository. You have two options:



# Install as editable package**Option A: Using credentials.json**

pip install -e .

```powershell

# Setup pre-commit hooks# Copy the template

pre-commit installCopy-Item config/credentials.json.template config/credentials.json

````

# Edit the file and add your API key

## ⚙️ Configuration# The file should look like:

# {

### 1. API Key Setup# "username": "",

# "password": "",

Edit `config/credentials.json`:# "api_key": "YOUR_GEMINI_API_KEY_HERE",

# "token": ""

````json# }

{```

  "username": "",

  "password": "",**Option B: Using Environment Variables**

  "api_key": "YOUR_GEMINI_API_KEY_HERE",

  "token": ""```powershell

}# PowerShell

```$env:GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"



**Security Note:** This file is gitignored and should never be committed.# Command Prompt

set GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE

### 2. Agent Configuration```



Edit `config/default_config.json` to customize:### 3. Install Tesseract OCR (Optional)



```jsonFor text recognition capabilities:

{

  "general": {1. Download Tesseract OCR from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

    "debug_mode": false,2. During installation, ensure "Add to PATH" is selected

    "log_level": "INFO"3. Verify installation:

  },   ```powershell

  "perception": {   tesseract --version

    "screenshot_dir": "data/screenshots",   ```

    "ocr_enabled": true,

    "ui_detection_enabled": true,- **Python 3.9+**

    "element_confidence_threshold": 0.8- **Windows 11** (required for Windows UI automation features)

  },- **Google Gemini API Key** (for AI capabilities)

  "gemini": {- **Tesseract OCR** (optional, for text recognition in screenshots)

    "model_name": "gemini-pro-vision",

    "temperature": 0.7,## Installation

    "max_tokens": 2048

  },### 1. Set Up Python Environment

  "memory": {

    "max_items": 100,```powershell

    "expiry_seconds": 3600# Clone the repository

  }git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git

}cd DjenisAiAgent

````

# Create and activate a virtual environment

### 3. Environment Variables (Alternative)python -m venv venv

.\venv\Scripts\activate

```powershell

# Set API key via environment variable# Install dependencies

$env:GEMINI_API_KEY = "your-api-key-here"pip install -r requirements.txt

```

## 💻 Usage### 2. Configure API Keys

### GUI Mode (Recommended)For security reasons, API keys are not stored in the main configuration files that might be committed to the repository. You have two options:

```````powershell**Option A: Using credentials.json**

python launch_ui.py

``````powershell

# Copy the template

**GUI Features:**Copy-Item config/credentials.json.template config/credentials.json

- Start/Stop/Pause controls

- Natural language task input# Edit the file and add your API key

- Real-time status monitoring# The file should look like:

- Screenshot preview# {

- Activity logs#   "username": "",

- Error reporting#   "password": "",

#   "api_key": "YOUR_GEMINI_API_KEY_HERE",

### CLI Mode#   "token": ""

# }

```powershell```

# Execute a single task

python src/main.py --task "Open Calculator"**Option B: Using Environment Variables**



# With configuration file```powershell

python src/main.py --config config/my_config.json --task "Type Hello World"# PowerShell

$env:GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# Debug mode

python src/main.py --debug --task "Take screenshot"# Command Prompt

```set GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE

```````

### Example Tasks

### 3. Install Tesseract OCR (Optional)

````python

# Simple tasksFor text recognition capabilities:

"Take a screenshot"

"Open Notepad"1. Download Tesseract OCR from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

"Click the Start button"2. During installation, ensure "Add to PATH" is selected

3. Verify installation:

# Complex tasks   ```powershell

"Open Calculator and calculate 25 * 4"   tesseract --version

"Open Notepad, type 'Hello World', and save as test.txt"   ```

"Find and click the Settings icon"

```## Usage



## 📁 Project Structure### Running the Agent



```There are two main ways to run the DjenisAiAgent:

DjenisAiAgent/

├── .github/                       # GitHub configuration#### 1. With the Graphical User Interface (Recommended)

│   ├── workflows/                 # CI/CD workflows

│   ├── ISSUE_TEMPLATE/           # Issue templates```powershell

│   └── PULL_REQUEST_TEMPLATE.md  # PR template# Run the UI version

├── docs/                         # Documentationpython launch_ui.py

│   ├── README.md                 # Documentation index```

│   ├── getting-started.md        # Detailed setup guide

│   └── architecture.md           # System architectureThis launches a user-friendly interface where you can:

├── src/                          # Source code

│   ├── __init__.py              # Package initialization- Monitor the agent's status and activities

│   ├── agent_core.py            # Main agent orchestrator- Send commands via the text input

│   ├── config.py                # Configuration management- Take screenshots for analysis

│   ├── main.py                  # CLI entry point- Pause/resume agent operations

│   ├── abstractions/            # Abstract interfaces

│   ├── gemini/                  # Gemini AI client#### 2. Command Line Mode

│   ├── memory/                  # Memory management

│   ├── perception/              # Screen analysis```powershell

│   ├── planning/                # Task planning# Basic usage

│   ├── tools/                   # Action toolspython src/main.py

│   └── ui/                      # GUI components

├── tests/                        # Test suite# With debug mode enabled

├── config/                       # Configurationpython src/main.py --debug

├── data/                         # Runtime data (gitignored)

├── .editorconfig                # Editor settings# With a custom configuration file

├── .gitignore                   # Git ignore rulespython src/main.py --config path/to/custom/config.json

├── .pre-commit-config.yaml      # Pre-commit hooks```

├── CHANGELOG.md                 # Version history

├── CONTRIBUTING.md              # Contribution guide### Running the Agent

├── LICENSE                      # MIT License

├── Makefile                     # Build commandsThere are two main ways to run the DjenisAiAgent:

├── pyproject.toml              # Project metadata

├── QUICKSTART.md               # Quick start guide#### 1. With the Graphical User Interface (Recommended)

├── README.md                   # This file

├── requirements.txt            # Dependencies```powershell

├── requirements-dev.txt        # Dev dependencies# Run the UI version

├── setup.py                    # Package setuppython launch_ui.py

├── clean.ps1                   # Cleanup script```

├── setup.ps1                   # Setup script

├── verify.ps1                  # Verification scriptThis launches a user-friendly interface where you can:

└── launch_ui.py                # GUI launcher

```- Monitor the agent's status and activities

- Send commands via the text input

## 📚 Documentation- Take screenshots for analysis

- Pause/resume agent operations

- **[QUICKSTART.md](QUICKSTART.md)** - Get up and running in 5 minutes

- **[docs/getting-started.md](docs/getting-started.md)** - Comprehensive setup guide#### 2. Command Line Mode

- **[docs/architecture.md](docs/architecture.md)** - System design and components

- **[CONTRIBUTING.md](CONTRIBUTING.md)** - How to contribute```powershell

- **[CHANGELOG.md](CHANGELOG.md)** - Version history# Basic usage

- **[IMPROVEMENTS.md](IMPROVEMENTS.md)** - Recent project improvementspython src/main.py



## 🛠️ Development# With debug mode enabled

python src/main.py --debug

### Setting Up Development Environment

# With a custom configuration file

```powershellpython src/main.py --config path/to/custom/config.json

# Install development dependencies```

pip install -r requirements-dev.txt

### Special Commands

# Install pre-commit hooks

pre-commit installWhen using the UI, you can type these commands:



# Run in development mode- `screenshot` - Capture the screen and analyze it

pip install -e .- `pause` - Toggle pause/resume of the agent

```- `exit` or `quit` - Close the application



### Code Quality Tools### Common Error Solutions



```powershell- **"Gemini API key not found"**: Check your credentials.json file or environment variable

# Format code with Black- **"OCR initialization failed"**: Make sure Tesseract is installed and in your PATH

black src/ tests/ --line-length=100- **"UI patterns could not be loaded"**: Verify data/ui_patterns.json exists and is valid JSON



# Lint with flake8## Configuration System

flake8 src/ --max-line-length=100

The agent uses a multi-layered configuration system for flexibility and security:

# Type check with mypy

mypy src/ --ignore-missing-imports### Core Configuration Files



# Run pre-commit checks- **default_config.json**: Contains non-sensitive settings

pre-commit run --all-files  - UI parameters

```  - Memory settings

  - Detection thresholds

### Project Scripts  - Model parameters

- **credentials.json**: Contains sensitive data (git-ignored)

```powershell  - API keys

# Setup project  - Usernames/passwords

.\setup.ps1  - Access tokens

- **prompt_templates.json**: Contains AI prompt structures

# Clean project  - Task instructions

.\clean.ps1  - System prompts

  - Response formatting

# Verify installation

.\verify.ps1### Key Configuration Options

````

| Setting | Description | Default |

## 🧪 Testing| --------------------------------- | ------------------------------ | -------------------- |

| `general.debug_mode` | Enable detailed logging | `false` |

```powershell| `general.log_level`              | Log verbosity level            |`"INFO"` |

# Run all tests| `perception.ocr_enabled` | Enable text recognition | `true` |

pytest tests/ -v| `perception.ui_detection_enabled` | Enable UI element detection | `true` |

| `gemini.model_name` | Gemini AI model to use | `"gemini-2.5-flash"` |

# Run with coverage| `memory.max_items` | Maximum memory items to retain | `100` |

pytest tests/ --cov=src --cov-report=html

## Advanced Topics

# Run specific test file

pytest tests/test_agent_core.py -v### Special Commands

````````

When using the UI, you can type these commands:

## 🤝 Contributing

- `screenshot` - Capture the screen and analyze it

We welcome contributions! Please read our [Contributing Guidelines](CONTRIBUTING.md) for details.- `pause` - Toggle pause/resume of the agent

- `exit` or `quit` - Close the application

### Quick Contribution Guide

### Common Error Solutions

1. **Fork** the repository

2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)- **"Gemini API key not found"**: Check your credentials.json file or environment variable

3. **Make** your changes following our [coding standards](CONTRIBUTING.md#coding-standards)- **"OCR initialization failed"**: Make sure Tesseract is installed and in your PATH

4. **Write/update** tests- **"UI patterns could not be loaded"**: Verify data/ui_patterns.json exists and is valid JSON

5. **Run** tests (`pytest tests/`)

6. **Commit** changes (`git commit -m 'Add amazing feature'`)## Configuration System

7. **Push** to branch (`git push origin feature/amazing-feature`)

8. **Open** a Pull RequestThe agent uses a multi-layered configuration system for flexibility and security:



## 🔒 Security### Core Configuration Files



- ⚠️ **Never commit API keys** - Use `config/credentials.json` (gitignored)- **default_config.json**: Contains non-sensitive settings

- 🔐 **Use environment variables** for CI/CD pipelines  - UI parameters

- 📝 **Review logs** before sharing - they may contain sensitive data  - Memory settings

- 🛡️ **Keep dependencies updated** - Run `pip list --outdated` regularly  - Detection thresholds

  - Model parameters

Report security vulnerabilities privately to the repository owner.- **credentials.json**: Contains sensitive data (git-ignored)

  - API keys

## 🐛 Troubleshooting  - Usernames/passwords

  - Access tokens

### Common Issues- **prompt_templates.json**: Contains AI prompt structures

  - Task instructions

**"No module named 'src'"**  - System prompts

```powershell  - Response formatting

# Ensure you're in the project root directory

cd DjenisAiAgent### Key Configuration Options

python launch_ui.py

```| Setting                           | Description                    | Default              |

| --------------------------------- | ------------------------------ | -------------------- |

**"API key not found"**| `general.debug_mode`              | Enable detailed logging        | `false`              |

```powershell| `general.log_level`               | Log verbosity level            | `"INFO"`             |

# Verify credentials.json exists and contains your API key| `perception.ocr_enabled`          | Enable text recognition        | `true`               |

cat config\credentials.json| `perception.ui_detection_enabled` | Enable UI element detection    | `true`               |

```| `gemini.model_name`               | Gemini AI model to use         | `"gemini-2.5-flash"` |

| `memory.max_items`                | Maximum memory items to retain | `100`                |

**"Tesseract not found"**

```powershell## Advanced Topics

# Option 1: Install Tesseract and add to PATH

# Option 2: Disable OCR in config/default_config.json### Running Tests

"ocr_enabled": false

```````powershell

# Run all tests

For more help, check the [documentation](docs/README.md) or [create an issue](https://github.com/ejupi-djenis30/DjenisAiAgent/issues).```powershell

# Run all tests

## 🗺️ Roadmappython -m pytest tests/



### Version 0.2.0 (Planned)# Run specific test file

- Linux supportpython -m pytest tests/test_perception.py

- macOS support (limited)

- Web browser automation# Run specific test file

- Enhanced pattern recognitionpython -m pytest tests/test_perception.py

- Plugin system````



### Long-term Goals### Extending the Agent

- Cross-platform compatibility

- Neural network-based UI detectionThe modular architecture makes it easy to extend functionality:

- Multi-monitor support

- REST API interface1. **Add UI Patterns**: Extend data/ui_patterns.json with new element definitions

- Cloud-based execution2. **Create Custom Tools**: Implement new tools in src/tools/

3. **Enhance Perception**: Add detection methods in src/perception/

## 📄 License

## Troubleshooting

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Common Issues

## 🙏 Acknowledgments

- **Agent not finding UI elements**: Try adjusting `perception.element_confidence_threshold`

- **Google** for the Gemini AI platform- **Slow performance**: Reduce screenshot frequency or disable advanced OCR

- **OpenCV community** for computer vision tools- **Memory leaks**: Adjust `memory.max_items` and `memory.expiry_seconds`

- **Tesseract team** for OCR capabilities

- **Python community** for excellent libraries### Extending the Agent

- All contributors who help improve this project

The modular architecture makes it easy to extend functionality:

## 📞 Contact & Support

1. **Add UI Patterns**: Extend data/ui_patterns.json with new element definitions

- **Repository**: [github.com/ejupi-djenis30/DjenisAiAgent](https://github.com/ejupi-djenis30/DjenisAiAgent)2. **Create Custom Tools**: Implement new tools in src/tools/

- **Issues**: [GitHub Issues](https://github.com/ejupi-djenis30/DjenisAiAgent/issues)3. **Enhance Perception**: Add detection methods in src/perception/

- **Author**: [@ejupi-djenis30](https://github.com/ejupi-djenis30)

## Troubleshooting

---

### Common Issues

**⭐ If you find this project useful, please consider giving it a star!**

- **Agent not finding UI elements**: Try adjusting `perception.element_confidence_threshold`

Made with ❤️ by the DjenisAiAgent team- **Slow performance**: Reduce screenshot frequency or disable advanced OCR

- **Memory leaks**: Adjust `memory.max_items` and `memory.expiry_seconds`

## License

This project is licensed under the MIT License.
This project is licensed under the MIT License.

## Acknowledgments

- Google Gemini for AI models
- OpenCV for computer vision capabilities
- PyAutoGUI and PyWinAuto for UI automation
- Tesseract for OCR capabilities

## Roadmap

- Linux support (currently Windows-only)
- Advanced task planning with multi-step reasoning
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

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) for details on how to submit pull requests, report issues, and contribute to the project.

### Quick Contribution Steps

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following our coding standards
4. Run tests (`pytest tests/`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

For more details, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation

- 📚 [Quick Start Guide](QUICKSTART.md) - Get running in 5 minutes
- 📖 [Full Documentation](docs/README.md) - Comprehensive guides
- 🏗️ [Architecture Overview](docs/architecture.md) - System design
- 📝 [Changelog](CHANGELOG.md) - Version history

## Project Status

This project has been recently cleaned up and improved! See [IMPROVEMENTS.md](IMPROVEMENTS.md) for a complete list of enhancements.

### Recent Improvements

- ✅ Standardized codebase to English
- ✅ Added comprehensive documentation
- ✅ Implemented CI/CD workflows
- ✅ Added automated setup and cleanup scripts
- ✅ Enhanced project structure and configuration
- ✅ Added development tools and pre-commit hooks

## Contact

- Project Owner: [ejupi-djenis30](https://github.com/ejupi-djenis30)
- Repository: [DjenisAiAgent](https://github.com/ejupi-djenis30/DjenisAiAgent)
- Issues: [GitHub Issues](https://github.com/ejupi-djenis30/DjenisAiAgent/issues)

## Disclaimer

This software is provided as-is. Always test automation in a safe environment before using in production systems.
````````
