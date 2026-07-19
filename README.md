# DjenisAiAgent

**Observable computer automation with explicit permission boundaries.**

[Project site](https://ejupi-djenis30.github.io/DjenisAiAgent/) · [Watch the 9-second demo](site/media/djenis-ai-agent-demo.mp4) · [Security policy](SECURITY.md) · [Report an issue](https://github.com/ejupi-djenis30/DjenisAiAgent/issues)

DjenisAiAgent is an experimental agent that operates Windows applications and browser sessions through structured tool calls. It captures the current interface, asks Gemini for one action, executes that action through a permission-gated tool layer, and observes the result before continuing.

This repository is a working engineering project, not a claim of general computer autonomy. Native desktop control requires Windows. Docker provides the web control plane and remote Selenium tools, but it cannot control the host desktop or capture the host screen.

## How it works

```text
operator objective
      │
      ▼
perception ── screenshot + accessibility tree
      │
      ▼
reasoning ─── Gemini returns one declared function call
      │
      ▼
policy ────── runtime + permission tier + allowlists
      │
      ▼
action ────── desktop, browser, file, or system tool
      │
      └──────── observation feeds the next turn
```

The orchestration layer rejects unknown tools, bounds network retries and task duration, and requires a verified observation before `finish_task`. Audit events pass through a redaction layer before they reach disk.

## Capability matrix

| Capability | Windows native | Docker / remote Selenium |
| --- | --- | --- |
| Windows UI Automation and keyboard/mouse tools | Yes | No |
| Browser DOM tools | Local debugger | Remote Selenium |
| Host desktop screenshots and stream | Yes | No |
| Authenticated local web console | Yes | Yes |
| Optional local WAV transcription | Yes | Yes, with a mounted model |

The tool registry is built at runtime. Unsupported capabilities are omitted rather than advertised and allowed to fail later.

## Permission model

The safe default is `observe`.

| Tier | What it exposes |
| --- | --- |
| `observe` | Runtime checks and read-only file tools restricted to approved paths. |
| `interact` | Adds supported desktop and browser interaction tools. |
| `system` | Adds shell execution, file writes, app launch, saved screenshots, and window closing. |

System tools require two independent settings:

```env
DJENIS_PERMISSION_TIER="system"
DJENIS_CONFIRM_DANGEROUS_ACTIONS="true"
```

File access is restricted by `DJENIS_ALLOWED_PATHS`; app launch is restricted by `DJENIS_ALLOWED_APPLICATIONS`; shell entry points are restricted by `DJENIS_ALLOWED_SHELL_COMMANDS`. Shell chaining, pipelines, substitutions, and multiline commands are rejected. A denied tool call is a hard boundary, not a suggestion for the agent to find a workaround.

## Quick start: Windows

Requirements:

- Windows 10 or 11
- Python 3.11 or 3.12
- a Google Gemini API key
- Chrome or Edge only if you want DOM-level browser tools

```powershell
git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
Set-Location DjenisAiAgent
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,full]"
Copy-Item .env.example .env
```

Set `GEMINI_API_KEY` in `.env`. Keep `DJENIS_PERMISSION_TIER="observe"` while inspecting the project. Change it to `interact` when you intentionally want desktop or browser control.

Run one task:

```powershell
python .\main.py "Open Calculator and calculate 12 times 8"
```

Or start the interactive CLI:

```powershell
python .\main.py
```

## Local web console

Web mode refuses to start without an operator token of at least 24 characters. Generate one locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the result in `.env` as `DJENIS_WEB_AUTH_TOKEN`, then run:

```powershell
python .\main.py --web
```

Open `http://127.0.0.1:8000`. The page exchanges the operator token for a short-lived, opaque HttpOnly cookie. WebSocket commands, the screen stream, and audio uploads require that session. Requests are subject to same-origin checks, rate limits, and upload limits.

The server binds to `127.0.0.1` by default. If you deliberately expose it beyond the machine, use TLS, set `DJENIS_WEB_SESSION_COOKIE_SECURE=true`, and define exact `DJENIS_WEB_ALLOWED_ORIGINS` values.

## Browser setup

For browser DOM tools on Windows, launch a separate browser profile with remote debugging. Do not attach the agent to a profile that contains unrelated private sessions.

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:TEMP\djenis-agent-browser"
```

The default debugger address is `127.0.0.1:9222`. Override it with `DJENIS_BROWSER_DEBUGGING_HOST` and `DJENIS_BROWSER_DEBUGGING_PORT`.

## Docker

Docker mode is browser-oriented. It runs the authenticated web console and connects to a dedicated Selenium Chromium container. It does **not** provide Windows UI Automation or host display capture.

Set both required secrets in `.env`:

```env
GEMINI_API_KEY="your-key"
DJENIS_WEB_AUTH_TOKEN="a-random-value-with-at-least-24-characters"
```

Then start the stack:

```powershell
docker compose up --build
```

The console is available at `http://127.0.0.1:8008`. The published port is loopback-only. Compose defaults to the `interact` tier so remote browser tools are available; system tools remain locked.

## Configuration

`.env.example` is the canonical reference. Important settings include:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJENIS_GEMINI_MODEL` | `gemini-3.5-flash` | Model used for multimodal function calling. |
| `DJENIS_RUNTIME_MODE` | `auto` | Resolves to `windows`, `docker`, or `headless`. |
| `DJENIS_PERMISSION_TIER` | `observe` | Maximum capability tier exposed to Gemini. |
| `DJENIS_ALLOWED_PATHS` | current directory | Comma-separated roots for file tools. |
| `DJENIS_WEB_HOST` | `127.0.0.1` | Default web bind address. |
| `DJENIS_WEB_SESSION_TTL` | `3600` | Browser session lifetime in seconds. |
| `DJENIS_API_TIMEOUT` | `120` | Per-request Gemini HTTP timeout in seconds. |
| `DJENIS_TASK_TIMEOUT` | `900` | Wall-clock limit for one operator task. |

`config.safe_view()` redacts API and web tokens for diagnostics.

## Development

Install the development environment on Windows:

```powershell
pip install -e ".[dev,full]"
pre-commit install
```

Run the same local gates used by CI:

```powershell
ruff check src tests main.py
ruff format --check src tests main.py
mypy src
pytest tests/unit
bandit -r src
pip-audit
```

The CI workflow targets the repository's actual default branch, `master`. Portable tests run on Linux and Python 3.11/3.12; the full desktop-aware coverage suite runs on Windows. A separate workflow builds and smoke-tests the Docker image.

## Repository map

```text
src/action/          permission checks and executable tools
src/orchestration/   bounded ReAct loop and cancellation
src/perception/      screenshots, UI snapshots, audio preprocessing
src/reasoning/       Gemini schemas, prompt, retries, response validation
web/static/          authenticated runtime dashboard
site/                public GitHub Pages presentation
tests/unit/          deterministic unit tests with mocked external services
```

The public project site and the runtime dashboard are deliberately separate. GitHub Pages never contains the operator console and cannot connect to a local agent by itself.

## Known limits

- The project is alpha software. Use it in a disposable or well-bounded environment first.
- UI automation depends on application accessibility quality and window focus.
- Cancellation can interrupt loop work and retry waits, but an in-flight third-party request remains bounded by its HTTP timeout.
- The in-memory web session and rate limiter are designed for a single-process local control plane, not a multi-instance public service.
- Canvas-heavy interfaces may not expose enough structure for reliable control.

## License

[MIT](LICENSE) © Djenis Ejupi
