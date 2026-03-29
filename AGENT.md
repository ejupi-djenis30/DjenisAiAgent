# DjenisAiAgent Developer Guide

## Overview

DjenisAiAgent is a multimodal automation agent built around a ReAct loop:

1. Perception captures the current desktop state as a screenshot plus a structured UI tree.
2. Reasoning asks Gemini for the next tool call using function calling.
3. Action executes the selected desktop, browser, clipboard, shell, or file tool.
4. Observation feeds the result back into the next turn until the task is completed or aborted.

The repository is designed to support two primary runtime modes:

- CLI mode for direct local execution.
- Web mode for queue-based execution, streaming updates, and browser control from FastAPI.

## Core Modules

| Path | Responsibility |
| --- | --- |
| `main.py` | CLI entry point, FastAPI app, WebSocket command flow, health and streaming endpoints. |
| `src/orchestration/agent_loop.py` | Main task loop, cancellation handling, retries, and tool dispatch. |
| `src/reasoning/gemini_core.py` | Gemini integration, tool schema generation, response validation, and API retry logic. |
| `src/perception/screen_capture.py` | Screenshot acquisition, UI snapshot caching, and multimodal context assembly. |
| `src/perception/audio_transcription.py` | Optional local Vosk-based WAV transcription. |
| `src/action/tools.py` | Desktop, shell, clipboard, browser bridge, and file tools exposed to the agent. |
| `src/action/browser_tools.py` | Selenium driver lifecycle and browser-specific DOM interactions. |
| `src/config.py` | Environment-backed configuration, validation, profiles, and safe logging view. |

## Tooling Conventions

- Tools should expose narrow, explicit behavior and return user-readable strings or JSON-safe payloads.
- High-risk operations should go through dedicated tools rather than arbitrary shell execution.
- Tool signatures are used to generate Gemini function schemas automatically, so keep names and argument types stable.
- New tools belong in `src/action/tools.py` unless they require a separate integration boundary such as Selenium.

## Runtime Safety

- `run_shell_command` is intentionally restricted to read-oriented diagnostics. Mutating or destructive PowerShell commands are blocked.
- Desktop and browser state reuse is protected with lightweight locking where shared mutable state exists.
- The task loop now enforces a global wall-clock timeout in addition to the per-turn limit.
- Perception can be downscaled before sending screenshots to Gemini to control latency and token cost.
- Structured audit events are appended to a JSONL log so task execution and tool calls can be reconstructed after failures.

## Configuration Notes

Important settings live in `.env` / environment variables:

- `GEMINI_API_KEY`: required for all reasoning.
- `DJENIS_MAX_LOOP_TURNS`: max number of reasoning turns.
- `DJENIS_TASK_TIMEOUT`: wall-clock timeout for the full task.
- `DJENIS_ACTION_TIMEOUT`: timeout for UI-bound actions.
- `DJENIS_API_TIMEOUT`: timeout per Gemini API attempt.
- `DJENIS_PERCEPTION_DOWNSCALE`: screenshot resize factor before reasoning.
- `DJENIS_ENABLE_AUDIT_LOG` / `DJENIS_AUDIT_LOG_PATH`: enable and locate the JSONL audit log.
- `DJENIS_PROFILE`: applies performance or quality presets.

Use `src/config.py` as the single source of truth for defaults and validation.

## Testing Workflow

Primary local targets:

- `make check`
- `make security`
- `make test-ci`
- `make ci-local`

The test suite is intentionally split:

- Portable tests run on Ubuntu in CI.
- Windows coverage and desktop automation checks run on Windows.
- Docker smoke tests validate the web surface and health endpoint.

## CI/CD Layout

GitHub Actions lives in `.github/workflows/`:

- `ci.yml`: linting, type checking, security scanning, portable tests, Windows coverage, Docker smoke test, image scan.
- `docker-publish.yml`: GHCR build/push, published image scan, release creation for version tags.
- `dependabot.yml`: weekly dependency and GitHub Actions updates.

## Contributor Guidance

- Keep changes minimal and local to the subsystem you are improving.
- Preserve the Windows-first automation model while keeping portable paths working for CI and Docker.
- If you add config, document it in `.env.example`, validate it in `src/config.py`, and cover it with tests.
- If you add tool behavior, add unit tests for both the success path and the rejection/failure path.
- If you change orchestration or reasoning behavior, update the corresponding tests in `tests/unit/` before changing the implementation.

## Near-Term Evolution

The current direction for the agent is pragmatic hardening before larger capability expansion:

1. Runtime safety and guardrails.
2. Observability and auditability.
3. CI/CD and dependency hygiene.
4. Explicit task planning and permission tiers.

That order keeps the agent usable while making future “advanced agent” work easier to land safely.