# DjenisAiAgent

DjenisAiAgent is a multimodal automation agent that observes the Windows desktop, reasons over the current UI state with Google Gemini, and executes actions through a structured tool layer. It is designed around the ReAct pattern and supports both native desktop automation and a web control surface with live status updates, streaming, and optional local audio transcription.

The project now includes a stronger engineering baseline: reproducible packaging with `pyproject.toml`, Docker support for web mode, GitHub Actions for CI/CD, a larger unit-test suite, and a coverage gate that runs on Windows where the desktop automation stack is actually available.

## What the project does

DjenisAiAgent combines four subsystems into one loop:

1. Perception captures a screenshot and a structured UI tree.
2. Reasoning sends that multimodal context to Gemini using function calling.
3. Action executes the selected tool against the current desktop or browser state.
4. Feedback records the observation so the next turn can self-correct.

This is useful for:

- Windows desktop automation driven by natural language.
- Browser automation when pywinauto cannot access DOM internals.
- Interactive experimentation with tool-calling agents.
- Building a local web control center around an LLM automation loop.

## Current capabilities

### Native Windows automation

- UI lookup with UIA first, then Win32 fallback.
- Click, double-click, right-click, typing, scrolling, keyboard shortcuts, and window management.
- Stable locator tokens via `element_id(...)` so later tool calls can target the same control.
- Timeout isolation for pywinauto operations to prevent the agent from hanging indefinitely.

### Browser-aware automation

- Selenium fallback for browser pages when desktop accessibility is insufficient.
- Browser search and focused text entry tools.
- Support for attaching to a browser started with remote debugging.

### Web mode

- FastAPI server with WebSocket command streaming.
- Live desktop video stream at `/stream`.
- Health endpoint at `/health` for Docker and CI smoke tests.
- Audio transcription endpoint at `/api/transcribe` when local transcription is enabled.

### Audio transcription

- Browser speech recognition first, when available.
- Optional local Vosk transcription fallback.
- WAV validation and sample-rate normalization before recognition.

### Developer ergonomics

- `ruff`, `mypy`, `pytest`, `pytest-cov`, `pre-commit`.
- Docker image and Docker Compose stack.
- GitHub Actions for linting, type checking, portable tests, Windows coverage gate, and Docker build smoke tests.

## Platform support

| Mode | Supported environment | Notes |
| --- | --- | --- |
| Native desktop automation | Windows | Full pywinauto + pyautogui support lives here. |
| Web control surface | Windows, Linux, Docker | FastAPI, WebSocket, health endpoint, streaming UI. |
| Browser automation | Windows native, Docker web mode | Docker is browser-oriented, not full desktop UI automation. |
| Local transcription | Any environment with Vosk model available | Requires `DJENIS_LOCAL_TRANSCRIPTION=1` and a valid model path. |

Important constraint: Docker does not provide native Windows desktop automation. The containerized setup is intended for web mode, browser automation, remote control, and API integration, not for interacting with arbitrary Windows desktop apps inside the container.

## Architecture

### High-level flow

```text
User command
	-> Perception (screenshot + UI tree)
	-> Reasoning (Gemini function calling)
	-> Action (desktop/browser/file/system tool)
	-> Observation/history update
	-> Next loop turn until finish_task or turn limit
```

### Main modules

| Path | Responsibility |
| --- | --- |
| `main.py` | Application entry point, CLI mode, web mode, FastAPI app, WebSocket endpoints, stream endpoint. |
| `src/config.py` | Environment loading, validation, profiles, defaults, safe logging view. |
| `src/perception/screen_capture.py` | Screenshot capture, UI tree extraction, snapshot caching, multimodal context assembly. |
| `src/perception/audio_transcription.py` | Local WAV preprocessing and Vosk-based transcription. |
| `src/reasoning/gemini_core.py` | Gemini setup, tool declaration generation, response validation, retry logic, system prompt loading. |
| `src/action/tools.py` | Desktop, browser, clipboard, shell, file, and task-completion tools. |
| `src/action/browser_tools.py` | Selenium attachment, lookup, typing, and URL inspection helpers. |
| `src/orchestration/agent_loop.py` | Main ReAct loop, retry behavior, cancellation flow, async queue processing. |
| `src/exceptions.py` | Central exception hierarchy for agent subsystems. |

### Why ReAct plus function calling

