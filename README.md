# DjenisAiAgent

**Local-first computer automation with explicit permission and evidence boundaries.**

[Project site](https://ejupi-djenis30.github.io/DjenisAiAgent/) · [Changelog](CHANGELOG.md) · [Threat model](docs/THREAT_MODEL.md) · [Security policy](SECURITY.md) · [Support](SUPPORT.md) · [Report an issue](https://github.com/ejupi-djenis30/DjenisAiAgent/issues)

DjenisAiAgent is an experimental agent that operates Windows applications and isolated
browser sessions through structured tool calls. Perception, planning, tool selection,
and verification stay under the operator's control: reasoning is served by a local
Ollama or OpenAI-compatible endpoint, with no hosted-provider credentials, remote-model
fallback, or automatic model download.

This is a working engineering project, not a claim of general computer autonomy.
Native desktop control requires Windows. Docker provides the web control plane behind an
unprivileged loopback gateway, a local Ollama sidecar, and remote Selenium tools; it
cannot control or capture the host desktop.

## How it works

```text
operator objective
      │
      ▼
perception ── screenshot + accessibility/browser snapshot
      │
      ▼
local model ─ exactly one declared function call
      │
      ▼
policy ────── runtime + permission tier + allowlists
      │
      ▼
action ────── desktop, browser, file, or system tool
      │
      └──────── fresh observation verifies the next turn
```

The model is an untrusted planner. The host rejects unknown tools and malformed
arguments, bounds retries, total task duration, and repeated actions, and validates
evidence before accepting a terminal outcome. Audit events pass through a redaction
layer before they reach disk.

## Precision contract

Accuracy is enforced in code, not left entirely to prompting:

- The system policy and real Python signatures become strict function schemas. The
  response must contain exactly one declared call and no mixed prose.
- Unknown properties, missing arguments, wrong types, duplicate JSON keys,
  non-finite values, oversized responses, and unexpected model identities fail closed.
- The host tracks observed state and stops identical actions against an unchanged
  frame before they become an unbounded side-effect loop.
- `finish_task` has distinct `completed` and `blocked` outcomes. Completion evidence
  must be grounded in the current UI or a compatible read tool and preserve the
  objective's identities, values, destinations, and polarity.
- After a state-changing action, success requires a fresh changed perception or an
  explicit resource-scoped read verification. An acknowledgement alone is not proof.
- Native Ollama preflight verifies the runtime, exact local model identifier, digest
  shape, tool support, and vision support when vision is enabled. Pinning
  `DJENIS_LOCAL_LLM_EXPECTED_DIGEST` additionally requires the artifact's full SHA-256
  to match. It also rejects models whose declared context is shorter than
  `DJENIS_LOCAL_LLM_CONTEXT_TOKENS`. A missing or incompatible model blocks CLI startup
  and web readiness; it is never downloaded.

## Local-only inference boundary

`DJENIS_LOCAL_LLM_ENDPOINT` accepts only plain HTTP on loopback (`127.0.0.1`, `::1`, or
`localhost`) or a fixed internal Docker service name in Docker mode. Credentials,
query strings, fragments, redirects, proxy environment variables, and public endpoints
are rejected or ignored. The client places a total deadline and byte limit around each
request.

The default backend is Ollama with `qwen3-vl:8b`. It uses Ollama's native
[`/api/chat`](https://docs.ollama.com/api/chat) tool-calling interface. The optional
`openai-compatible` backend targets a local `/v1` server such as
[llama.cpp's HTTP server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).
In either mode, the configured model must already be present and must support both
function calling and images for the default multimodal workflow.

Local-only inference does **not** make browser tasks offline. A browser must still reach
the public sites the operator asks it to visit. In Docker, the long-running agent and
Ollama containers stay exclusively on an internal control network. Selenium Chrome also
joins a browser-egress network. A small hardened gateway joins control plus a separate
ingress network and is the only service publishing a host port. The explicit
provisioning profile gives a temporary model process download egress.

## Capability matrix

| Capability | Windows native | Docker / remote Selenium |
| --- | --- | --- |
| Windows UI Automation and keyboard/mouse tools | Yes | No |
| Browser DOM tools | Local debugger | Remote Selenium |
| Host desktop screenshots and stream | Yes | No |
| Authenticated local web console | Yes | Yes |
| Local model endpoint | Loopback process | Internal Ollama sidecar |
| Optional local WAV transcription | Yes | Yes, with a mounted model |

The tool registry is built at runtime. Unsupported capabilities are omitted rather
than advertised and allowed to fail later.

## Permission model

The safe default is `observe`.

| Tier | What it exposes |
| --- | --- |
| `observe` | Runtime checks and read-only file tools restricted to approved paths. |
| `interact` | Adds supported desktop and browser interaction tools. |
| `system` | Adds native process execution, file writes, app launch, saved screenshots, and window closing. |

System tools require two independent settings:

```env
DJENIS_PERMISSION_TIER="system"
DJENIS_CONFIRM_DANGEROUS_ACTIONS="true"
```

File access is restricted by `DJENIS_ALLOWED_PATHS`; app launch by
`DJENIS_ALLOWED_APPLICATIONS`; and native program execution by
`DJENIS_ALLOWED_SHELL_COMMANDS`. Executable allowlists contain absolute paths. The
host launches the configured executable directly, never searches `PATH`, never routes
model output through a command shell, and supplies a minimal child environment.
Only allowlist narrow programs you trust.

Browser navigation accepts only HTTP(S). A destination must resolve exclusively to
public addresses unless its exact private/local hostname is in
`DJENIS_ALLOWED_URL_HOSTS`. Explicit targets and current/redirect destinations are
rechecked. Application checks complement, but do not replace, network egress policy.

## Quick start: Windows

Requirements:

- Windows 10 or 11
- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/) 0.11.29 or a compatible release
- [Ollama](https://docs.ollama.com/) or a local OpenAI-compatible server
- Chrome or Edge only for DOM-level browser tools

Start the local runtime in one terminal:

```powershell
$env:OLLAMA_NO_CLOUD = "1"
ollama serve
```

Then provision the default model explicitly from a second terminal:

```powershell
ollama pull qwen3-vl:8b
ollama list
```

If the desktop Ollama application is already serving the endpoint, configure
`OLLAMA_NO_CLOUD=1` in that process's environment and restart it before provisioning.
`ollama list` must show the exact model identifier.

Set up DjenisAiAgent in another terminal:

```powershell
git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
Set-Location DjenisAiAgent
uv sync --frozen --extra dev --extra full
Copy-Item .env.example .env
```

The defaults in `.env.example` connect to `http://127.0.0.1:11434` and select
`qwen3-vl:8b`. Keep `DJENIS_PERMISSION_TIER="observe"` while inspecting the project;
change it to `interact` only when you intend to allow desktop or browser control.

The default 65,536-token context follows
[Ollama's guidance for agent workloads](https://docs.ollama.com/context-length) and
preserves a long objective, UI structure, recent actions, and postcondition evidence
in one reasoning window. Ollama receives it as `num_ctx`. KV-cache memory grows with
context length, so hardware-limited systems can reduce
`DJENIS_LOCAL_LLM_CONTEXT_TOKENS` deliberately (minimum `4096`). Doing so reduces memory
pressure but also shortens retained evidence and can lower precision; choose a value
the exact model declares as supported.

Run one task:

```powershell
uv run --frozen --no-sync python .\main.py "Open Calculator and calculate 12 times 8"
```

Or start the interactive CLI:

```powershell
uv run --frozen --no-sync python .\main.py
```

CLI startup performs a fail-closed local-runtime preflight. Web mode starts its
liveness endpoint independently but keeps `/ready` false until the same preflight
passes. Neither mode pulls a missing model, switches endpoints, or contacts a hosted
inference service.

After the first provisioning from a trusted source, obtain the full lowercase SHA-256
from Ollama's [`/api/tags`](https://docs.ollama.com/api/tags) response:

```powershell
((Invoke-RestMethod "http://127.0.0.1:11434/api/tags").models |
  Where-Object name -eq "qwen3-vl:8b").digest
```

Copy it into `DJENIS_LOCAL_LLM_EXPECTED_DIGEST`. This optional pin is recommended for
reproducible runs and detects an artifact change behind the same model name. It applies
only to the native `ollama` backend.

### Local OpenAI-compatible server

Use a loopback server whose model supports image input and function tools. For example,
after starting a compatible llama.cpp server on port `8080`:

```env
DJENIS_LOCAL_LLM_BACKEND="openai-compatible"
DJENIS_LOCAL_LLM_ENDPOINT="http://127.0.0.1:8080/v1"
DJENIS_LOCAL_LLM_MODEL="the-exact-local-model-id"
```

The endpoint must expose `/v1/models` and `/v1/chat/completions`. There is no API-key
setting because authenticated or remote inference endpoints are outside this project's
local-only contract.

## Local web console

Web mode refuses to start without an operator token of at least 24 characters. Generate
one locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put it in `.env` as `DJENIS_WEB_AUTH_TOKEN`, then run:

```powershell
uv run --frozen --no-sync python .\main.py --web
```

Open `http://127.0.0.1:8000`. The page exchanges the operator token for a short-lived,
opaque HttpOnly cookie. WebSocket commands, the screen stream, and audio uploads require
that session. Logout revokes live sockets immediately.

Optional Vosk transcription accepts complete mono or stereo 16-bit PCM WAV files at
8–192 kHz. Clips are limited to 120 seconds by default through
`DJENIS_TRANSCRIPTION_MAX_DURATION_SECONDS` (1–600); the output sample rate is limited
to 8–48 kHz. Duration, frame integrity and upload size are checked before resampling
or loading the model, so a small WAV cannot request unbounded decoded audio. Invalid
clips return a client error and release the worker slot.

Two unauthenticated probe endpoints have deliberately different meanings:

- `GET /health` is process liveness. It does not contact or load the model.
- `GET /ready` verifies that configuration and the selected local runtime/model are
  ready to reason. Use this endpoint for traffic readiness and diagnostics.

The server binds to `127.0.0.1` by default. If you deliberately expose it beyond the
machine, add TLS, enable secure cookies, define exact allowed origins, and enforce an
external access policy.

## Browser setup

For browser DOM tools on Windows, launch a separate browser profile with remote
debugging. Do not attach the agent to a profile containing unrelated private sessions.

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:TEMP\djenis-agent-browser"
```

The default debugger address is `127.0.0.1:9222`. Override it with
`DJENIS_BROWSER_DEBUGGING_HOST` and `DJENIS_BROWSER_DEBUGGING_PORT`.

## Docker

Docker mode is browser-oriented. It runs the authenticated web console, a pinned Ollama
sidecar, a dedicated Selenium Chromium container, and an unprivileged NGINX gateway. It
does **not** expose the agent or Ollama directly and does **not** provide Windows UI
Automation or host display capture.

1. Create `.env`, set a unique web operator secret, and keep the permission tier at
   its safe default:

   ```env
   DJENIS_WEB_AUTH_TOKEN="a-random-value-with-at-least-24-characters"
   DJENIS_LOCAL_LLM_MODEL="qwen3-vl:8b"
   DJENIS_LOCAL_LLM_EXPECTED_DIGEST=""
   DJENIS_LOCAL_LLM_CONTEXT_TOKENS="65536"
   DJENIS_PERMISSION_TIER="observe"
   ```

2. Populate the named model volume with the opt-in provisioning profile:

   ```powershell
   docker compose --profile provision run --rm ollama-provision
   ```

   This is the only Compose path that attaches a model process to an egress-capable
   network. It exits after the explicit pull. Do not run it while the normal Ollama
   service is using the same volume.

3. Start the runtime:

   ```powershell
   docker compose up --build -d
   Invoke-RestMethod http://127.0.0.1:8008/ready
   ```

The console is at `http://127.0.0.1:8008`. That loopback port belongs only to the
digest-pinned `nginxinc/nginx-unprivileged:1.30.0-alpine` gateway. It forwards HTTP,
WebSocket commands, the multipart screen stream, and bounded transcription uploads to
the agent across `djenis-control`; the agent itself has no published port. Compose
starts at `observe`, matching the image, `.env.example`, and the application default.
At that tier the agent can inspect approved state but cannot click, type, or navigate.

Elevate only when a browser task needs clicks, typing, or navigation, and only after
`/ready` reports `status: ready`. Keep `interact` out of `.env`: the recreated
container retains its tier across agent, Docker daemon, and host restarts until you
explicitly reset it. First verify that Compose still resolves the safe default, then
recreate only the agent:

```powershell
if (Test-Path Env:DJENIS_PERMISSION_TIER) {
    throw "Clear DJENIS_PERMISSION_TIER from this shell before changing the tier."
}
$composeJson = docker compose config --format json
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose could not resolve the deployment."
}
$tierLine = @($composeJson | Select-String -Pattern '^\s*"DJENIS_PERMISSION_TIER":\s*"(?<tier>[^"]+)"[,]?\s*$')
if ($tierLine.Count -ne 1 -or $tierLine[0].Matches[0].Groups["tier"].Value -ne "observe") {
    throw "Keep DJENIS_PERMISSION_TIER absent or set to observe in .env."
}
$env:DJENIS_PERMISSION_TIER = "interact"
try {
    docker compose up -d --no-deps --force-recreate --wait --wait-timeout 120 djenis-agent
    if ($LASTEXITCODE -ne 0) {
        throw "The interact container was not recreated successfully."
    }
    $containerJson = docker inspect --format "{{json .Config.Env}}" djenis-agent
    if ($LASTEXITCODE -ne 0) {
        throw "The recreated agent container could not be inspected."
    }
    $containerTier = ($containerJson | ConvertFrom-Json |
        Where-Object { $_ -like "DJENIS_PERMISSION_TIER=*" })
    if ($containerTier -ne "DJENIS_PERMISSION_TIER=interact") {
        throw "The recreated agent is not running at the requested interact tier."
    }
    $readiness = Invoke-RestMethod http://127.0.0.1:8008/ready
    if ($readiness.status -ne "ready") {
        throw "The recreated interact agent is not ready."
    }
} finally {
    Remove-Item Env:DJENIS_PERMISSION_TIER
}
```

This enables the existing `interact` tools; it does not unlock `system` tools.
Readiness is checked after the new agent starts, not against the previous process.
If any command after `docker compose up` fails, assume that the `interact` container
is still active and run the reset block below before continuing.
When the browser task is finished, reset immediately and verify both the recreated
agent and the default that future Compose runs will use:

```powershell
$env:DJENIS_PERMISSION_TIER = "observe"
try {
    docker compose up -d --no-deps --force-recreate --wait --wait-timeout 120 djenis-agent
    if ($LASTEXITCODE -ne 0) {
        throw "The observe container was not recreated successfully; treat the runtime as elevated."
    }
    $containerJson = docker inspect --format "{{json .Config.Env}}" djenis-agent
    if ($LASTEXITCODE -ne 0) {
        throw "The recreated agent container could not be inspected."
    }
    $containerTier = ($containerJson | ConvertFrom-Json |
        Where-Object { $_ -like "DJENIS_PERMISSION_TIER=*" })
    if ($containerTier -ne "DJENIS_PERMISSION_TIER=observe") {
        throw "The recreated agent is not running at the safe observe tier."
    }
    $readiness = Invoke-RestMethod http://127.0.0.1:8008/ready
    if ($readiness.status -ne "ready") {
        throw "The recreated observe agent is not ready."
    }
} finally {
    Remove-Item Env:DJENIS_PERMISSION_TIER
}
$composeJson = docker compose config --format json
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose could not resolve the deployment after the reset."
}
$tierLine = @($composeJson | Select-String -Pattern '^\s*"DJENIS_PERMISSION_TIER":\s*"(?<tier>[^"]+)"[,]?\s*$')
if ($tierLine.Count -ne 1 -or $tierLine[0].Matches[0].Groups["tier"].Value -ne "observe") {
    throw "Correct DJENIS_PERMISSION_TIER in .env before the next Compose run."
}
```

`docker compose up` never starts the provisioning service. Long-running Ollama has
`OLLAMA_NO_CLOUD=1`, no published port, and no egress-capable network. If the selected
model is absent or incompatible, readiness fails instead of downloading or falling
back. Gateway health checks proxy `/health`; traffic admission should still use
`/ready`.

For a reproducible deployment, start once after trusted provisioning, read the full
digest from Ollama's `/api/tags` response on the internal control network, set
`DJENIS_LOCAL_LLM_EXPECTED_DIGEST`, and recreate the agent container. Subsequent
readiness checks then fail if the named artifact changes.

```powershell
docker compose exec djenis-agent python -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://ollama:11434/api/tags')); print(next(item['digest'] for item in data['models'] if item['name']=='qwen3-vl:8b'))"
```

For GPU acceleration, add a local Compose override appropriate for the host runtime;
do not weaken the network split or publish the Ollama port. The 65,536-token default can
require substantial KV-cache memory even when model weights fit; lower
`DJENIS_LOCAL_LLM_CONTEXT_TOKENS` consciously when the target hardware cannot sustain
it, and re-run readiness to verify the model contract.

### Container releases

The versioned agent image uses SemVer tags without the Git tag's leading `v`:

```powershell
docker pull ghcr.io/ejupi-djenis30/djenis-ai-agent:0.3.0
```

Every push to `master` updates only `edge` and its commit-specific `sha-*` alias. A
signed version tag promotes one verified digest to `latest`, the full version, minor
line, and major line. Release authorization requires the annotated, SSH-signed tag and
`origin/master` to resolve to the same commit. Builds are pushed by digest; Trivy, SPDX
SBOM, provenance, signature verification, draft authorization, and immutable Release
checks gate alias promotion. See [AGENT.md](AGENT.md) and the checked-in
[release-tag ruleset](.github/rulesets/README.md) for the maintenance contract.
The complete operator-facing changes from `v0.2.2` are recorded in the
[v0.3.0 release notes](docs/releases/v0.3.0.md).

## Configuration

`.env.example` is the canonical reference. Important settings include:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJENIS_LOCAL_LLM_BACKEND` | `ollama` | `ollama` or `openai-compatible`. |
| `DJENIS_LOCAL_LLM_ENDPOINT` | `http://127.0.0.1:11434` | Loopback or fixed internal Docker endpoint. |
| `DJENIS_LOCAL_LLM_MODEL` | `qwen3-vl:8b` | Exact pre-provisioned local model identifier. |
| `DJENIS_LOCAL_LLM_EXPECTED_DIGEST` | empty | Optional full Ollama artifact SHA-256 pin; recommended after provisioning. |
| `DJENIS_LOCAL_LLM_CONTEXT_TOKENS` | `65536` | Requested Ollama context; more retained evidence costs more KV-cache memory. |
| `DJENIS_LOCAL_LLM_VISION` | `true` | Require and send bounded screenshot input. |
| `DJENIS_LOCAL_LLM_KEEP_ALIVE` | `10m` | Ollama model residency requested per call. |
| `DJENIS_LOCAL_LLM_SEED` | `0` | Deterministic sampling seed where supported. |
| `DJENIS_LOCAL_LLM_RESPONSE_MAX_BYTES` | `1048576` | Maximum JSON response body. |
| `DJENIS_LOCAL_LLM_IMAGE_MAX_BYTES` | `5242880` | Maximum encoded reasoning image. |
| `DJENIS_RUNTIME_MODE` | `auto` | Resolves to `windows`, `docker`, or `headless`. |
| `DJENIS_PERMISSION_TIER` | `observe` | Maximum capability tier exposed to the planner. |
| `DJENIS_ALLOWED_PATHS` | current directory | Comma-separated roots for file tools. |
| `DJENIS_ALLOWED_URL_HOSTS` | empty | Exact private/local hosts allowed for browser navigation. |
| `DJENIS_WEB_HOST` | `127.0.0.1` | Default web bind address. |
| `DJENIS_API_TIMEOUT` | `120` | Total local reasoning request timeout in seconds. |
| `DJENIS_TASK_TIMEOUT` | `900` | Wall-clock limit for one operator task. |
| `DJENIS_TOOL_ARGUMENT_MAX_CHARS` | `16384` | Maximum serialized argument payload per call. |
| `DJENIS_MAX_REPEATED_ACTIONS` | `2` | Identical attempts allowed on unchanged state. |
| `DJENIS_AUDIT_LOG_MAX_BYTES` | `10485760` | Rotate the local JSONL audit log at this size. |

`config.safe_view()` omits or redacts security-sensitive values for diagnostics.

## Development

Install the locked development environment:

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

`uv.lock` freezes development and native dependencies across supported platforms.
Portable tests run on Linux and Python 3.11/3.12; the desktop-aware coverage suite runs
on Windows. A separate workflow builds and smoke-tests the Docker image.

Docker installs from `requirements-docker.lock` with package hashes. Regenerate it only
after reviewing dependency updates:

```powershell
uv pip compile requirements-docker.txt --output-file requirements-docker.lock --generate-hashes --python-version 3.12 --python-platform linux
```

## Repository map

```text
src/action/          permission checks and executable tools
src/orchestration/   bounded ReAct loop, evidence guard, and cancellation
src/perception/      screenshots, UI snapshots, audio preprocessing
src/reasoning/       local HTTP backends, schemas, prompt, and response validation
deploy/              hardened reverse-proxy configuration for container ingress
web/static/          authenticated runtime dashboard
site/                public GitHub Pages presentation
scripts/             release, workflow-contract, and project-site validators
tests/unit/          deterministic unit tests with mocked local runtimes
```

The public project site and runtime dashboard are deliberately separate. GitHub Pages
does not contain the operator console and cannot connect to a local agent by itself.

## Known limits

- This is alpha software. Start in a disposable or tightly bounded environment.
- Local HTTP is a deployment boundary, not process attestation. A malicious process
  already controlling the configured loopback port can observe prompts and images.
- Model quality and tool-call reliability depend on the exact local artifact, template,
  quantization, available memory, and runtime version.
- Screenshots are not automatically redacted. They stay within the configured local
  inference process but can contain any data visible on the controlled display.
- Browser egress, pages, downloads, and accounts remain external to the inference
  boundary. Use a dedicated browser profile and network controls.
- UI automation depends on application accessibility quality and window focus.
- The in-memory web session and rate limiter target a single-process local control
  plane, not a multi-instance public service.
- Canvas-heavy interfaces may not expose enough structure for reliable control.

## License

[MIT](LICENSE) © Ejupi Labs and DjenisAiAgent contributors
