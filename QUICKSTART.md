# Quick Start Guide

Get up and running with DjenisAiAgent in 5 minutes!

## Prerequisites

- Windows 11
- Python 3.9+
- Google Gemini API Key

## Installation (Quick Method)

### Step 1: Clone & Setup

```powershell
# Clone the repository
git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
cd DjenisAiAgent

# Run automated setup
.\setup.ps1
```

The setup script will:

- ✅ Check Python version
- ✅ Create virtual environment
- ✅ Install all dependencies
- ✅ Create necessary directories
- ✅ Set up configuration files

### Step 2: Configure API Key

Edit `config/credentials.json`:

```json
{
  "username": "",
  "password": "",
  "api_key": "YOUR_GEMINI_API_KEY_HERE",
  "token": ""
}
```

Get your API key at: https://makersuite.google.com/app/apikey

### Step 3: Run the Agent

**Option A - GUI (Recommended for beginners)**

```powershell
python launch_ui.py
```

**Option B - Command Line**

```powershell
python src/main.py --task "Take a screenshot"
```

## First Tasks to Try

### 1. Simple Screenshot

```
Task: "Take a screenshot"
```

Check `data/screenshots/` for the result.

### 2. Open Application

```
Task: "Open Calculator"
```

Watch the agent find and click the Calculator icon.

### 3. Type Text

```
Task: "Open Notepad and type 'Hello World'"
```

The agent will open Notepad and type the text.

## GUI Controls

- **Start Agent**: Begin agent execution
- **Pause**: Temporarily pause the agent
- **Stop**: Completely stop the agent
- **Task Input**: Enter natural language commands
- **Status Panel**: View agent status and progress
- **Screenshot View**: See what the agent sees
- **Log Panel**: Read detailed execution logs

## Project Structure (Quick Reference)

```
DjenisAiAgent/
├── src/                 # Source code
├── tests/              # Tests
├── config/             # Configuration files
├── data/               # Runtime data (screenshots, memory)
├── docs/               # Documentation
├── launch_ui.py        # Start GUI
└── setup.ps1           # Setup script
```

## Common Commands

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run tests
pytest tests/ -v

# Clean project
.\clean.ps1

# Format code
black src/ --line-length=100

# Check code quality
flake8 src/ --max-line-length=100
```

## Troubleshooting

### Issue: "No module named 'src'"

**Solution**: Make sure you're in the project root directory.

### Issue: "API key not found"

**Solution**: Check that `config/credentials.json` exists and contains your API key.

### Issue: "Permission denied"

**Solution**: Run PowerShell as Administrator or adjust execution policy:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue: Dependencies fail to install

**Solution**: Upgrade pip first:

```powershell
python -m pip install --upgrade pip
```

## Next Steps

1. 📖 Read the [Getting Started Guide](docs/getting-started.md)
2. 🏗️ Learn about the [Architecture](docs/architecture.md)
3. 🤝 Check [Contributing Guidelines](CONTRIBUTING.md)
4. 🐛 Report issues on [GitHub](https://github.com/ejupi-djenis30/DjenisAiAgent/issues)

## Need Help?

- 📚 [Full Documentation](docs/README.md)
- 💬 [GitHub Discussions](https://github.com/ejupi-djenis30/DjenisAiAgent/discussions)
- 🐛 [Issue Tracker](https://github.com/ejupi-djenis30/DjenisAiAgent/issues)

## Tips for Success

1. **Start Simple**: Begin with basic tasks like screenshots
2. **Use Clear Commands**: The more specific, the better
3. **Check Logs**: The `agent.log` file contains detailed information
4. **Monitor Carefully**: Watch the agent's actions when starting out
5. **Experiment**: Try different tasks to understand capabilities

## Safety Notes

⚠️ **Important Safety Information**:

- The agent can control your mouse and keyboard
- Always monitor the agent during operation
- Start with simple, safe tasks
- Use the pause button if something goes wrong
- Keep sensitive windows closed when running the agent

## Quick Reference Card

| Action        | Command                       |
| ------------- | ----------------------------- |
| Start GUI     | `python launch_ui.py`         |
| Start CLI     | `python src/main.py`          |
| Run Tests     | `pytest tests/`               |
| Clean Project | `.\clean.ps1`                 |
| Setup Project | `.\setup.ps1`                 |
| Activate venv | `.\venv\Scripts\Activate.ps1` |

---

**Ready to automate?** Start with `python launch_ui.py` and enter your first task! 🚀