This repository does not rely on fragile prompt parsing. Gemini receives structured tool declarations and is expected to call exactly one tool per turn. The orchestration layer validates tool names, rejects invalid function calls, and feeds observations back into the next reasoning step. That keeps the loop inspectable and much more robust than free-form text agents.

## Repository layout

```text
.
├── .github/workflows/           # CI and Docker publish pipelines
├── Dockerfile                   # Multi-stage runtime image for web mode
├── docker-compose.yml           # Agent + Selenium Chrome stack
├── index.html                   # Web control center UI
├── main.py                      # CLI + FastAPI entry point
├── Makefile                     # Common dev commands
├── pyproject.toml               # Packaging, lint, type-check, pytest, coverage config
├── requirements.txt             # Baseline dependency list
├── requirements-docker.txt      # Minimal dependency set for container builds
├── src/
│   ├── action/
│   ├── orchestration/
│   ├── perception/
│   ├── reasoning/
│   ├── config.py
│   └── exceptions.py
└── tests/unit/                  # Unit tests for config, reasoning, orchestration, browser, audio, and screen helpers
```

## Quick start on Windows

### Prerequisites

- Windows 10 or Windows 11.
- Python 3.11 or 3.12 recommended.
- A valid Google Gemini API key.
- PowerShell.
- Optional: Chrome or Edge with remote debugging for browser fallback.

### 1. Create and activate a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2. Install dependencies

If you want the full local development setup:

```powershell
pip install -e ".[dev,windows,web,browser,transcription]"
```

If you only want the baseline runtime dependencies from the legacy requirements file:

```powershell
pip install -r requirements.txt
```

The editable install is preferred because it matches the tooling configured in `pyproject.toml` and the CI workflow.

### 3. Configure secrets

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and set at minimum:

```env
GEMINI_API_KEY="your-real-api-key"
```

### 4. Run in CLI mode

Single command mode:

```powershell
python .\main.py "open notepad and type hello world"
```

Interactive loop mode:

```powershell
python .\main.py
```

Interactive loop after an initial command:

```powershell
python .\main.py "open calculator" --interactive
```

### 5. Run in web mode

```powershell
python .\main.py --web --host 0.0.0.0 --port 8000
```

Available endpoints in web mode:

- `GET /` serves the web control center.
- `GET /health` returns status, version, uptime, and current agent state.
- `GET /stream` returns a multipart JPEG live desktop stream.
- `POST /api/transcribe` accepts WAV audio for local transcription when enabled.
- `WS /ws` accepts commands, cancellations, and task deletion messages.

## Browser automation setup

Desktop accessibility does not expose modern web pages well. For serious browser work, start Chrome or Edge with remote debugging enabled before running the agent.

