# Getting Started with DjenisAiAgent

This guide will help you get DjenisAiAgent up and running on your Windows 11 system.

## Prerequisites

Before you begin, ensure you have the following:

1. **Windows 11** operating system
2. **Python 3.9 or higher** installed
3. **Google Gemini API Key** ([Get one here](https://makersuite.google.com/app/apikey))
4. **Tesseract OCR** (optional, for text recognition)
   - Download from: https://github.com/UB-Mannheim/tesseract/wiki
   - Add to system PATH after installation

## Installation Methods

### Method 1: Automated Setup (Recommended)

1. Clone the repository:

   ```powershell
   git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
   cd DjenisAiAgent
   ```

2. Run the setup script:

   ```powershell
   .\setup.ps1
   ```

3. Follow the prompts to install dependencies and configure the project.

### Method 2: Manual Setup

1. Clone the repository:

   ```powershell
   git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
   cd DjenisAiAgent
   ```

2. Create a virtual environment:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

4. Create configuration files:
   ```powershell
   Copy-Item config/credentials.json.template config/credentials.json
   Copy-Item config/default_config.json.template config/default_config.json
   ```

## Configuration

### 1. API Key Setup

Edit `config/credentials.json` and add your Gemini API key:

```json
{
  "username": "",
  "password": "",
  "api_key": "YOUR_GEMINI_API_KEY_HERE",
  "token": ""
}
```

### 2. Verify Configuration

Open `config/default_config.json` and review the settings. Default values should work for most users.

## Running the Agent

### Option 1: Graphical Interface

Start the GUI application:

```powershell
python launch_ui.py
```

The control panel will open, allowing you to:

- Start/stop the agent
- Input tasks in natural language
- Monitor agent status and actions
- View screenshots and logs

### Option 2: Command Line

Run the agent from the command line:

```powershell
python src/main.py --task "Open Notepad and type 'Hello World'"
```

## First Steps

1. **Test Basic Functionality**

   - Start the agent UI
   - Click "Start Agent"
   - Enter a simple task: "Take a screenshot"
   - Verify the screenshot appears in `data/screenshots/`

2. **Try a Simple Automation**

   - Task: "Open Calculator"
   - The agent should analyze the screen and click the Calculator icon

3. **Explore the Interface**
   - Review the status panel
   - Check the log output
   - Examine captured screenshots

## Next Steps

- Read the [Configuration Guide](configuration.md) for advanced settings
- Explore the [API Reference](api-reference.md) to understand available features
- Check out [Architecture Overview](architecture.md) to learn how it works
- Review [Development Guide](development.md) if you want to contribute

## Troubleshooting

If you encounter issues:

1. Check the `agent.log` file for error messages
2. Verify your API key is correct
3. Ensure all dependencies are installed
4. Review the [Troubleshooting Guide](troubleshooting.md)

## Common Issues

### "No module named 'src'"

- Make sure you're running from the project root directory
- Verify the virtual environment is activated

### "API key not found"

- Check that `config/credentials.json` exists
- Verify the API key is properly formatted

### Tesseract OCR not found

- Install Tesseract OCR from the link above
- Add Tesseract to your system PATH
- Or set `ocr_enabled: false` in config

## Getting Help

- [FAQ](faq.md)
- [GitHub Issues](https://github.com/ejupi-djenis30/DjenisAiAgent/issues)
- [Troubleshooting Guide](troubleshooting.md)
