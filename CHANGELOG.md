# Changelog

This file records user-visible and release-engineering changes to DjenisAiAgent.

## Unreleased

## 0.3.0 - 2026-07-29

### Added

- Host-enforced completion evidence, distinct `completed` and `blocked` outcomes,
  strict tool-argument validation, and a repeated-action stagnation guard.
- Remote Selenium navigation and multimodal browser perception for container runtimes.
- A local-only Compose stack with an unprivileged loopback gateway, internal Ollama
  service, explicit model-provisioning profile, and isolated Selenium browser egress.
- A threat model and fail-closed liveness/readiness split for operators.

### Changed

- Move reasoning to pre-provisioned local Ollama or OpenAI-compatible models, with no
  hosted-provider credential, remote fallback, or automatic runtime download.
- Send agent policy as a system instruction and require exactly one manually dispatched
  function call.
- Preserve the newest execution evidence when prompt history is truncated.
- Keep desktop element lookup side-effect free and remove the incomplete coordinate
  mouse protocol from the model-visible capability set.
- Restrict native program execution to configured absolute executables, a minimal child
  environment, bounded output, and direct process launch without a command shell.
- Validate browser destinations before navigation and after redirects, with explicit
  allowlisting for intentional private or local hosts.
- Run the complete unit suite in release gates and align local quality tooling with CI.

### Removed

- Gemini inference, `GEMINI_API_KEY`, and `DJENIS_GEMINI_MODEL`. Existing `v0.2.2`
  deployments must configure a supported local model before upgrading.

## 0.2.2 - 2026-07-20

### Fixed

- Publish `edge` and `sha-*` from `master` without moving the stable `latest` alias.
- Publish `latest`, full, minor, and major aliases only from a verified version tag.

### Changed

- Require each new release tag to be annotated and SSH-signed, with a valid signature reported by GitHub before authorization, alias promotion, or Release publication.
- Keep the existing `v0.2.1` release unchanged; the stricter contract begins with `v0.2.2`.

## 0.2.1 - 2026-07-20

### Fixed

- Keep the Git tag, Python package version, runtime version, and lockfile version in sync.
- Publish and verify GHCR aliases without the Git tag's leading `v`.
- Generate release instructions from the validated project version, so every documented image reference exists.
- Reject release tags whose dereferenced commit is not exactly the current `origin/master` commit.
- Keep stable GHCR aliases unchanged until the candidate digest passes Trivy.

### Changed

- Verify the published digest, SPDX SBOM, BuildKit provenance, and GitHub OIDC signature before creating a GitHub Release.
- Parse workflow structure in the release-contract validator and run pinned, checksummed actionlint in CI.
- Add a declarative GitHub ruleset that makes existing `v*` release tags immutable.

## 0.2.0 - 2026-07-20

### Added

- Authenticated HTTP and WebSocket boundaries for the local web console.
- Reproducible dependency locks, container scanning, SBOM, provenance, and release automation.
- A public project page with an interactive, deterministic walkthrough.

### Changed

- Raise the test coverage gate and extend fail-closed tests around privileged tools.
