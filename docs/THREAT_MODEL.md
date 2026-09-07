# Threat model and data boundaries

DjenisAiAgent is a privileged local automation process, not a security sandbox. Its
safety model assumes a trusted operator, an explicitly bounded runtime, a trusted
local model-serving process, and an untrusted model whose requested actions are
validated by host policy.

## Data flow

For each reasoning turn, the process sends the configured **local** inference endpoint:

- the operator objective;
- a current screenshot when vision is enabled;
- a bounded accessibility tree or remote-browser snapshot containing rendered text and
  visible, non-password controls;
- a bounded recent execution record; and
- declarations for tools available in the active runtime and permission tier.

The endpoint is restricted to loopback HTTP or a fixed internal Docker service. The
client does not use proxy environment variables, follow redirects, attach credentials,
or retry against another provider. There is no hosted inference fallback.

Textual credential shapes are redacted best-effort before reasoning. Screenshots are
not automatically redacted and can contain anything visible on the controlled display.
Local transport prevents intentional provider disclosure, but does not protect against
a malicious process already owning the configured port, a compromised model runtime,
host malware, swap/crash capture, or operator-enabled logging in that runtime.

The local JSONL audit log stores bounded metadata such as event types, tool names,
argument names and lengths, durations, model/backend identity, and outcome
classifications. It intentionally avoids full arbitrary objectives, arguments,
observations, and completion evidence. Redaction is defense in depth, not proof that
personal data can never reach application logs.

## Trust boundaries

| Boundary | Trust level | Enforcement |
| --- | --- | --- |
| System policy and host runtime summary | Trusted | Created by checked-in host code. |
| Operator objective | Authorized instruction | Limited by tier, runtime, and allowlists. |
| Local model server process | Deployment trust | Local endpoint validation, no proxies/redirects, bounded HTTP. |
| Model output | Untrusted plan | One declared call, strict JSON/schema/argument checks. |
| Webpages, documents, UI labels, clipboard, and tool output | Untrusted data | Explicit data boundary; never interpreted as policy. |
| Tool execution | Privileged boundary | Capability registry, permission tier, path/app/process/URL policy. |
| Completion claim | Untrusted request | Relevant fresh evidence, post-action perception, and stagnation checks. |
| Browser network | External/untrusted | Destination checks plus deployment egress controls. |

## Primary threats and controls

- **Prompt injection:** UI and tool text are labeled as untrusted data. The host
  validates every requested tool, argument, and terminal outcome independently of the
  model's explanation.
- **Malformed or ambiguous model responses:** only one call is accepted. Duplicate JSON
  keys, non-finite values, unknown tools, legacy/multiple calls, mixed prose, model
  identity mismatch, and oversized responses fail closed.
- **False completion:** `finish_task` distinguishes `completed` from `blocked`.
  Generic or ungrounded evidence is rejected. State-changing actions require a fresh
  relevant postcondition or domain/resource-compatible read.
- **Repeated side effects:** identical actions against the same semantic UI state are
  bounded; volatile clock/counter values do not reset stagnation.
- **Capability escalation:** unsupported tools are omitted. Permission denials are
  terminal and system tools require a second dangerous-action opt-in.
- **Filesystem/process abuse:** paths and absolute executables use operator allowlists.
  Native execution bypasses a shell, rejects chaining/substitution, and gives child
  processes a minimal environment.
- **Local inference escape:** the endpoint parser rejects public IPs, credentials,
  query strings, fragments, unexpected paths, and unapproved Docker hostnames. The
  transport ignores system proxy configuration and refuses redirects.
- **Runtime artifact substitution:** native Ollama preflight requires the exact local
  model identifier and validates its digest shape and capabilities before work. The
  optional `DJENIS_LOCAL_LLM_EXPECTED_DIGEST` pin compares the full SHA-256 and is
  recommended after trusted provisioning. The server remains a trusted component.
- **SSRF and unsafe navigation:** browser URLs must use HTTP(S). Non-allowlisted hosts
  must resolve exclusively to globally routable addresses; explicit targets and
  redirects are rechecked, and unsafe top-level page context is discarded before
  inference.
- **Web control-plane abuse:** opaque authenticated sessions, origin validation,
  loopback binding, bounded queues/connections/uploads/workers, rate limits, and
  immediate socket revocation.
