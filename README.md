# DjenisAiAgent

**Observable computer automation with explicit permission boundaries.**

[Project site](https://ejupi-djenis30.github.io/DjenisAiAgent/) · [Changelog](CHANGELOG.md) · [Support](SUPPORT.md) · [Security policy](SECURITY.md) · [Report an issue](https://github.com/ejupi-djenis30/DjenisAiAgent/issues)

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

File access is restricted by `DJENIS_ALLOWED_PATHS`; app launch is restricted by `DJENIS_ALLOWED_APPLICATIONS`; native program execution is restricted by `DJENIS_ALLOWED_SHELL_COMMANDS`. The execution tool does not invoke PowerShell or another command shell, and it rejects chaining, pipelines, substitutions, and multiline commands. Runtime and captured output are bounded by `DJENIS_SHELL_TIMEOUT` and `DJENIS_SHELL_OUTPUT_MAX_BYTES`. An allowlisted program can still perform any operation exposed by its own flags, so only add narrow diagnostic executables you trust. A denied tool call is a hard boundary, not a suggestion for the agent to find a workaround.

## Quick start: Windows

Requirements:

- Windows 10 or 11
- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/) 0.11.29 or a compatible release
- a Google Gemini API key
- Chrome or Edge only if you want DOM-level browser tools

```powershell
git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
Set-Location DjenisAiAgent
uv sync --frozen --extra dev --extra full
Copy-Item .env.example .env
```

Set `GEMINI_API_KEY` in `.env`. Keep `DJENIS_PERMISSION_TIER="observe"` while inspecting the project. Change it to `interact` when you intentionally want desktop or browser control.

Run one task:

```powershell
uv run --frozen --no-sync python .\main.py "Open Calculator and calculate 12 times 8"
```

Or start the interactive CLI:

```powershell
uv run --frozen --no-sync python .\main.py
```

## Local web console

Web mode refuses to start without an operator token of at least 24 characters. Generate one locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the result in `.env` as `DJENIS_WEB_AUTH_TOKEN`, then run:

```powershell
uv run --frozen --no-sync python .\main.py --web
```

Open `http://127.0.0.1:8000`. The page exchanges the operator token for a short-lived, opaque HttpOnly cookie. WebSocket commands, the screen stream, and audio uploads require that session. Logout revokes live sockets immediately. Requests are subject to same-origin checks, rate limits, bounded session/connection pools, pre-parse upload limits, and concurrency limits for expensive workers.

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

The versioned container uses SemVer tags without the Git tag's leading `v`:

```powershell
docker pull ghcr.io/ejupi-djenis30/djenis-ai-agent:0.2.1
```

The first authorization for a release fetches the exact remote tag and `origin/master` into isolated Git refs and requires their dereferenced commits to match. A new version is built and pushed by digest, never by alias. If a run already prepared a draft Release, a retry recovers its recorded digest even when no image alias exists yet. If the immutable full-version alias exists, it must agree with that authorization. This avoids pretending that two container builds of one commit must be byte-for-byte identical.

Trivy scans the selected digest and the workflow checks its SPDX SBOM and BuildKit SLSA provenance. Before reusing any remote digest, the workflow first verifies pre-existing GitHub OIDC provenance bound to this repository, workflow, source commit, and source ref; it never signs an untrusted reused digest into legitimacy. New digests are signed and every path is verified again. Only after those gates pass can the full (`0.2.1`), minor (`0.2`), and major (`0`) aliases change.

GitHub Release publication is a recoverable state machine: absent, exact draft authorization, then exact immutable publication. The repository's immutable-release setting is an external administrator gate because the workflow token cannot read that administrator endpoint. After provenance succeeds, the workflow creates or verifies the asset-free draft before changing aliases and records the authorized commit and Docker digest in its canonical body. Draft recovery uses the authenticated, fully paginated Release inventory because GitHub's tag lookup exposes published Releases only. The publisher permits one canonical SemVer draft at a time and rejects an older unfinished release after a newer version has published, preventing moving aliases from rolling backward.

