# Contributing

Thanks for taking the time to improve DjenisAiAgent. Keep changes small enough to review and be direct about what you tested.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Set up the project

Use Python 3.11 or 3.12 and the locked environment:

```powershell
uv sync --frozen --extra dev --extra full
Copy-Item .env.example .env
```

Do not put a real API key in `.env` unless a manual test needs it. Most unit tests use mocks and run without external credentials.

## Before opening a pull request

Run the same checks as CI:

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

Add or update tests when behavior changes. Explain any check you could not run.

## Respect the permission boundary

New tools must use the existing permission checks. Keep the default tier at `observe`, require a narrow allowlist for system access, and never route model output through a command shell. A refusal is a hard stop; tools must not work around it.

## Protect private data

Never commit credentials, cookies, personal data, private prompts, raw audit logs, or screenshots from a real account. Use synthetic examples in tests and documentation. Review staged changes before every commit.

For vulnerabilities or exposed credentials, do not open a public issue. Follow [SECURITY.md](SECURITY.md) and use GitHub private vulnerability reporting.
