# Security policy

DjenisAiAgent can control applications and, when explicitly enabled, execute shell commands and write files. Treat it like any other privileged automation tool: run it only in an environment you understand and limit the data and accounts available to that environment.

## Supported version

Security fixes are applied to the latest commit on `master`. The project is pre-1.0 and does not currently maintain older release branches.

## Reporting a vulnerability

Do not open a public issue for a vulnerability or exposed credential. Use GitHub's private vulnerability reporting feature on this repository. Include the affected commit, configuration, reproduction steps, and expected impact. Do not include real credentials or unrelated personal data.

## Operating guidance

- Keep `.env` out of version control and rotate any credential that may have been exposed.
- Leave `DJENIS_PERMISSION_TIER=observe` until a task needs more capability.
- Enable `system` only with narrow `DJENIS_ALLOWED_PATHS` and `DJENIS_ALLOWED_APPLICATIONS` values.
- Keep the web console bound to `127.0.0.1` unless you have added TLS and explicit network controls.
- Use a separate browser profile for automation.
- Review `logs/agent-audit.jsonl` before sharing it, even though known secrets and oversized values are redacted.

## Security boundaries

The project validates operator sessions, origins, upload size, request rate, tool names, permission tiers, paths, applications, and URL schemes. These controls reduce accidental exposure; they are not a formal sandbox. The `system` tier intentionally grants high-impact capabilities to the local process.
