# DjenisAiAgent Developer Guide

## Architecture

DjenisAiAgent is a multimodal automation agent built around a bounded
perceive–reason–act–verify loop:

1. Perception captures a screenshot plus a structured desktop or browser snapshot.
2. A pre-provisioned local model selects exactly one declared function.
3. Host policy validates the call against runtime capabilities, permission tier,
   allowlists, types, sizes, and current state.
4. The action layer executes it and records a fresh observation.
5. The evidence guard accepts a terminal result only when the observed postcondition
   supports it.

There are two runtime modes:

- Windows native mode provides desktop automation, local browser attachment, and
  host-screen capture.
- Web/Docker mode provides the authenticated control plane and browser DOM control
  through remote Selenium. It cannot automate or capture the host desktop.

Inference is always local. The supported backends are native Ollama and a loopback
OpenAI-compatible `/v1` server. There are no provider API keys, remote-model fallback,
or runtime model downloads.

## Core modules

| Path | Responsibility |
| --- | --- |
| `main.py` | CLI entry point, FastAPI app, WebSocket command flow, liveness, and readiness. |
| `src/orchestration/agent_loop.py` | Main task loop, cancellation, reasoning failures, and tool dispatch. |
| `src/orchestration/execution_guard.py` | Strict arguments, stagnation detection, and evidence-based terminal validation. |
| `src/reasoning/local_llm.py` | Local HTTP transports, schemas, runtime preflight, response validation, and retries. |
| `src/reasoning/system_prompt.txt` | Provider-neutral planner policy. |
| `src/perception/screen_capture.py` | Screenshot acquisition, UI snapshot caching, and multimodal context assembly. |
| `src/perception/audio_transcription.py` | Optional local Vosk-based WAV transcription. |
| `src/action/tools.py` | Desktop, process, clipboard, browser bridge, and file tools. |
| `src/action/browser_tools.py` | Selenium lifecycle and browser-specific DOM interactions. |
| `src/config.py` | Environment-backed configuration, validation, profiles, and safe logging view. |
| `deploy/nginx.conf` | Unprivileged container ingress for HTTP, WebSocket, stream, and upload proxying. |

## Reasoning contract

- Tool signatures generate schemas automatically; keep names, types, defaults, and
  argument documentation stable.
- The model response must identify the configured model and contain exactly one tool
  call with no surrounding prose or legacy parallel-call envelope.
- JSON parsing rejects duplicate keys and non-finite values. Tool arguments are
  validated again before dispatch.
- Transport ignores proxy environment variables, rejects redirects, limits response
  bytes, and enforces one total deadline across bounded retries.
- `ReasoningFailure` is structured. Protocol incompatibility and local-runtime
  failures terminate; correctable planner output may consume another bounded turn.
- Native Ollama preflight checks `/api/version`, `/api/tags`, and `/api/show`, including
  exact artifact identity, digest shape, tools capability, and vision capability when
  used. When configured, `DJENIS_LOCAL_LLM_EXPECTED_DIGEST` must match that full
  SHA-256. The model's declared context must be at least
  `DJENIS_LOCAL_LLM_CONTEXT_TOKENS`; requests pass that value as Ollama `num_ctx`.
  Preflight never invokes `/api/pull`.
- An OpenAI-compatible backend must expose `/v1/models` and
  `/v1/chat/completions`. Because implementations vary, its full tools/vision contract
  is also proven by the first real response.

## Runtime safety

- The tool registry is derived from both runtime capability and configured permission
  tier. A denied capability is omitted, and a refusal is a hard stop.
- `run_shell_command` is intentionally a native-process tool despite its historical
  name. It resolves one configured absolute executable, bypasses a command shell,
  rejects chaining/substitution, and supplies a minimal environment.
- Identical actions against unchanged semantic state are bounded. Volatile clocks and
  counters do not reset the stagnation guard.
- Completion is not an action acknowledgement. A state-changing step requires a fresh,
  relevant UI change or resource-compatible read verification.
- Structured JSONL audit events contain bounded metadata rather than full arbitrary
  objectives, arguments, observations, or completion evidence.
- Web sessions, sockets, queues, uploads, workers, prompt history, observations, local
  response bodies, and audit-log growth all have explicit limits.
- Remote Selenium perception comes from its own screenshot and DOM snapshot, not a
  blank host-desktop frame.

## Local inference configuration

The source of truth is `src/config.py`; mirror additions in `.env.example` and tests.

Important variables:

- `DJENIS_LOCAL_LLM_BACKEND`: `ollama` or `openai-compatible`.
- `DJENIS_LOCAL_LLM_ENDPOINT`: loopback HTTP URL, or a fixed internal service name in
  Docker. OpenAI-compatible bases end in `/v1`.
