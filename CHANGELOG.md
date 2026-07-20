# Changelog

This file records user-visible and release-engineering changes to DjenisAiAgent.

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