Every mutation-time check freshly fetches the exact remote tag into an isolated ref and requires it to match both the event source and the durable authorization. Alias promotion also rereads the draft and its digest immediately before it writes. The final step publishes the same draft, fails closed unless GitHub reports `immutable: true`, and confirms a newly published Release is explicitly latest. A retry can therefore finish after `master` advances without weakening the original authorization. A completed Release rerun verifies only its immutable version alias and never rewrites the moving minor or major aliases; it does not demand that an older completed release remain latest forever.

Keep both repository release immutability and the checked-in [immutable release-tag ruleset](.github/rulesets/README.md) enabled. The settings make published Releases and their tags immutable, while the workflow's isolated remote-ref checks remain an independent fail-closed control before publication.

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
| `DJENIS_WEB_MAX_CONNECTIONS` | `8` | Maximum simultaneous authenticated WebSockets. |
| `DJENIS_WEB_STREAM_MAX_CLIENTS` | `2` | Maximum concurrent native desktop streams. |
| `DJENIS_API_TIMEOUT` | `120` | Per-request Gemini HTTP timeout in seconds. |
| `DJENIS_TASK_TIMEOUT` | `900` | Wall-clock limit for one operator task. |
| `DJENIS_OBSERVATION_MAX_CHARS` | `16384` | Maximum tool-result text retained in model context. |
| `DJENIS_AUDIT_LOG_MAX_BYTES` | `10485760` | Rotate the local JSONL audit log at this size. |

`config.safe_view()` redacts API and web tokens for diagnostics.

## Development

Install the development environment on Windows:

```powershell
uv sync --frozen --extra dev --extra full
uv run --frozen --no-sync pre-commit install
```

Run the same local gates used by CI:

```powershell
uv lock --check
uv run --frozen --no-sync ruff check src tests scripts main.py
uv run --frozen --no-sync ruff format --check src tests scripts main.py
uv run --frozen --no-sync mypy src scripts
uv run --frozen --no-sync pytest tests/unit
uv run --frozen --no-sync bandit -r src scripts main.py
uv run --frozen --no-sync pip-audit
uv run --frozen --no-sync python scripts/validate_site.py
uv run --frozen --no-sync python scripts/validate_release.py
actionlint
```

`uv.lock` freezes development and native-runtime dependencies across supported platforms. The CI workflow targets the repository's actual default branch, `master`. Portable tests run on Linux and Python 3.11/3.12; the full desktop-aware coverage suite runs on Windows. A separate workflow builds and smoke-tests the Docker image.

Docker installs from `requirements-docker.lock` with package hashes. Regenerate it only after reviewing dependency updates:

```powershell
uv pip compile requirements-docker.txt --output-file requirements-docker.lock --generate-hashes --python-version 3.12 --python-platform linux
```

## Repository map

```text
src/action/          permission checks and executable tools
src/orchestration/   bounded ReAct loop and cancellation
src/perception/      screenshots, UI snapshots, audio preprocessing
src/reasoning/       Gemini schemas, prompt, retries, response validation
web/static/          authenticated runtime dashboard
site/                public GitHub Pages presentation
scripts/             release state, workflow-contract, and project-site validators
tests/unit/          deterministic unit tests with mocked external services
```

The public project site and the runtime dashboard are deliberately separate. GitHub Pages never contains the operator console and cannot connect to a local agent by itself.

## Known limits

- The project is alpha software. Use it in a disposable or well-bounded environment first.
- UI automation depends on application accessibility quality and window focus.
- Cancellation can interrupt loop work and retry waits, but an in-flight third-party request remains bounded by its HTTP timeout. Timed-out transcription threads retain their worker slot until they actually exit.
- The bounded in-memory web session and rate limiter are designed for a single-process local control plane, not a multi-instance public service.
- Canvas-heavy interfaces may not expose enough structure for reliable control.

## License

[MIT](LICENSE) © Djenis Ejupi