- `DJENIS_LOCAL_LLM_MODEL`: exact pre-provisioned model identifier.
- `DJENIS_LOCAL_LLM_EXPECTED_DIGEST`: optional lowercase full SHA-256 pin for Ollama;
  recommended after the first trusted provisioning and invalid for other backends.
- `DJENIS_LOCAL_LLM_CONTEXT_TOKENS`: requested Ollama context, default `65536`. Reducing
  it saves KV-cache memory but can truncate objective/UI/action evidence and reduce
  precision; keep the change explicit and test the target model.
- `DJENIS_LOCAL_LLM_VISION`: require/send image input.
- `DJENIS_LOCAL_LLM_KEEP_ALIVE`: Ollama model residency requested per call.
- `DJENIS_LOCAL_LLM_SEED`: deterministic sampling seed where supported.
- `DJENIS_LOCAL_LLM_RESPONSE_MAX_BYTES`: response-body limit.
- `DJENIS_LOCAL_LLM_IMAGE_MAX_BYTES`,
  `DJENIS_LOCAL_LLM_VISION_MAX_DIMENSION`, and
  `DJENIS_LOCAL_LLM_VISION_QUALITY`: screenshot transport bounds.
- `DJENIS_API_TIMEOUT`, `DJENIS_API_MAX_RETRIES`, and
  `DJENIS_API_RETRY_DELAY`: total local reasoning deadline and retry policy.

Do not add endpoint authentication, public-host exceptions, automatic pulls, provider
SDKs, or fallback routing. Such changes would alter the project's local-only trust
boundary and require an explicit architecture decision.

## Web probes

- `GET /health` is liveness. Keep it fast and independent of inference so process
  supervisors do not restart a healthy process during model loading.
- `GET /ready` validates configuration and the selected local runtime/model. Readiness
  may fail while liveness remains healthy.

Do not merge the semantics of these endpoints. Compose and image health checks use
`/health`; traffic admission and operator diagnostics should use `/ready`.

## Docker network contract

The checked-in Compose stack separates four networks:

- `djenis-control` is internal and connects agent, Ollama, Selenium, and the gateway.
- `console-ingress` connects only the unprivileged gateway to a host-reachable bridge;
  the gateway also joins control and publishes `127.0.0.1:8008`.
- `browser-egress` is attached only to Selenium Chrome for requested web navigation.
- `model-provisioning` is attached only to the opt-in `ollama-provision` profile.

Agent and long-running Ollama stay exclusively on the internal network and have no
published ports. The gateway uses the digest-pinned unprivileged NGINX image, a
read-only root filesystem, dropped capabilities, `no-new-privileges`, and a bounded
`/tmp` tmpfs. Its configuration preserves the original Host/Origin relationship,
supports WebSocket upgrade, disables buffering for screen streaming and transcription,
strips spoofable forwarding chains, and uses bounded upstream timeouts.

The long-running Ollama service sets `OLLAMA_NO_CLOUD=1` and uses a persistent named
model volume. `docker compose up` never downloads models. Provision the configured
artifact explicitly, while the normal runtime is stopped:

```powershell
docker compose --profile provision run --rm ollama-provision
```

Treat a Compose change that gives agent/runtime Ollama egress, publishes agent port
`8000` or Ollama port `11434`, moves loopback publishing away from the gateway, or
pulls a model at startup as a security-boundary change.

## Testing workflow

Primary local targets:

- `make check`
- `make security`
- `make test-ci`
- `make ci-local`

Run the direct gates when diagnosing a failure:

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

All reasoning tests must use deterministic local HTTP fakes or mocks. Unit and CI jobs
must not require a running model, pull artifacts, or contact a hosted inference API.
Portable tests run on Linux; desktop-aware coverage runs on Windows. Docker smoke tests
cover liveness separately from model readiness.

## CI/CD and releases

GitHub Actions lives in `.github/workflows/`:

- `ci.yml` runs lint, typing, security, portable tests, Windows coverage, Docker smoke,
  and image scanning.
- `docker-publish.yml` builds GHCR images and performs signed-tag release publication.
- `dependabot.yml` proposes weekly dependency and action updates.

Release publication is fail-closed. The annotated SSH-signed tag, remote default-branch
commit, event source, durable draft authorization, image digest, provenance, signature,
SBOM, immutable version alias, and GitHub Release must agree before mutable aliases can
move. Preserve those checks when changing release code.

## Contributor guidance

- Keep changes local to the subsystem being improved and preserve unrelated worktree
  edits.
- Preserve Windows-first automation while keeping portable and Docker paths explicit.
- Add tests for both accepted and rejected behavior.
- Treat new tools, endpoint exceptions, process execution, browser destinations, model
  transport, and network attachments as security-sensitive changes.
- Update this guide, the README, `.env.example`, threat model, and project site when an
  architectural boundary changes.
