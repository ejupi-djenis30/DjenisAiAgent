# Security policy

DjenisAiAgent can control applications and, when explicitly enabled, start native
programs and write files. Treat it as privileged automation: run it only in an
environment you understand and limit the data, accounts, programs, paths, browser
destinations, and model runtime available to it.

## Supported version

Security fixes are applied to the latest commit on `master`. The project is pre-1.0 and
does not currently maintain older release branches.

## Reporting a vulnerability

Do not open a public issue for a vulnerability or exposed credential. Use GitHub's
private vulnerability reporting feature for this repository. Include the affected
commit, configuration, reproduction steps, and expected impact. Do not include real
credentials or unrelated personal data.

## Operating guidance

- Keep `.env`, model-server logs, screenshots, cookies, and audit logs out of version
  control.
- Use only a local model endpoint. Do not add public endpoints, proxy routing,
  automatic model downloads, or hosted-model fallback.
- For Ollama, set `OLLAMA_NO_CLOUD=1`, provision the selected artifact explicitly, and
  keep port `11434` unexposed. After trusted provisioning, pin its full lowercase
  SHA-256 with `DJENIS_LOCAL_LLM_EXPECTED_DIGEST`.
- Confirm the model supports `DJENIS_LOCAL_LLM_CONTEXT_TOKENS`. Lowering the 65,536
  default reduces KV-cache memory but also reduces retained objective and verification
  evidence; treat it as a precision tradeoff, not a transparent optimization.
- Leave `DJENIS_PERMISSION_TIER=observe` until a task needs more capability.
- Enable `system` only with narrow path, application, and absolute-executable
  allowlists plus `DJENIS_CONFIRM_DANGEROUS_ACTIONS=true`.
- Keep `DJENIS_ALLOWED_URL_HOSTS` empty unless one exact private/local browser
  destination is intentional.
- In Docker, publish only the unprivileged gateway on `127.0.0.1`; do not publish the
  agent or Ollama directly. Remote exposure requires TLS, exact origins, and explicit
  network access policy.
- Use a dedicated OS/browser profile and review what is visible before starting.
- Review `logs/agent-audit.jsonl` before sharing it. Redaction and metadata-only event
  design reduce exposure but are not an anonymity guarantee.

## Security boundaries

The project validates local inference endpoints, runtime/model identity, operator
sessions, origins, upload size, request rate, connection and worker capacity, tool
names and arguments, permission tiers, paths, applications, and browser destinations.
The model is always an untrusted planner.

Native process execution never passes model output to a command shell, launches only
configured absolute executables, and supplies a minimal environment. Any allowlisted
program still retains the power of its own flags.

Local-only inference means objectives, screenshots, UI context, and recent observations
are sent to the configured local serving process rather than a hosted model. Loopback
is a network boundary, not process attestation: a compromised local server or host can
still read that data. Screenshots are not automatically redacted.

Browser navigation is a separate boundary. Public-site access still requires browser
egress, and webpages remain untrusted. Application-level URL checks reduce SSRF, but
network policy remains stronger against redirects, DNS rebinding, and subresources.
The Compose stack therefore keeps agent and Ollama exclusively on an internal network.
Selenium Chrome receives browser egress. A digest-pinned, unprivileged NGINX gateway
bridges a separate host-facing ingress network to the agent and is the only service
publishing a loopback port. Its read-only filesystem, dropped capabilities, bounded
tmpfs, fixed upstream, and proxy timeouts reduce its exposure; because its ingress
bridge is non-internal, a gateway compromise remains a network risk.

`/health` is liveness and intentionally independent of the model. `/ready` checks the
selected local runtime/model and should gate traffic. These controls reduce accidental
exposure; they are not a formal sandbox. The `system` tier intentionally grants
high-impact capabilities to the local process.

The full data-flow and residual-risk analysis is in
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
