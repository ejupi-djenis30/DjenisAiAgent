# ❓ Frequently Asked Questions (FAQ)

## General Questions

### What is DjenisAiAgent?

DjenisAiAgent is an AI-powered automation tool that can interact with your Windows 11 computer like a human would. It uses Google's Gemini AI to understand your screen, make decisions, and perform tasks autonomously.

### Is DjenisAiAgent free to use?

Yes, DjenisAiAgent is open source and free under the MIT License. However, you need a Google Gemini API key, which may have associated costs depending on your usage.

### What can DjenisAiAgent do?

DjenisAiAgent can:

- Open applications
- Click buttons and UI elements
- Type text
- Navigate menus
- Take screenshots
- Read text from the screen (OCR)
- Remember previous actions
- Execute complex multi-step tasks

### What can't DjenisAiAgent do?

Current limitations:

- Only works on Windows 11
- Cannot interact with some secure applications
- Limited to visible UI elements
- Requires manual supervision for safety
- Cannot handle CAPTCHAs or security challenges

## Installation & Setup

### What are the system requirements?

- **OS**: Windows 11
- **Python**: 3.9 or higher
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 500MB for installation
- **Internet**: Required for Gemini AI API

### How do I get a Gemini API key?

1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Get API Key"
4. Copy the key to `config/credentials.json`

### Do I need Tesseract OCR?

Tesseract is optional but recommended for better text recognition. You can:

