# DjenisAiAgent

Multi-modal Windows automation agent powered by Google Gemini using the ReAct paradigm.

## Project layout

```
.
├── main.py                      # Entry point with CLI argument parsing
├── requirements.txt             # Python dependencies
├── src/
│   ├── config.py               # Flexible configuration with env overrides
│   ├── action/
│   │   └── tools.py            # Windows UI automation tools (click, type, etc.)
│   ├── orchestration/
│   │   └── agent_loop.py       # Main ReAct loop coordinator
│   ├── perception/
│   │   └── screen_capture.py  # Screenshot + UI tree capture
│   └── reasoning/
│       └── gemini_core.py      # Gemini API integration with Function Calling
├── .env                         # User-provided secrets (ignored by git)
└── .env.example                 # Template for local setup
```

## Architecture: ReAct Paradigm

DjenisAiAgent implements the **ReAct (Reason + Act)** pattern:

1. **Observe (Perception)**: Capture screenshot + UI element tree
2. **Reason (Gemini)**: Multimodal LLM decides next action via Function Calling
3. **Act (Tools)**: Execute chosen tool (click, type_text, etc.)
4. **Verify (Feedback)**: Record observation and update history for self-correction

This cycle repeats until the task is completed or max turns is reached.

## Key Features

### 🔧 Robust Action Tools
- **Backend fallback**: UIA (modern) → Win32 (legacy) for maximum compatibility
- **Error handling**: No crashes—failed actions return descriptive messages for self-correction
- **Dynamic UI support**: Waits for elements to be ready before interaction

### 🧠 Gemini Function Calling
- **Structured responses**: Model outputs machine-readable function calls (no fragile parsing)
- **Multimodal context**: Screenshot + UI tree + history sent to Gemini
- **Self-correction**: Observation feedback enables the agent to recover from mistakes

### 🔐 Secure Configuration
- **Environment-first**: Process env → `.env` → defaults (no secret overwriting)
- **Sanitized logging**: `config.safe_view()` redacts API keys
- **Flexible tuning**: Override any `DJENIS_*` variable per environment

## Getting started

### 1. Install dependencies

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure secrets

```powershell
# Copy template and edit with your API key
cp .env.example .env
# Edit .env and set GEMINI_API_KEY="your-key-here"
```

### 3. Run the agent

**Interactive mode (continuous loop):**
```powershell
py -3 .\main.py
# Enter commands one at a time
# Type 'exit' or 'quit' to terminate
```

**CLI mode (single command):**
```powershell
py -3 .\main.py "open notepad and type hello world"
```

**Force interactive after initial command:**
```powershell
py -3 .\main.py "first command" --interactive
```

**With custom settings:**
```powershell
$env:DJENIS_MAX_LOOP_TURNS="15"
$env:DJENIS_LOG_LEVEL="DEBUG"
py -3 .\main.py "your command"
```

See [QUICKSTART.md](QUICKSTART.md) for detailed usage examples.

## Available Tools

The agent can call these tools via Gemini Function Calling:

| Tool | Description | Arguments |
|------|-------------|-----------|
| `click` | Click a UI element | `element_id: str` |
| `type_text` | Type text into an input field | `element_id: str, text: str` |
| `get_text` | Read text from a UI element | `element_id: str` |
| `scroll` | Scroll in a direction | `direction: str, amount: int` |
| `press_hotkey` | Send keyboard shortcuts | `keys: str` |
| `finish_task` | Mark task as complete | `summary: str` |

## Configuration Options

Set via environment variables or `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *(required)* | Your Google AI API key |
| `DJENIS_GEMINI_MODEL` | `gemini-1.5-pro-latest` | Model to use |
| `DJENIS_MAX_LOOP_TURNS` | `50` | Maximum ReAct iterations |
| `DJENIS_ACTION_TIMEOUT` | `30` | Timeout per action (seconds) |
| `DJENIS_TEMPERATURE` | `0.7` | Model creativity (0.0-1.0) |
| `DJENIS_LOG_LEVEL` | `INFO` | Logging verbosity |

## Troubleshooting

### "GEMINI_API_KEY not set"
Make sure you've copied `.env.example` to `.env` and added your actual API key.

### "Nessuna finestra attiva trovata"
The agent needs an active window to interact with. Open an application before running commands.

### Tool execution fails
Check the observation message—the agent logs detailed errors. Common issues:
- Element not found: UI tree might not expose the element you're targeting
- Timeout: Element took too long to appear (try increasing `DJENIS_ACTION_TIMEOUT`)

## Security Notes

- **Never commit `.env`**: The `.gitignore` excludes it, but double-check before pushing
- **Use secret managers in production**: Azure Key Vault, AWS Secrets Manager, etc.
- **Avoid logging secrets**: Use `config.safe_view()` instead of raw config printing

## Example Usage

```powershell
# Simple task
py -3 .\main.py "open calculator and compute 5 plus 3"

# Complex automation
py -3 .\main.py "open edge, go to youtube, search for python tutorial"

# With custom turn limit
$env:DJENIS_MAX_LOOP_TURNS="20"
py -3 .\main.py "your longer task here"
```

## Development

### Run syntax checks
```powershell
py -3 -m compileall .
```

### Test imports
```powershell
py -3 -c "from src.orchestration.agent_loop import run_agent_loop; print('OK')"
```

### Enable debug logging
```powershell
$env:DJENIS_LOG_LEVEL="DEBUG"
$env:DJENIS_VERBOSE_LOGGING="true"
py -3 .\main.py "test command"
```

## Architecture Details

### Why Function Calling?
Traditional LLM agents parse unstructured text responses, leading to fragile, error-prone systems. Gemini's Function Calling forces the model to output structured `FunctionCall` objects with validated parameters—dramatically improving reliability.

### Why ReAct?
The Reason + Act cycle with feedback enables:
- **Self-correction**: Agent sees the result of failed actions and adjusts strategy
- **Transparency**: Each turn logs thought → action → observation for debugging
- **Robustness**: Errors become observations, not crashes

### Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `perception/` | Capture visual (screenshot) + structural (UI tree) state |
| `reasoning/` | Send multimodal context to Gemini, receive function calls |
| `action/` | Execute pywinauto-based UI automation safely |
| `orchestration/` | Coordinate ReAct loop, manage history, handle errors |
| `config.py` | Load and validate configuration from environment |

---

Built with ❤️ using Google Gemini, pywinauto, and the ReAct paradigm.