### Microsoft Edge

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222
```

### Google Chrome

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

Once the browser is running with port `9222`, the browser tool layer can attach and use DOM-level interactions where needed.

## Docker usage

### What Docker is good for here

The Docker setup is intended for:

- Running the FastAPI server.
- Serving the web UI.
- Exposing `/health`, `/stream`, and WebSocket control endpoints.
- Driving browser automation through Selenium in a Linux container.

The Docker setup is not intended for native Windows desktop automation.

### Build the image

```powershell
docker build -t djenis-ai-agent:latest .
```

### Run the image directly

```powershell
docker run --rm -p 8000:8000 -e GEMINI_API_KEY=your_key djenis-ai-agent:latest
```

### Run the compose stack

```powershell
docker compose up --build
```

The compose stack starts:

- `djenis-agent`, the FastAPI web service.
- `chrome`, a Selenium standalone Chrome container.

### Published images

The Docker publish workflow pushes tagged and `latest` images to GHCR:

```bash
docker pull ghcr.io/ejupi/djenis-ai-agent:latest
```

For tagged releases:

```bash
docker pull ghcr.io/ejupi/djenis-ai-agent:v0.1.0
```

## Command-line options

`main.py` currently supports these flags:

| Argument | Description |
| --- | --- |
| `command` | Optional natural-language command for one-shot CLI execution. |
| `--interactive` | Forces the continuous CLI loop. |
| `--web` | Starts FastAPI + WebSocket mode instead of CLI mode. |
| `--host` | Web server bind address. Default: `0.0.0.0`. |
| `--port` | Web server port. Default: `8000`. |
| `--no-ui` | Reserved compatibility flag for headless scenarios. |

## Tool inventory

The action layer contains many tools. The most important categories are below.

### Desktop and UI tools

- `element_id`
- `element_id_fast`
- `click`
- `double_click`
- `right_click`
- `type_text`
- `get_text`
- `scroll`
- `move_mouse`
- `verify_mouse_position`
- `confirm_mouse_position`
- `switch_window`
- `maximize_window`
- `close_window`

### Keyboard and timing tools

- `press_key_repeat`
- `press_keys`
- `hotkey`
- `wait_seconds`

### Browser tools

- `browser_search`
- Selenium-backed helpers in `src/action/browser_tools.py`

### Clipboard and system tools

- `copy_to_clipboard`
- `paste_from_clipboard`
- `read_clipboard`
- `set_clipboard_text`
- `run_shell_command`

### File and app tools

- `start_application`
- `open_file`
- `open_url`
- `take_screenshot`
- `list_files`
- `read_file`
- `write_file`

### Reasoning and lifecycle tools

- `deep_think`
- `finish_task`

## Configuration reference

All configuration is loaded from environment variables or `.env`. Existing process environment variables win over values inside `.env`.

### Core agent and model settings

| Variable | Default | Description |
| --- | --- | --- |
| `GEMINI_API_KEY` | required | Gemini API key. The application refuses to start if this is missing or a placeholder. |
| `DJENIS_GEMINI_MODEL` | `gemini-1.5-pro-latest` | Model name passed to Gemini. |
| `DJENIS_MAX_LOOP_TURNS` | `50` | Maximum number of ReAct turns before the task is marked as failed. |
| `DJENIS_MAX_MOUSE_POSITIONING_ATTEMPTS` | `10` | Maximum mouse mini-loop retries. |
| `DJENIS_ACTION_TIMEOUT` | `45` | Timeout budget for interactive actions. |
| `DJENIS_TEMPERATURE` | `0.7` | Generation temperature. |
| `DJENIS_MAX_TOKENS` | `60096` | Maximum output token budget. |

### API resilience settings

| Variable | Default | Description |
| --- | --- | --- |
| `DJENIS_API_TIMEOUT` | `120` | Gemini API timeout budget. |
| `DJENIS_API_MAX_RETRIES` | `3` | Retry attempts for transient API failures. |
| `DJENIS_API_RETRY_DELAY` | `2.0` | Base retry delay used for backoff. |

### Logging and streaming settings

| Variable | Default | Description |
| --- | --- | --- |
| `DJENIS_LOG_LEVEL` | `INFO` | Python logging level. |
| `DJENIS_VERBOSE_LOGGING` | `false` | Enables more verbose diagnostic behavior. |
| `DJENIS_STREAM_RESIZE_FACTOR` | `1.0` | Resize factor for streamed frames. |
| `DJENIS_STREAM_FRAME_QUALITY` | `80` | JPEG quality for streamed frames. |
| `DJENIS_STREAM_MAX_FPS` | `30` | Maximum stream FPS. |
| `DJENIS_PERCEPTION_DOWNSCALE` | `1.0` | Downscale factor used during perception. |

### Screenshot and UI snapshot settings

| Variable | Default | Description |
| --- | --- | --- |
| `DJENIS_SCREENSHOT_INTERVAL` | `0.1` | Delay between perception captures in some modes. |
| `DJENIS_SCREENSHOT_QUALITY` | `100` | Image quality for screenshots. |
| `DJENIS_SCREENSHOT_FORMAT` | `PNG` | Screenshot serialization format. |
| `DJENIS_SNAPSHOT_DEPTH` | `4` | Maximum UI tree traversal depth. |
| `DJENIS_LOCATOR_CACHE_SIZE` | `64` | LRU cache size for stable locator tokens. |

### Shell, clipboard, and transcription settings

| Variable | Default | Description |
| --- | --- | --- |
| `DJENIS_SHELL_TIMEOUT` | `60` | Timeout for PowerShell commands executed by the agent. |
| `DJENIS_CLIPBOARD_MAX_BYTES` | `1048576` | Max clipboard payload returned to the model. |
| `DJENIS_LOCAL_TRANSCRIPTION` | `false` | Enables local Vosk fallback transcription. |
| `DJENIS_VOSK_MODEL_PATH` | empty | Required when local transcription is enabled. |
| `DJENIS_TRANSCRIPTION_SAMPLE_RATE` | `16000` | Target sample rate for WAV normalization. |

### Profiles

| Variable | Default | Description |
| --- | --- | --- |
| `DJENIS_PROFILE` | `default` | `performance`, `turbo`, `fast`, `quality`, and `hires` adjust multiple capture/stream settings together. |

### Example `.env`

```env
GEMINI_API_KEY="your-real-key"
DJENIS_GEMINI_MODEL="gemini-1.5-pro-latest"
DJENIS_MAX_LOOP_TURNS="50"
DJENIS_ACTION_TIMEOUT="45"
DJENIS_LOG_LEVEL="INFO"
DJENIS_STREAM_MAX_FPS="15"
DJENIS_LOCAL_TRANSCRIPTION="0"
```

## Development workflow

### Preferred install for contributors

```powershell
pip install -e ".[dev,windows,web,browser,transcription]"
pre-commit install
```

### Common commands

If you use the `Makefile`:

```bash
make lint
make type-check
make test
make test-cov
make docker-build
make docker-up
```

Equivalent direct commands:

```powershell
ruff check src tests main.py
ruff format --check src tests main.py
mypy src
pytest tests/unit -q
pytest tests/unit --cov=src --cov-report=term-missing
```

## Testing and coverage

The unit suite now covers:

- configuration loading and validation,
- Gemini schema generation and response handling,
- audio transcription preprocessing and recognition flow,
- browser tool lifecycle and Selenium fallback behavior,
- orchestration loop helpers and cancellation paths,
- screen snapshot formatting and cache behavior,
- exception hierarchy behavior.

Run the local unit suite:

```powershell
pytest tests/unit -q
```

Run the coverage suite:

```powershell
pytest tests/unit --cov=src --cov-report=term-missing --cov-report=html
```

Coverage is enforced in CI on Windows, where the desktop automation dependencies are available. At the time of this rewrite, the local suite reaches more than 50% coverage on `src/`.

## CI/CD

### CI workflow

The `CI` workflow now includes:

1. Ruff lint and formatting checks.
2. Mypy type checking.
3. Portable unit tests on Ubuntu for cross-platform modules.
4. A Windows coverage gate that runs the full unit suite and uploads artifacts.
5. A Docker build plus `/health` smoke test.

This split matters because some agent capabilities are genuinely Windows-specific, while others can and should be validated on Linux too.

### Docker publish workflow

The `Docker Publish` workflow:

1. Builds on pushes to `main` and on `v*` tags.
2. Publishes images to GHCR.
3. Tags `main` as `latest` and also emits `sha-*` tags.
4. Creates a GitHub Release automatically for version tags.

## Troubleshooting

### `GEMINI_API_KEY not set`

Create `.env` from `.env.example` and set a real Gemini API key. Placeholder values are rejected during startup.

### Browser actions are failing

Make sure the browser was launched with `--remote-debugging-port=9222`. Without that, Selenium cannot attach to the existing session.

### The agent cannot find a UI element

- Make sure the correct window is active.
- Increase `DJENIS_ACTION_TIMEOUT` for slower apps.
- Use broader queries first, then rely on `element_id` tokens for subsequent actions.
- For websites, prefer browser-aware flows over pure desktop UI access.

### Docker container starts but desktop automation does not work

That is expected. Docker mode is for web mode and browser automation. Native Windows desktop interaction must run on a Windows host.

### Local transcription does not work

- Install the transcription dependency set.
- Set `DJENIS_LOCAL_TRANSCRIPTION=1`.
- Point `DJENIS_VOSK_MODEL_PATH` to an extracted model directory.
- Send valid WAV audio to `/api/transcribe`.

### Coverage passes locally on Windows but not on Linux

The full coverage gate is designed for Windows because desktop automation dependencies live there. Portable Linux tests intentionally cover the cross-platform subset.

## Security and operational notes

- Never commit `.env`.
- Do not log raw API keys; use `config.safe_view()` when printing config.
- The shell tool is powerful. Treat model prompts and agent objectives as privileged input.
- Clipboard output is size-limited to reduce accidental data exposure.
- Docker images should receive secrets via environment variables or a secret manager, not baked into the image.

## Known limitations

- Native desktop automation is Windows-only.
- Browser DOM automation requires a debuggable browser session.
- The Gemini integration now depends on `google-genai`; keep an eye on upstream release notes because the SDK is evolving quickly.
- Very dynamic or canvas-heavy UIs may still require fallback or more explicit targeting.

## Suggested next improvements

- Add integration tests against a deterministic demo app.
- Add contract tests around Gemini response shapes and tool-calling behavior.
- Expand typed interfaces for tool payloads and WebSocket events.
- Add screenshots and an architecture diagram to the repository wiki or docs folder.

## License

This repository is configured with an MIT license