- Install it from [Tesseract GitHub](https://github.com/UB-Mannheim/tesseract/wiki)
- Or disable OCR in configuration: `"ocr_enabled": false`

### The setup script fails. What should I do?

Common solutions:

1. Ensure Python 3.9+ is installed
2. Run PowerShell as Administrator
3. Update pip: `python -m pip install --upgrade pip`
4. Check your internet connection
5. Try manual installation steps

## Configuration

### Where do I put my API key?

Add your Gemini API key to `config/credentials.json`:

```json
{
  "api_key": "YOUR_GEMINI_API_KEY_HERE"
}
```

Never commit this file to Git (it's gitignored by default).

### How do I change the screenshot directory?

Edit `config/default_config.json`:

```json
{
  "perception": {
    "screenshot_dir": "C:/path/to/your/directory"
  }
}
```

### Can I use environment variables for configuration?

Yes! Set environment variables:

```powershell
$env:GEMINI_API_KEY = "your-key"
```

The agent will use environment variables if config files don't exist.

### How do I adjust the AI's behavior?

Edit `config/default_config.json`:

```json
{
  "gemini": {
    "temperature": 0.7,  # Lower = more deterministic, Higher = more creative
    "max_tokens": 2048   # Maximum response length
  }
}
```

## Usage

### How do I start the agent?

**GUI Mode** (recommended):

```powershell
python launch_ui.py
```

**CLI Mode**:

```powershell
python src/main.py --task "Your task here"
```

### What kind of tasks can I give it?

Examples:

- Simple: "Take a screenshot", "Open Calculator"
- Medium: "Open Notepad and type Hello World"
- Complex: "Open Calculator, calculate 25 \* 4, and save the result"

### How do I stop the agent?

- **GUI**: Click the "Stop" button
- **CLI**: Press `Ctrl+C`
- **Emergency**: Close the terminal window

### Why isn't the agent finding UI elements?

Possible reasons:

1. Element confidence threshold too high - lower it in config
2. OCR disabled - enable it for better text detection
3. UI element not visible on screen
4. Application using custom UI framework

Try adjusting `element_confidence_threshold` in config from 0.8 to 0.6.

### Can I run multiple agents simultaneously?

Not recommended. Multiple agents controlling the same mouse/keyboard can cause conflicts. Use sequential execution instead.

## Troubleshooting

### "No module named 'src'" error

**Cause**: Not running from project root directory.

**Solution**:

```powershell
cd DjenisAiAgent
python launch_ui.py
```

### "API key not found" error

**Cause**: Missing or invalid API key in configuration.

**Solution**:

1. Check `config/credentials.json` exists
2. Verify API key is correctly formatted
3. Try setting environment variable: `$env:GEMINI_API_KEY = "your-key"`

### "Tesseract not found" error

**Cause**: Tesseract OCR not installed or not in PATH.

**Solutions**:

1. Install Tesseract and add to PATH
2. Or disable OCR in config: `"ocr_enabled": false`

### Agent is very slow

**Possible causes and solutions**:

1. **High screenshot frequency**

   - Reduce capture rate in config

2. **OCR enabled but not needed**

   - Disable if not using text recognition

3. **Low confidence threshold**

   - Increase to reduce false positives

4. **Debug mode enabled**
   - Disable for better performance

### Screenshots aren't being saved

**Solutions**:

1. Check `data/screenshots` directory exists
2. Verify write permissions
3. Check disk space
4. Review `screenshot_dir` setting in config

### The GUI won't start

**Common fixes**:

1. Ensure Tkinter is installed (comes with Python)
2. Try reinstalling Python with Tkinter option
3. Check error logs in `agent.log`
4. Run from command line to see error messages

## Development

### How do I contribute?

1. Read [CONTRIBUTING.md](../CONTRIBUTING.md)
2. Fork the repository
3. Create a feature branch
4. Make your changes
5. Submit a pull request

### How do I run tests?

```powershell
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Can I create custom tools?

Yes! See the [API Reference](api-reference.md) for examples of creating custom tools.

### How do I add a new UI pattern?

Edit `data/ui_patterns.json` and add your pattern:

```json
{
  "pattern_name": {
    "type": "button",
    "visual_features": {...},
    "text_hints": ["Click", "OK", "Submit"]
  }
}
```

## Security & Privacy

### Is my data safe?

DjenisAiAgent:

- Stores API keys locally (gitignored)
- Saves screenshots locally (gitignored)
- Sends screenshots to Gemini AI for analysis
- Does not collect telemetry

**Important**: Screenshots sent to Gemini AI may contain sensitive information. Use caution with confidential data.

### Can I use this offline?

No. DjenisAiAgent requires internet connection for:

- Gemini AI API calls
- Python package installations

Some features (screenshot capture, local analysis) work offline, but AI decision-making requires connectivity.

### Should I use this on a production machine?

**Not recommended** for production use. DjenisAiAgent:

- Is in alpha/beta stage
- May make unintended actions
- Requires supervision
- Could interact with sensitive data

Use on test machines or with caution.

### How do I report a security vulnerability?

Report security issues privately to the repository owner. Do not open public issues for security concerns.

## Performance

### How much does it cost to run?

Costs depend on Gemini AI API usage:

- Each screenshot analysis = 1 API call
- Pricing varies by Google's current rates
- Monitor usage in Google Cloud Console

### How fast can it execute tasks?

Typical execution times:

- Simple task (1-2 actions): 5-15 seconds
- Medium task (3-5 actions): 15-45 seconds
- Complex task (6+ actions): 1-3 minutes

Factors affecting speed:

- API response time
- Screenshot analysis complexity
- UI element detection difficulty
- Safety delays between actions

### Can I make it faster?

Yes, by:

1. Reducing safety delays (not recommended)
2. Disabling unnecessary features (OCR if not needed)
3. Using faster screenshot capture methods
4. Caching common UI patterns

## Future Plans

### Will Linux/macOS be supported?

Yes! Linux support is planned for v0.2.0. macOS support is under consideration but faces technical challenges with UI automation.

### Will there be a web interface?

Web interface and REST API are on the roadmap for future versions.

### Can I use this commercially?

Yes, under the MIT License terms. However:

- No warranty is provided
- You must include the license
- Google Gemini API has its own terms of service

### How can I request a feature?

1. Check [existing feature requests](https://github.com/ejupi-djenis30/DjenisAiAgent/issues?q=is%3Aissue+is%3Aopen+label%3Aenhancement)
2. If not found, [create a new feature request](https://github.com/ejupi-djenis30/DjenisAiAgent/issues/new/choose)
3. Provide detailed description and use cases

## Getting Help

### Where can I get help?

1. **Documentation**: Check [docs/](README.md) folder
2. **Issues**: Search [GitHub Issues](https://github.com/ejupi-djenis30/DjenisAiAgent/issues)
3. **Discussions**: Join [GitHub Discussions](https://github.com/ejupi-djenis30/DjenisAiAgent/discussions)

### How do I report a bug?

1. Check if the bug was already reported
2. Create a [new issue](https://github.com/ejupi-djenis30/DjenisAiAgent/issues/new/choose)
3. Use the bug report template
4. Include:
   - Steps to reproduce
   - Expected vs actual behavior
   - System information
   - Relevant logs

### The documentation doesn't answer my question

If you can't find an answer:

1. Search [closed issues](https://github.com/ejupi-djenis30/DjenisAiAgent/issues?q=is%3Aissue+is%3Aclosed)
2. Ask in [Discussions](https://github.com/ejupi-djenis30/DjenisAiAgent/discussions)
3. Create a new issue with the "question" label

---

**Still have questions?** [Open an issue](https://github.com/ejupi-djenis30/DjenisAiAgent/issues/new) or check our [documentation](README.md)!