- **Resource exhaustion:** reasoning has a total deadline, retry cap, response/image
  byte limits, and bounded model context. Agent turns, task time, tool output, and
  concurrency are separately limited. WAV size, frame integrity, source/output sample
  rates and clip duration are checked before resampling or Vosk loading; bounding
  upload bytes alone would not bound decoded audio. The 65,536-token default improves evidence
  retention but increases local KV-cache memory; operators may explicitly lower it for
  constrained hardware, accepting the corresponding precision/context tradeoff.

## Docker network boundary

Normal Compose runtime separates the following paths:

- Agent, Ollama, Selenium, and the gateway share `djenis-control`, an internal network.
  Agent and Ollama connect to no other network.
- Selenium also joins `browser-egress`, because browser automation may need public web
  access.
- The unprivileged NGINX gateway also joins `console-ingress` and alone publishes
  `127.0.0.1:8008`. It proxies to agent port `8000` over control; the agent does not
  publish that port directly.

Ollama has no published port, sets `OLLAMA_NO_CLOUD=1`, and cannot reach an
internet-facing network during normal operation. The persistent model volume is
populated only by the opt-in `ollama-provision` profile, whose separate network has
temporary egress. `docker compose up` never starts that service or pulls a model.

The gateway is a deployment trust boundary because it sees console HTTP, objectives
carried by WebSocket, the screen stream, and uploads. Its image is digest-pinned and
unprivileged; root filesystem is read-only, capabilities are dropped, privileges cannot
be gained, scratch space is a bounded tmpfs, and its only configured upstream is the
agent. The non-internal ingress bridge is necessary for Docker Desktop port publishing;
a compromised gateway could still misuse that network, so it is not treated as a
sandbox.

This split keeps inference local while preserving explicit console and browser
connectivity. It does not make web content local, private, or trustworthy. Container
network controls also do not constrain Windows native mode; host firewall policy is
required there.

## Liveness and readiness

`/health` reports process liveness and intentionally does not contact the model. `/ready`
checks validated configuration plus the selected local runtime/model. A live but
unready process is expected while the runtime is unavailable or incompatible. Process
supervisors should use liveness for restart decisions and readiness for traffic.

## Residual risk

- A model-visible screenshot can disclose anything visible on screen to the local
  model-serving process.
- Loopback proves network location, not process identity. Another local process can bind
  the configured port or tamper with runtime/model files.
- Model quantization, templates, runtime versions, and tool/vision support affect
  reliability even when a model identifier and digest match an approved artifact.
- UI automation can target the wrong control when accessibility metadata is poor.
- An allowlisted program, local URL host, path, browser profile, or model runtime carries
  the authority granted by the operator.
- Native desktop actions are not isolated from the logged-in user session.
- A tool acknowledgement is not proof of the requested business outcome; weakly
  observable applications may require operator confirmation.
- DNS and application-level checks reduce SSRF and browser-context leakage, but a
  redirect, script navigation, DNS rebinding, or page subresource can issue a request
  before or without a top-level URL change. Deployment egress filtering remains the
  stronger network boundary.
- The OpenAI-compatible ecosystem is heterogeneous. Model-list preflight cannot prove
  tool and vision semantics as strongly as native Ollama capability inspection.
- A compromised ingress gateway can observe console traffic and may gain outbound
  reachability through its non-internal bridge despite its hardened configuration.

## Deployment checklist

1. Provision and review the exact local model artifact before starting the agent.
   After first trusted preflight, pin its full SHA-256 with
   `DJENIS_LOCAL_LLM_EXPECTED_DIGEST`.
2. Disable remote model features in the serving runtime; use `OLLAMA_NO_CLOUD=1` for
   Ollama.
3. Start at `DJENIS_PERMISSION_TIER=observe`.
4. Use a disposable or dedicated OS and browser profile.
5. Keep allowed paths, applications, commands, and URL hosts minimal.
6. Publish only the gateway on loopback; never publish the agent directly. Add TLS and
   exact origins before remote exposure.
7. Keep the model endpoint on loopback or the internal Docker network; never publish it.
8. Review what is visible before a task, even though inference remains local.
9. Use `/ready` to confirm the selected runtime/model before admitting work.
10. Treat `system` tier as privileged code execution, not ordinary assistant access.
