"""Validate the version, tag, container, and release workflow contract."""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess  # nosec B404
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "djenis-ai-agent"
WORKFLOW_PATH = Path(".github/workflows/docker-publish.yml")
CI_WORKFLOW_PATH = Path(".github/workflows/ci.yml")
TAG_RULESET_PATH = Path(".github/rulesets/immutable-v-tags.json")
SEMVER_PATTERN = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
GIT_COMMIT_PATTERN = re.compile(r"[0-9a-fA-F]{40,64}")
PINNED_ACTION_PATTERN = re.compile(r"[^@\s]+@[0-9a-f]{40}")
REMOTE_TAG_REF_ROOT = "refs/djenis-release-verification/tags"
REMOTE_MASTER_REF = "refs/djenis-release-verification/heads/master"

PUBLISH_REF_GATE = "github.ref == 'refs/heads/master' || startsWith(github.ref, 'refs/tags/v')"
TAG_REF_GATE = "startsWith(github.ref, 'refs/tags/v')"
RELEASE_VALIDATION_COMMAND = 'uv run --frozen --no-sync python scripts/validate_release.py --github-output "${GITHUB_OUTPUT}"'
ATTEST_ACTION = "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6"
ACTIONLINT_VERSION = "1.7.12"
ACTIONLINT_SHA256 = "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
MINIMUM_GH_VERSION = "2.92.0"
MINIMUM_REGISTRY_BACKOFF_SECONDS = 60
MAXIMUM_REGISTRY_BACKOFF_SECONDS = 120

EXPECTED_JOB_PERMISSIONS: dict[str, dict[str, dict[str, str]]] = {
    "ci.yml": {
        "lint": {"contents": "read"},
        "security": {"contents": "read"},
        "type-check": {"contents": "read"},
        "portable-tests": {"contents": "read"},
        "windows-coverage": {"contents": "read"},
        "docker-build": {"contents": "read"},
    },
    "docker-publish.yml": {
        "verify": {"contents": "read"},
        "release-preflight": {"contents": "write"},
        "candidate": {"contents": "read", "packages": "write"},
        "attest": {
            "attestations": "write",
            "contents": "read",
            "id-token": "write",
            "packages": "write",
        },
        "attest-master": {
            "attestations": "write",
            "contents": "read",
            "id-token": "write",
            "packages": "write",
        },
        "authorize-release": {"contents": "write"},
        "promote-release": {"contents": "write", "packages": "write"},
        "promote-master": {"contents": "read", "packages": "write"},
        "release": {"contents": "write"},
    },
    "pages.yml": {
        "deploy": {"contents": "read", "id-token": "write", "pages": "write"},
    },
}

YamlMapping = dict[str, object]
GitRunner = Callable[[tuple[str, ...]], str]


class ReleaseContractError(ValueError):
    """Raised when repository release metadata cannot describe one release."""


@dataclass(frozen=True)
class ReleaseContract:
    """Validated release values shared by CI jobs."""

    version: str
    image_tags: tuple[str, str, str, str]
    tag_commit: str | None = None


@dataclass(frozen=True)
class ReleaseTagOrigin:
    """Dereferenced commits used to authorize a release tag."""

    tag_commit: str
    master_commit: str


def image_tags_for_version(version: str) -> tuple[str, str, str, str]:
    """Return the immutable, minor, major, and latest release aliases."""

    if SEMVER_PATTERN.fullmatch(version) is None:
        raise ReleaseContractError(f"project version must be stable SemVer, got {version!r}")
    major, minor, _patch = version.split(".")
    return version, f"{major}.{minor}", major, "latest"


def master_image_tags_for_commit(commit: str) -> tuple[str, str]:
    """Return the moving edge alias and exact short-SHA alias for master."""

    if GIT_COMMIT_PATTERN.fullmatch(commit) is None:
        raise ReleaseContractError("master commit must be an exact Git object id")
    return "edge", f"sha-{commit[:7].lower()}"


def _project_version(project_root: Path) -> str:
    with (project_root / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)
    version = project.get("project", {}).get("version")
    if not isinstance(version, str):
        raise ReleaseContractError("pyproject.toml is missing project.version")
    return version


def _runtime_version(project_root: Path) -> str:
    config_path = project_root / "src" / "config.py"
    tree = ast.parse(config_path.read_text(encoding="utf-8"), filename=str(config_path))
    versions: list[str] = []
    for node in tree.body:
        value: ast.expr | None = None
        is_version = False
        if isinstance(node, ast.AnnAssign):
            is_version = isinstance(node.target, ast.Name) and node.target.id == "VERSION"
            value = node.value
        elif isinstance(node, ast.Assign):
            is_version = any(
                isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets
            )
            value = node.value
        if is_version and isinstance(value, ast.Constant) and isinstance(value.value, str):
            versions.append(value.value)
    if len(versions) != 1:
        raise ReleaseContractError("src/config.py must declare exactly one string VERSION")
    return versions[0]


def _locked_version(project_root: Path) -> str:
    with (project_root / "uv.lock").open("rb") as lock_file:
        lock = tomllib.load(lock_file)
    packages = [
        package
        for package in lock.get("package", [])
        if package.get("name") == PROJECT_NAME and package.get("source") == {"editable": "."}
    ]
    if len(packages) != 1:
        raise ReleaseContractError("uv.lock must contain one editable djenis-ai-agent package")
    version = packages[0].get("version")
    if not isinstance(version, str):
        raise ReleaseContractError("the editable djenis-ai-agent lock entry is missing a version")
    return version


def repository_versions(project_root: Path) -> dict[str, str]:
    """Read every authoritative project version source."""

    return {
        "pyproject.toml": _project_version(project_root),
        "src/config.py": _runtime_version(project_root),
        "uv.lock": _locked_version(project_root),
    }


def _mapping(value: object) -> YamlMapping | None:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    return cast(YamlMapping, value)


def _sequence(value: object) -> list[object] | None:
    return cast(list[object], value) if isinstance(value, list) else None


def _parse_workflow(workflow: str, label: str) -> tuple[YamlMapping | None, list[str]]:
    try:
        document = yaml.safe_load(workflow)
    except yaml.YAMLError as exc:
        return None, [f"{label} is not valid YAML: {exc}"]
    mapping = _mapping(document)
    if mapping is None:
        return None, [f"{label} must contain a YAML mapping"]
    return mapping, []


def _workflow_job(
    document: YamlMapping, job_name: str, label: str, errors: list[str]
) -> YamlMapping | None:
    jobs = _mapping(document.get("jobs"))
    job = _mapping(jobs.get(job_name)) if jobs is not None else None
    if job is None:
        errors.append(f"{label} is missing the {job_name!r} job")
    return job


def _workflow_steps(job: YamlMapping, job_name: str, errors: list[str]) -> list[YamlMapping]:
    raw_steps = _sequence(job.get("steps"))
    if raw_steps is None:
        errors.append(f"{job_name} job must declare a steps list")
        return []
    steps = [_mapping(step) for step in raw_steps]
    if any(step is None for step in steps):
        errors.append(f"{job_name} job contains a non-mapping step")
    return [step for step in steps if step is not None]


def _workflow_step(
    steps: Sequence[YamlMapping], step_id: str, job_name: str, errors: list[str]
) -> YamlMapping | None:
    matches = [step for step in steps if step.get("id") == step_id]
    if len(matches) != 1:
        errors.append(f"{job_name} job must contain exactly one step with id {step_id!r}")
        return None
    return matches[0]


def _step_index(steps: Sequence[YamlMapping], step_id: str) -> int | None:
    return next((index for index, step in enumerate(steps) if step.get("id") == step_id), None)


def _normalized_shell(step: Mapping[str, object]) -> str:
    run = step.get("run")
    if not isinstance(run, str):
        return ""
    commands: list[str] = []
    for line in run.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            stripped = stripped[:-1].rstrip()
        commands.append(stripped)
    return " ".join(" ".join(commands).split())


def _needs(job: Mapping[str, object]) -> set[str]:
    value = job.get("needs")
    if isinstance(value, str):
        return {value}
    sequence = _sequence(value)
    return {item for item in sequence or [] if isinstance(item, str)}


def _validate_checkout(steps: Sequence[YamlMapping], job_name: str, errors: list[str]) -> None:
    checkout = _workflow_step(steps, "checkout", job_name, errors)
    if checkout is None:
        return
    uses = checkout.get("uses")
    settings = _mapping(checkout.get("with"))
    if not isinstance(uses, str) or not uses.startswith("actions/checkout@"):
        errors.append(f"{job_name} checkout step must use actions/checkout")
    if settings is None or settings.get("fetch-depth") != 0:
        errors.append(f"{job_name} checkout must fetch full history for tag dereferencing")
    if settings is None or settings.get("persist-credentials") is not False:
        errors.append(f"{job_name} checkout must disable persisted credentials")


def _validate_retry_schedule(
    step: YamlMapping, variable: str, label: str, errors: list[str]
) -> None:
    environment = _mapping(step.get("env"))
    raw_schedule = environment.get(variable) if environment is not None else None
    try:
        delays = [int(delay) for delay in str(raw_schedule).split()]
    except ValueError:
        delays = []
    total = sum(delays)
    if (
        not delays
        or any(delay <= 0 for delay in delays)
        or delays != sorted(delays)
        or not MINIMUM_REGISTRY_BACKOFF_SECONDS <= total <= MAXIMUM_REGISTRY_BACKOFF_SECONDS
    ):
        errors.append(
            f"{label} retry delays must be nondecreasing and total "
            f"{MINIMUM_REGISTRY_BACKOFF_SECONDS}-{MAXIMUM_REGISTRY_BACKOFF_SECONDS} seconds"
        )


def _validate_signed_tag_step(
    step: YamlMapping,
    *,
    expected_commit: str,
    expected_gate: str | None,
    label: str,
    errors: list[str],
) -> None:
    """Require a fail-closed GitHub API check for an annotated SSH-signed tag."""

    command = _normalized_shell(step)
    environment = _mapping(step.get("env"))
    required = (
        "scripts/verify_github_tag.py",
        '--repository "${GITHUB_REPOSITORY}"',
        '--api-url "${GITHUB_API_URL}"',
        '--tag "${GITHUB_REF_NAME}"',
        f'--expected-commit "{expected_commit}"',
    )
    if (
        any(token not in command for token in required)
        or environment != {"GITHUB_TOKEN": "${{ github.token }}"}  # nosec B105
        or step.get("if") != expected_gate
        or step.get("shell") != "bash"
        or step.get("continue-on-error") not in (None, False)
    ):
        errors.append(f"{label} must require an annotated GitHub-verified SSH release tag")


def _validate_attestation_job(
    job: YamlMapping,
    *,
    job_name: str,
    expected_gate: str,
    require_reuse_preflight: bool,
    errors: list[str],
) -> None:
    expected_needs = (
        {"candidate", "release-preflight"} if require_reuse_preflight else {"verify", "candidate"}
    )
    if _needs(job) != expected_needs or job.get("if") != expected_gate:
        errors.append(f"{job_name} job must use its exact dependencies and ref gate")
    expected_permissions = {
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
        "packages": "write",
    }
    if _mapping(job.get("permissions")) != expected_permissions:
        errors.append(f"{job_name} must use exact least-privilege OIDC permissions")
    steps = _workflow_steps(job, job_name, errors)
    signing = _workflow_step(steps, "github-attestation", job_name, errors)
    verification = _workflow_step(steps, "verify-github-attestation", job_name, errors)
    reuse_preflight = (
        _workflow_step(steps, "verify-reused-attestation", job_name, errors)
        if require_reuse_preflight
        else None
    )
    if signing is not None:
        signing_with = _mapping(signing.get("with"))
        expected_signing = {
            "subject-name": "${{ needs.candidate.outputs.image }}",
            "subject-digest": "${{ needs.candidate.outputs.digest }}",
            "push-to-registry": True,
        }
        if signing.get("uses") != ATTEST_ACTION or signing_with != expected_signing:
            errors.append(f"{job_name} must sign the scanned candidate digest with GitHub OIDC")
        expected_signing_gate = (
            "needs.candidate.outputs.reused != 'true'" if require_reuse_preflight else None
        )
        if signing.get("if") != expected_signing_gate or signing.get("continue-on-error") is True:
            errors.append(
                f"{job_name} signing must not bypass trusted reuse provenance verification"
            )
    source_digest = "AUTHORIZED_COMMIT" if require_reuse_preflight else "GITHUB_SHA"
    required_verification_tokens = (
        'image_uri="oci://${PUBLISHED_IMAGE}@${PUBLISHED_DIGEST}"',
        "gh attestation verify",
        '--repo "${GITHUB_REPOSITORY}"',
        '--signer-workflow "${GITHUB_REPOSITORY}/.github/workflows/docker-publish.yml"',
        f'--source-digest "${{{source_digest}}}"',
        '--source-ref "${GITHUB_REF}"',
        '--predicate-type "https://slsa.dev/provenance/v1"',
        '--cert-oidc-issuer "https://token.actions.githubusercontent.com"',
        "--bundle-from-oci",
        "--deny-self-hosted-runners",
    )
    if reuse_preflight is not None:
        _validate_retry_schedule(
            reuse_preflight,
            "ATTESTATION_RETRY_DELAYS",
            f"{job_name} reused attestation",
            errors,
        )
        preflight_command = _normalized_shell(reuse_preflight)
        reuse_environment = _mapping(reuse_preflight.get("env"))
        if (
            reuse_preflight.get("if") != "needs.candidate.outputs.reused == 'true'"
            or reuse_preflight.get("continue-on-error") is True
            or "|| true" in preflight_command
            or any(token not in preflight_command for token in required_verification_tokens)
            or reuse_environment is None
            or reuse_environment.get("AUTHORIZED_COMMIT")
            != "${{ needs.release-preflight.outputs.tag_commit }}"
        ):
            errors.append(
                f"{job_name} must verify identity-bound pre-existing provenance before reuse"
            )
    if verification is not None:
        _validate_retry_schedule(
            verification, "ATTESTATION_RETRY_DELAYS", f"{job_name} attestation", errors
        )
        command = _normalized_shell(verification)
        required = (
            f'minimum_gh_version="{MINIMUM_GH_VERSION}"',
            *required_verification_tokens,
        )
        verification_environment = _mapping(verification.get("env"))
        source_environment_invalid = require_reuse_preflight and (
            verification_environment is None
            or verification_environment.get("AUTHORIZED_COMMIT")
            != "${{ needs.release-preflight.outputs.tag_commit }}"
        )
        if any(token not in command for token in required) or source_environment_invalid:
            errors.append(
                f"{job_name} Sigstore verification must bind digest, source, workflow, and OIDC identity"
            )
    signing_index = _step_index(steps, "github-attestation")
    verification_index = _step_index(steps, "verify-github-attestation")
    if signing_index is None or verification_index is None or signing_index >= verification_index:
        errors.append(f"{job_name} must sign before cryptographic verification")
    if require_reuse_preflight:
        preflight_index = _step_index(steps, "verify-reused-attestation")
        if (
            preflight_index is None
            or signing_index is None
            or verification_index is None
            or not preflight_index < signing_index < verification_index
        ):
            errors.append(
                f"{job_name} must verify reused provenance before any OIDC signing action"
            )


def validate_workflow_text(workflow: str) -> list[str]:
    """Structurally validate the state-aware Docker release workflow."""

    document, errors = _parse_workflow(workflow, "docker-publish workflow")
    if document is None:
        return errors

    triggers = _mapping(document.get("on"))
    push = _mapping(triggers.get("push")) if triggers is not None else None
    branches = _sequence(push.get("branches")) if push is not None else None
    tags = _sequence(push.get("tags")) if push is not None else None
    if branches != ["master"] or tags != ["v*"]:
        errors.append("docker-publish push triggers must be exactly master and v* tags")
    if triggers is None or "workflow_dispatch" not in triggers:
        errors.append("docker-publish workflow must retain workflow_dispatch verification")
    concurrency = _mapping(document.get("concurrency"))
    if concurrency != {
        "group": (
            "${{ github.workflow }}-${{ startsWith(github.ref, 'refs/tags/v') "
            "&& 'release' || github.ref }}"
        ),
        "cancel-in-progress": False,
    }:
        errors.append("publication runs for one ref must serialize without cancellation")

    verify = _workflow_job(document, "verify", "docker-publish workflow", errors)
    release_preflight = _workflow_job(
        document, "release-preflight", "docker-publish workflow", errors
    )
    candidate = _workflow_job(document, "candidate", "docker-publish workflow", errors)
    authorize_release = _workflow_job(
        document, "authorize-release", "docker-publish workflow", errors
    )
    attest = _workflow_job(document, "attest", "docker-publish workflow", errors)
    attest_master = _workflow_job(document, "attest-master", "docker-publish workflow", errors)
    promote_release = _workflow_job(document, "promote-release", "docker-publish workflow", errors)
    promote_master = _workflow_job(document, "promote-master", "docker-publish workflow", errors)
    release = _workflow_job(document, "release", "docker-publish workflow", errors)

    if verify is not None:
        steps = _workflow_steps(verify, "verify", errors)
        _validate_checkout(steps, "verify", errors)
        contract = _workflow_step(steps, "release-contract", "verify", errors)
        if contract is not None and _normalized_shell(contract) != RELEASE_VALIDATION_COMMAND:
            errors.append("verify job must execute the release validator and export its version")
        outputs = _mapping(verify.get("outputs"))
        if outputs != {"version": "${{ steps.release-contract.outputs.version }}"}:
            errors.append("verify job must export the structurally validated release version")

    if release_preflight is not None:
        if (
            _needs(release_preflight) != {"verify"}
            or release_preflight.get("if") != PUBLISH_REF_GATE
        ):
            errors.append("release-preflight must depend on verify and use the publish ref gate")
        steps = _workflow_steps(release_preflight, "release-preflight", errors)
        _validate_checkout(steps, "release-preflight", errors)
        resolve = _workflow_step(steps, "resolve-remote-tag", "release-preflight", errors)
        verify_signed = _workflow_step(steps, "verify-signed-tag", "release-preflight", errors)
        inspect_authorization = _workflow_step(
            steps, "inspect-release-authorization", "release-preflight", errors
        )
        authorize_new = _workflow_step(steps, "authorize-new-source", "release-preflight", errors)
        if resolve is not None:
            command = _normalized_shell(resolve)
            if resolve.get("if") != TAG_REF_GATE or any(
                token not in command
                for token in (
                    'scripts/validate_release.py --tag "${GITHUB_REF_NAME}" --verify-remote-tag',
                    '--expected-tag-commit "${GITHUB_SHA}"',
                    '--github-output "${GITHUB_OUTPUT}"',
                )
            ):
                errors.append("release preflight must resolve the exact isolated remote tag")
        if verify_signed is not None:
            _validate_signed_tag_step(
                verify_signed,
                expected_commit="${{ steps.resolve-remote-tag.outputs.tag_commit }}",
                expected_gate=TAG_REF_GATE,
                label="release preflight",
                errors=errors,
            )
        if inspect_authorization is not None:
            command = _normalized_shell(inspect_authorization)
            inspect_required = (
                "scripts/publish_github_release.py --phase inspect",
                '--target-commit "${{ steps.resolve-remote-tag.outputs.tag_commit }}"',
                '--image "${{ steps.image.outputs.name }}"',
                '--github-output "${GITHUB_OUTPUT}"',
            )
            if inspect_authorization.get("if") != TAG_REF_GATE or any(
                token not in command for token in inspect_required
            ):
                errors.append("release preflight must inspect exact durable authorization state")
        resolve_index = _step_index(steps, "resolve-remote-tag")
        verify_signed_index = _step_index(steps, "verify-signed-tag")
        inspect_index = _step_index(steps, "inspect-release-authorization")
        if (
            resolve_index is None
            or verify_signed_index != resolve_index + 1
            or inspect_index != verify_signed_index + 1
        ):
            errors.append(
                "signed tag verification must separate remote resolution from Release inspection"
            )
        if authorize_new is not None:
            command = _normalized_shell(authorize_new)
            expected_gate = (
                "startsWith(github.ref, 'refs/tags/v') && "
                "steps.inspect-release-authorization.outputs.state == 'absent'"
            )
            if " ".join(str(authorize_new.get("if", "")).split()) != expected_gate or any(
                token not in command
                for token in (
                    '--tag "${GITHUB_REF_NAME}" --verify-tag-origin',
                    '--expected-tag-commit "${{ steps.resolve-remote-tag.outputs.tag_commit }}"',
                )
            ):
                errors.append(
                    "only a new release may require fresh isolated tag-to-master authorization"
                )
        authorize_index = _step_index(steps, "authorize-new-source")
        if inspect_index is None or authorize_index != inspect_index + 1:
            errors.append("new source authorization must immediately follow Release inspection")
        expected_outputs = {
            "digest": "${{ steps.inspect-release-authorization.outputs.digest }}",
            "image": "${{ steps.image.outputs.name }}",
            "state": "${{ steps.inspect-release-authorization.outputs.state || 'none' }}",
            "tag_commit": "${{ steps.resolve-remote-tag.outputs.tag_commit }}",
        }
        if _mapping(release_preflight.get("outputs")) != expected_outputs:
            errors.append(
                "release-preflight must export exact state, digest, image, and tag commit"
            )

    if candidate is not None:
        if _needs(candidate) != {"verify", "release-preflight"}:
            errors.append("candidate job must depend on verify and release-preflight")
        if candidate.get("if") != PUBLISH_REF_GATE:
            errors.append(
                "candidate job must be gated to master or v-prefixed tags so manual runs on "
                "arbitrary branches remain verify-only"
            )
        steps = _workflow_steps(candidate, "candidate", errors)
        _validate_checkout(steps, "candidate", errors)
        metadata = _workflow_step(steps, "meta", "candidate", errors)
        validate_master_tags = _workflow_step(
            steps, "validate-master-image-tags", "candidate", errors
        )
        validate_release_tags = _workflow_step(steps, "validate-image-tags", "candidate", errors)
        inspect = _workflow_step(steps, "release-state", "candidate", errors)
        build = _workflow_step(steps, "build", "candidate", errors)
        select = _workflow_step(steps, "select", "candidate", errors)
        scan = _workflow_step(steps, "scan", "candidate", errors)
        buildkit = _workflow_step(steps, "verify-buildkit", "candidate", errors)

        if metadata is not None:
            metadata_with = _mapping(metadata.get("with"))
            expected_rules = [
                "type=semver,pattern={{version}}",
                "type=semver,pattern={{major}}.{{minor}}",
                "type=semver,pattern={{major}}",
                "type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/v') }}",
                "type=raw,value=edge,enable=${{ github.ref == 'refs/heads/master' }}",
                "type=sha,prefix=sha-,format=short,enable=${{ github.ref == 'refs/heads/master' }}",
            ]
            actual_rules: list[str] = []
            if metadata_with is not None and isinstance(metadata_with.get("tags"), str):
                actual_rules = [
                    line.strip()
                    for line in cast(str, metadata_with["tags"]).splitlines()
                    if line.strip()
                ]
            if metadata_with is None or metadata_with.get("flavor") != "latest=false":
                errors.append("metadata-action must disable automatic latest for SemVer tags")
            if not str(metadata.get("uses", "")).startswith("docker/metadata-action@"):
                errors.append("candidate metadata step must use docker/metadata-action")
            if actual_rules != expected_rules:
                errors.append(
                    "metadata-action tags must be release-only latest and SemVer aliases plus master-only edge and sha"
                )

        expected_validation_environment = {
            "PUBLISHED_IMAGE": "${{ steps.image.outputs.name }}",
            "PUBLISHED_TAGS": "${{ steps.meta.outputs.tags }}",
        }
        if validate_master_tags is not None:
            command = _normalized_shell(validate_master_tags)
            if (
                validate_master_tags.get("if") != "github.ref == 'refs/heads/master'"
                or _mapping(validate_master_tags.get("env")) != expected_validation_environment
                or validate_master_tags.get("shell") != "bash"
                or validate_master_tags.get("continue-on-error") not in (None, False)
                or any(
                    token not in command
                    for token in (
                        "scripts/validate_release.py",
                        '--master-commit "${GITHUB_SHA}"',
                        '--image-name "${PUBLISHED_IMAGE}"',
                        '--image-tags "${PUBLISHED_TAGS}"',
                    )
                )
            ):
                errors.append(
                    "master image metadata must be runtime-validated as edge and sha only"
                )
        if validate_release_tags is not None:
            command = _normalized_shell(validate_release_tags)
            if (
                validate_release_tags.get("if") != TAG_REF_GATE
                or _mapping(validate_release_tags.get("env")) != expected_validation_environment
                or validate_release_tags.get("shell") != "bash"
                or validate_release_tags.get("continue-on-error") not in (None, False)
                or any(
                    token not in command
                    for token in (
                        "scripts/validate_release.py",
                        '--tag "${GITHUB_REF_NAME}"',
                        '--image-name "${PUBLISHED_IMAGE}"',
                        '--image-tags "${PUBLISHED_TAGS}"',
                    )
                )
            ):
                errors.append(
                    "release image metadata must be runtime-validated as latest and SemVer only"
                )

        metadata_index = _step_index(steps, "meta")
        master_validation_index = _step_index(steps, "validate-master-image-tags")
        release_validation_index = _step_index(steps, "validate-image-tags")
        if (
            metadata_index is None
            or master_validation_index != metadata_index + 1
            or release_validation_index != master_validation_index + 1
        ):
            errors.append("image metadata must be validated immediately after extraction")

        if inspect is not None:
            command = _normalized_shell(inspect)
            if inspect.get("if") != TAG_REF_GATE or not all(
                token in command
                for token in (
                    "scripts/release_registry.py inspect",
                    '"${{ steps.image.outputs.name }}:${{ needs.verify.outputs.version }}"',
                    '--github-output "${GITHUB_OUTPUT}"',
                )
            ):
                errors.append("candidate must fail-closed inspect the immutable version alias")

        if build is not None:
            build_with = _mapping(build.get("with"))
            expected_output = (
                "type=image,name=${{ steps.image.outputs.name }},"
                "push-by-digest=true,name-canonical=true,push=true"
            )
            expected_build_gate = (
                "needs.release-preflight.outputs.state == 'none' || "
                "(needs.release-preflight.outputs.state == 'absent' && "
                "steps.release-state.outputs.exists != 'true')"
            )
            if " ".join(str(build.get("if", "")).split()) != expected_build_gate:
                errors.append(
                    "a rerun must reuse its draft digest or immutable alias instead of rebuilding"
                )
            if not str(build.get("uses", "")).startswith("docker/build-push-action@"):
                errors.append("candidate build step must use docker/build-push-action")
            if build_with is None or build_with.get("outputs") != expected_output:
                errors.append("candidate image must be pushed by digest without a public alias")
            if build_with is not None and ({"push", "tags"} & set(build_with)):
                errors.append("candidate build must not publish Docker tags")

        if select is not None:
            select_run = _normalized_shell(select)
            expected_select_environment = {
                "AUTHORIZED_DIGEST": "${{ needs.release-preflight.outputs.digest }}",
                "AUTHORIZATION_STATE": "${{ needs.release-preflight.outputs.state }}",
                "BUILT_DIGEST": "${{ steps.build.outputs.digest }}",
                "REMOTE_DIGEST": "${{ steps.release-state.outputs.digest }}",
                "REUSE_RELEASE": "${{ steps.release-state.outputs.exists }}",
            }
            if (
                not all(
                    token in select_run
                    for token in (
                        "AUTHORIZED_DIGEST",
                        "AUTHORIZATION_STATE",
                        "REMOTE_DIGEST",
                        "BUILT_DIGEST",
                        'echo "digest=${selected_digest}"',
                        'echo "reused=${reused}"',
                    )
                )
                or _mapping(select.get("env")) != expected_select_environment
            ):
                errors.append(
                    "candidate selection must reuse the remote digest or select the build"
                )

        if scan is not None:
            scan_with = _mapping(scan.get("with"))
            expected_image = "${{ steps.image.outputs.name }}@${{ steps.select.outputs.digest }}"
            if not str(scan.get("uses", "")).startswith("aquasecurity/trivy-action@"):
                errors.append("candidate scan step must use Trivy")
            if scan_with is None or scan_with.get("image-ref") != expected_image:
                errors.append("Trivy must scan the selected immutable candidate digest")
            if scan_with is None or scan_with.get("exit-code") != "1":
                errors.append("Trivy must fail the candidate job on blocked vulnerabilities")

        ordered_ids = ["release-state", "build", "select", "scan", "verify-buildkit"]
        indices = [_step_index(steps, step_id) for step_id in ordered_ids]
        if any(index is None for index in indices) or indices != sorted(cast(list[int], indices)):
            errors.append(
                "candidate order must be remote preflight, optional digest build, selection, Trivy, then BuildKit verification"
            )
        candidate_shell = " ".join(_normalized_shell(step) for step in steps)
        if "imagetools create" in candidate_shell or "docker push" in candidate_shell:
            errors.append("candidate job must never mutate a public image alias")
        if buildkit is not None:
            command = _normalized_shell(buildkit)
            if (
                "https://spdx.dev/Document" not in command
                or "https://slsa.dev/provenance/v1" not in command
            ):
                errors.append("candidate must verify BuildKit SBOM and SLSA attestations")

        expected_outputs = {
            "digest": "${{ steps.select.outputs.digest }}",
            "image": "${{ steps.image.outputs.name }}",
            "tags": "${{ steps.meta.outputs.tags }}",
            "reused": "${{ steps.select.outputs.reused }}",
        }
        if _mapping(candidate.get("outputs")) != expected_outputs:
            errors.append(
                "candidate job must export its exact digest, image, aliases, and reuse state"
            )

    if authorize_release is not None:
        if (
            _needs(authorize_release) != {"verify", "release-preflight", "candidate", "attest"}
            or authorize_release.get("if") != TAG_REF_GATE
        ):
            errors.append("authorize-release must wait for verified provenance and remain tag-only")
        steps = _workflow_steps(authorize_release, "authorize-release", errors)
        _validate_checkout(steps, "authorize-release", errors)
        rebind = _workflow_step(steps, "verify-authorized-tag", "authorize-release", errors)
        verify_signed = _workflow_step(steps, "verify-signed-tag", "authorize-release", errors)
        prepare = _workflow_step(steps, "prepare-release", "authorize-release", errors)
        if rebind is not None:
            command = _normalized_shell(rebind)
            if any(
                token not in command
                for token in (
                    '--tag "${GITHUB_REF_NAME}" --verify-remote-tag',
                    '--expected-tag-commit "${{ needs.release-preflight.outputs.tag_commit }}"',
                )
            ):
                errors.append("draft authorization must freshly fetch the exact remote tag")
        if verify_signed is not None:
            _validate_signed_tag_step(
                verify_signed,
                expected_commit="${{ needs.release-preflight.outputs.tag_commit }}",
                expected_gate=None,
                label="draft authorization",
                errors=errors,
            )
        if prepare is not None:
            command = _normalized_shell(prepare)
            prepare_required = (
                '"${RELEASE_AUTHORIZATION_STATE}" != "absent"',
                "scripts/publish_github_release.py --phase prepare",
                '--target-commit "${AUTHORIZED_COMMIT}"',
                '--digest "${{ needs.candidate.outputs.digest }}"',
                '--github-output "${GITHUB_OUTPUT}"',
            )
            if prepare.get("if") is not None or any(
                token not in command for token in prepare_required
            ):
                errors.append("draft authorization must be prepared only after verified provenance")
        rebind_index = _step_index(steps, "verify-authorized-tag")
        verify_signed_index = _step_index(steps, "verify-signed-tag")
        prepare_index = _step_index(steps, "prepare-release")
        if (
            rebind_index is None
            or verify_signed_index != rebind_index + 1
            or prepare_index != verify_signed_index + 1
        ):
            errors.append(
                "exact signed remote tag must be verified immediately before draft authorization"
            )
        if _mapping(authorize_release.get("outputs")) != {
            "digest": "${{ steps.prepare-release.outputs.digest }}",
            "release_id": "${{ steps.prepare-release.outputs.release_id }}",
            "state": "${{ steps.prepare-release.outputs.state }}",
            "tag_commit": "${{ needs.release-preflight.outputs.tag_commit }}",
        }:
            errors.append("authorize-release must export the complete durable authorization")

    if attest is not None:
        _validate_attestation_job(
            attest,
            job_name="attest",
            expected_gate=TAG_REF_GATE,
            require_reuse_preflight=True,
            errors=errors,
        )
    if attest_master is not None:
        _validate_attestation_job(
            attest_master,
            job_name="attest-master",
            expected_gate="github.ref == 'refs/heads/master'",
            require_reuse_preflight=False,
            errors=errors,
        )

    if promote_release is not None:
        if _needs(promote_release) != {
            "verify",
            "release-preflight",
            "candidate",
            "authorize-release",
            "attest",
        }:
            errors.append(
                "promote-release must wait for durable authorization and verified OIDC provenance"
            )
        if promote_release.get("if") != TAG_REF_GATE:
            errors.append("promote-release must be tag-only")
        steps = _workflow_steps(promote_release, "promote-release", errors)
        _validate_checkout(steps, "promote-release", errors)
        recheck = _workflow_step(steps, "recheck-release-authorization", "promote-release", errors)
        require_authorization = _workflow_step(
            steps, "require-release-authorization", "promote-release", errors
        )
        authorize = _workflow_step(steps, "authorize-alias-mutation", "promote-release", errors)
        verify_signed = _workflow_step(steps, "verify-signed-tag", "promote-release", errors)
        promote = _workflow_step(steps, "promote", "promote-release", errors)
        verify_published = _workflow_step(
            steps, "verify-published-alias", "promote-release", errors
        )
        if recheck is not None:
            command = _normalized_shell(recheck)
            if any(
                token not in command
                for token in (
                    "scripts/publish_github_release.py --phase inspect",
                    '--target-commit "${{ needs.authorize-release.outputs.tag_commit }}"',
                    '--github-output "${GITHUB_OUTPUT}"',
                )
            ):
                errors.append("promotion must freshly inspect the durable Release authorization")
        if require_authorization is not None:
            environment = _mapping(require_authorization.get("env"))
            command = _normalized_shell(require_authorization)
            if (
                environment is None
                or environment.get("AUTHORIZED_DIGEST")
                != "${{ needs.authorize-release.outputs.digest }}"
                or environment.get("CURRENT_DIGEST")
                != "${{ steps.recheck-release-authorization.outputs.digest }}"
                or environment.get("AUTHORIZED_STATE")
                != "${{ needs.authorize-release.outputs.state }}"
                or environment.get("CURRENT_STATE")
                != "${{ steps.recheck-release-authorization.outputs.state }}"
                or "CURRENT_STATE" not in command
                or "CANDIDATE_DIGEST" not in command
                or '"${AUTHORIZED_STATE}" == "published"' not in command
            ):
                errors.append(
                    "promotion must require the unchanged recoverable digest authorization"
                )
        if authorize is not None:
            command = _normalized_shell(authorize)
            rebind_required = (
                "scripts/validate_release.py",
                '--tag "${GITHUB_REF_NAME}" --verify-remote-tag',
                '--expected-tag-commit "${{ needs.authorize-release.outputs.tag_commit }}"',
            )
            if any(token not in command for token in rebind_required):
                errors.append(
                    "alias mutation authorization must rebind the exact remote tag to the draft commit"
                )
        if verify_signed is not None:
            _validate_signed_tag_step(
                verify_signed,
                expected_commit="${{ needs.authorize-release.outputs.tag_commit }}",
                expected_gate=None,
                label="release alias promotion",
                errors=errors,
            )
        authorize_index = _step_index(steps, "authorize-alias-mutation")
        verify_signed_index = _step_index(steps, "verify-signed-tag")
        promote_index = _step_index(steps, "promote")
        if (
            authorize_index is None
            or verify_signed_index != authorize_index + 1
            or promote_index != verify_signed_index + 1
        ):
            errors.append(
                "tag origin and SSH signature must be rechecked immediately before first alias mutation"
            )
        if promote is not None:
            command = _normalized_shell(promote)
            if promote.get("if") != "steps.recheck-release-authorization.outputs.state == 'draft'":
                errors.append("published release reruns must not rewrite moving image aliases")
            for token in (
                "scripts/release_registry.py promote",
                '--digest "${{ needs.candidate.outputs.digest }}"',
                '--immutable-alias "${{ needs.candidate.outputs.image }}:${{ needs.verify.outputs.version }}"',
            ):
                if token not in command:
                    errors.append(
                        "release alias promotion must use state-aware immutable preflight"
                    )
                    break
        if verify_published is not None:
            command = _normalized_shell(verify_published)
            if (
                verify_published.get("if")
                != "steps.recheck-release-authorization.outputs.state == 'published'"
                or "scripts/release_registry.py verify" not in command
                or '--digest "${{ needs.candidate.outputs.digest }}"' not in command
            ):
                errors.append(
                    "published release reruns must verify only their immutable version alias"
                )

    if promote_master is not None:
        if _needs(promote_master) != {"verify", "candidate", "attest-master"}:
            errors.append("promote-master must wait for verified master OIDC provenance")
        if promote_master.get("if") != "github.ref == 'refs/heads/master'":
            errors.append("promote-master must be master-only")
        steps = _workflow_steps(promote_master, "promote-master", errors)
        promote = _workflow_step(steps, "promote", "promote-master", errors)
        if promote is not None and "scripts/release_registry.py promote" not in _normalized_shell(
            promote
        ):
            errors.append("master aliases must use verified state-aware promotion")

    if release is not None:
        if _needs(release) != {
            "verify",
            "candidate",
            "authorize-release",
            "attest",
            "promote-release",
        }:
            errors.append("release job must wait for durable authorization and verified promotion")
        if release.get("if") != TAG_REF_GATE:
            errors.append("release job must be tag-only")
        steps = _workflow_steps(release, "release", errors)
        _validate_checkout(steps, "release", errors)
        authorize = _workflow_step(steps, "verify-authorized-tag", "release", errors)
        verify_signed = _workflow_step(steps, "verify-signed-tag", "release", errors)
        publish = _workflow_step(steps, "finalize-release", "release", errors)
        if authorize is not None:
            command = _normalized_shell(authorize)
            if (
                "scripts/validate_release.py" not in command
                or '--tag "${GITHUB_REF_NAME}" --verify-remote-tag' not in command
                or '--expected-tag-commit "${{ needs.authorize-release.outputs.tag_commit }}"'
                not in command
            ):
                errors.append("Release finalization must rebind the exact authorized remote tag")
        if verify_signed is not None:
            _validate_signed_tag_step(
                verify_signed,
                expected_commit="${{ needs.authorize-release.outputs.tag_commit }}",
                expected_gate=None,
                label="Release finalization",
                errors=errors,
            )
        authorize_index = _step_index(steps, "verify-authorized-tag")
        verify_signed_index = _step_index(steps, "verify-signed-tag")
        publish_index = _step_index(steps, "finalize-release")
        if (
            authorize_index is None
            or verify_signed_index != authorize_index + 1
            or publish_index != verify_signed_index + 1
        ):
            errors.append(
                "authorized signed remote tag must be rechecked immediately before finalization"
            )
        if publish is not None:
            command = _normalized_shell(publish)
            finalize_required = (
                "scripts/publish_github_release.py",
                "--phase finalize",
                '--target-commit "${{ needs.authorize-release.outputs.tag_commit }}"',
                '--image "${{ needs.candidate.outputs.image }}"',
                '--digest "${{ needs.candidate.outputs.digest }}"',
                '--retry-delays "${RELEASE_RETRY_DELAYS}"',
            )
            if publish.get("if") is not None or any(
                token not in command for token in finalize_required
            ):
                errors.append(
                    "Release must finalize the exact immutable, retrying, asset-free draft"
                )
        if any("softprops/action-gh-release@" in str(step.get("uses", "")) for step in steps):
            errors.append("Release must not delegate partial-state handling to softprops")

    return errors


def validate_repository_workflows(project_root: Path) -> list[str]:
    """Require every action SHA pin and every job's exact least-privilege permissions."""

    workflow_root = project_root / ".github" / "workflows"
    paths = sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
    errors: list[str] = []
    seen_names: set[str] = set()
    for path in paths:
        seen_names.add(path.name)
        document, parse_errors = _parse_workflow(
            path.read_text(encoding="utf-8"), f"{path.name} workflow"
        )
        errors.extend(parse_errors)
        if document is None:
            continue
        if "permissions" in document:
            errors.append(f"{path.name} must declare permissions explicitly on every job")
        jobs = _mapping(document.get("jobs"))
        if jobs is None:
            errors.append(f"{path.name} must declare jobs")
            continue
        expected_jobs = EXPECTED_JOB_PERMISSIONS.get(path.name)
        if expected_jobs is None:
            errors.append(f"{path.name} has no reviewed job-permission contract")
            continue
        if set(jobs) != set(expected_jobs):
            errors.append(f"{path.name} job inventory must be exactly {sorted(expected_jobs)!r}")
        for job_name, raw_job in jobs.items():
            job = _mapping(raw_job)
            if job is None:
                errors.append(f"{path.name}:{job_name} must be a mapping")
                continue
            expected_permissions = expected_jobs.get(job_name)
            if _mapping(job.get("permissions")) != expected_permissions:
                errors.append(
                    f"{path.name}:{job_name} permissions must be exactly {expected_permissions!r}"
                )
            job_uses = job.get("uses")
            uses_values: list[object] = [job_uses] if job_uses is not None else []
            raw_steps = _sequence(job.get("steps")) or []
            uses_values.extend(
                step.get("uses") for step in raw_steps if isinstance(step, dict) and "uses" in step
            )
            for uses in uses_values:
                if not isinstance(uses, str):
                    errors.append(f"{path.name}:{job_name} contains a non-string action reference")
                    continue
                if uses.startswith("./") or uses.startswith("docker://"):
                    continue
                if PINNED_ACTION_PATTERN.fullmatch(uses) is None:
                    errors.append(
                        f"{path.name}:{job_name} action must be pinned to a full commit SHA: {uses}"
                    )
    missing = set(EXPECTED_JOB_PERMISSIONS) - seen_names
    for name in sorted(missing):
        errors.append(f"required workflow is missing: {name}")
    return errors


def validate_ci_workflow_text(workflow: str) -> list[str]:
    """Structurally require pinned actionlint execution in the CI lint job."""

    document, errors = _parse_workflow(workflow, "CI workflow")
    if document is None:
        return errors
    lint = _workflow_job(document, "lint", "CI workflow", errors)
    if lint is None:
        return errors
    steps = _workflow_steps(lint, "CI lint", errors)
    install = _workflow_step(steps, "install-actionlint", "CI lint", errors)
    actionlint = _workflow_step(steps, "actionlint", "CI lint", errors)
    if install is not None:
        environment = _mapping(install.get("env"))
        expected_environment = {
            "ACTIONLINT_SHA256": ACTIONLINT_SHA256,
            "ACTIONLINT_VERSION": ACTIONLINT_VERSION,
        }
        install_run = _normalized_shell(install)
        if environment != expected_environment:
            errors.append("CI must pin actionlint version and Linux archive SHA-256")
        if (
            "https://github.com/rhysd/actionlint/releases/download/" not in install_run
            or "sha256sum --check" not in install_run
            or 'install -m 0755 actionlint "${RUNNER_TEMP}/actionlint"' not in install_run
        ):
            errors.append("CI must checksum and install the pinned actionlint binary")
    if actionlint is not None and _normalized_shell(actionlint) != '"${RUNNER_TEMP}/actionlint"':
        errors.append("CI lint job must execute actionlint over all workflows")

    install_index = _step_index(steps, "install-actionlint")
    actionlint_index = _step_index(steps, "actionlint")
    if install_index is None or actionlint_index is None or install_index >= actionlint_index:
        errors.append("CI must install actionlint before executing it")
    return errors


def validate_tag_ruleset_text(ruleset_text: str) -> list[str]:
    """Validate the checked-in immutable v* tag ruleset payload."""

    try:
        document = json.loads(ruleset_text)
    except json.JSONDecodeError as exc:
        return [f"release tag ruleset is not valid JSON: {exc}"]
    if not isinstance(document, dict):
        return ["release tag ruleset must contain a JSON object"]

    errors: list[str] = []
    if document.get("target") != "tag" or document.get("enforcement") != "active":
        errors.append("release tag ruleset must actively target tags")
    if document.get("bypass_actors") != []:
        errors.append("release tag ruleset must not declare bypass actors")
    conditions = document.get("conditions")
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if not isinstance(ref_name, dict) or ref_name != {
        "include": ["refs/tags/v*"],
        "exclude": [],
    }:
        errors.append("release tag ruleset must target only refs/tags/v*")

    rules = document.get("rules")
    rule_map = {
        rule.get("type"): rule
        for rule in rules or []
        if isinstance(rule, dict) and isinstance(rule.get("type"), str)
    }
    if set(rule_map) != {"deletion", "update"}:
        errors.append("release tag ruleset must block both deletion and update")
    update = rule_map.get("update")
    if not isinstance(update, dict) or update.get("parameters") != {
        "update_allows_fetch_and_merge": False
    }:
        errors.append("release tag update rule must be fail-closed")
    return errors


def validate_release_documentation(project_root: Path, version: str) -> list[str]:
    """Require the changelog and pull example to describe the current version."""

    readme = (project_root / "README.md").read_text(encoding="utf-8")
    changelog = (project_root / "CHANGELOG.md").read_text(encoding="utf-8")
    errors: list[str] = []
    image_reference = f"djenis-ai-agent:{version}"
    if image_reference not in readme:
        errors.append(f"README.md must document the current image tag {image_reference}")
    if f"djenis-ai-agent:v{version}" in readme:
        errors.append("README.md must not use the v-prefixed Git tag as an image tag")
    if f"## {version} -" not in changelog:
        errors.append(f"CHANGELOG.md must contain a {version} release entry")
    if ".github/rulesets/README.md" not in readme:
        errors.append("README.md must link the immutable release-tag ruleset instructions")
    return errors


def validate_image_metadata(
    *, image_name: str, metadata_tags: str, expected_tags: tuple[str, ...]
) -> None:
    """Require exactly the expected aliases from metadata-action."""

    image_name = image_name.rstrip("/")
    actual = tuple(line.strip() for line in metadata_tags.splitlines() if line.strip())
    expected = tuple(f"{image_name}:{tag}" for tag in expected_tags)
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ReleaseContractError(
            "published image tag metadata does not match the release contract; "
            f"expected {sorted(expected)!r}, got {sorted(actual)!r}"
        )


def _run_git(project_root: Path, arguments: tuple[str, ...]) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise ReleaseContractError("Git is required to validate release tag origin")
    try:
        result = subprocess.run(  # nosec B603
            [git_executable, "-C", str(project_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        raise ReleaseContractError(
            f"Git command failed while validating release tag origin: {detail.strip()}"
        ) from exc
    return result.stdout.strip()


def verify_release_tag_origin(
    project_root: Path, tag: str, *, git_runner: GitRunner | None = None
) -> ReleaseTagOrigin:
    """Fail unless the dereferenced release tag equals the fetched origin/master commit."""

    runner = git_runner or (lambda arguments: _run_git(project_root, arguments))
    if re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", tag) is None:
        raise ReleaseContractError("remote release tag must be stable v-prefixed SemVer")
    remote_tag_ref = f"{REMOTE_TAG_REF_ROOT}/{tag}"
    runner(
        (
            "fetch",
            "--atomic",
            "--force",
            "--no-tags",
            "--no-write-fetch-head",
            "origin",
            f"+refs/tags/{tag}:{remote_tag_ref}",
            f"+refs/heads/master:{REMOTE_MASTER_REF}",
        )
    )
    tag_commit = runner(("rev-parse", f"{remote_tag_ref}^{{commit}}")).strip()
    master_commit = runner(("rev-parse", f"{REMOTE_MASTER_REF}^{{commit}}")).strip()
    if GIT_COMMIT_PATTERN.fullmatch(tag_commit) is None:
        raise ReleaseContractError(f"could not dereference release tag {tag!r} to a commit")
    if GIT_COMMIT_PATTERN.fullmatch(master_commit) is None:
        raise ReleaseContractError("could not resolve fetched origin/master to a commit")
    if tag_commit.lower() != master_commit.lower():
        raise ReleaseContractError(
            "release tag commit must equal origin/master exactly; "
            f"tag={tag_commit}, origin/master={master_commit}"
        )
    return ReleaseTagOrigin(tag_commit=tag_commit.lower(), master_commit=master_commit.lower())


def verify_remote_release_tag(
    project_root: Path,
    tag: str,
    *,
    expected_commit: str | None = None,
    git_runner: GitRunner | None = None,
) -> str:
    """Fetch only the exact remote tag into an isolated ref and dereference it."""

    if re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", tag) is None:
        raise ReleaseContractError("remote release tag must be stable v-prefixed SemVer")
    if expected_commit is not None and GIT_COMMIT_PATTERN.fullmatch(expected_commit) is None:
        raise ReleaseContractError("expected release tag commit must be an exact Git object id")
    runner = git_runner or (lambda arguments: _run_git(project_root, arguments))
    remote_tag_ref = f"{REMOTE_TAG_REF_ROOT}/{tag}"
    runner(
        (
            "fetch",
            "--force",
            "--no-tags",
            "--no-write-fetch-head",
            "origin",
            f"+refs/tags/{tag}:{remote_tag_ref}",
        )
    )
    tag_commit = runner(("rev-parse", f"{remote_tag_ref}^{{commit}}")).strip()
    if GIT_COMMIT_PATTERN.fullmatch(tag_commit) is None:
        raise ReleaseContractError(f"could not dereference remote release tag {tag!r}")
    normalized = tag_commit.lower()
    if expected_commit is not None and normalized != expected_commit.lower():
        raise ReleaseContractError(
            "remote release tag must equal the durable authorization commit exactly; "
            f"expected={expected_commit.lower()}, actual={normalized}"
        )
    return normalized


def validate_release_contract(
    project_root: Path,
    *,
    tag: str | None = None,
    image_name: str | None = None,
    image_tags: str | None = None,
    master_commit: str | None = None,
    verify_tag_origin: bool = False,
    verify_remote_tag: bool = False,
    expected_tag_commit: str | None = None,
    git_runner: GitRunner | None = None,
) -> ReleaseContract:
    """Validate repository and optional tag-event metadata as one contract."""

    versions = repository_versions(project_root)
    if len(set(versions.values())) != 1:
        details = ", ".join(f"{source}={version}" for source, version in versions.items())
        raise ReleaseContractError(f"project version sources disagree: {details}")

    version = next(iter(versions.values()))
    expected_image_tags = image_tags_for_version(version)

    workflow_path = project_root / WORKFLOW_PATH
    workflow_errors = validate_workflow_text(workflow_path.read_text(encoding="utf-8"))
    ci_errors = validate_ci_workflow_text(
        (project_root / CI_WORKFLOW_PATH).read_text(encoding="utf-8")
    )
    ruleset_errors = validate_tag_ruleset_text(
        (project_root / TAG_RULESET_PATH).read_text(encoding="utf-8")
    )
    repository_workflow_errors = validate_repository_workflows(project_root)
    structural_errors = workflow_errors + ci_errors + ruleset_errors + repository_workflow_errors
    if structural_errors:
        raise ReleaseContractError("; ".join(structural_errors))

    documentation_errors = validate_release_documentation(project_root, version)
    if documentation_errors:
        raise ReleaseContractError("; ".join(documentation_errors))

    if tag is not None and tag != f"v{version}":
        raise ReleaseContractError(
            f"Git tag must be v{version} for project version {version}, got {tag!r}"
        )
    tag_commit: str | None = None
    if verify_tag_origin and verify_remote_tag:
        raise ReleaseContractError(
            "tag-origin and remote-tag verification modes are mutually exclusive"
        )
    if verify_tag_origin:
        if tag is None:
            raise ReleaseContractError("tag-origin verification requires an explicit Git tag")
        origin = verify_release_tag_origin(project_root, tag, git_runner=git_runner)
        tag_commit = origin.tag_commit
        if expected_tag_commit is not None and tag_commit != expected_tag_commit.lower():
            raise ReleaseContractError(
                "fresh tag-to-master authorization changed after remote tag resolution"
            )
    elif verify_remote_tag:
        if tag is None:
            raise ReleaseContractError("remote-tag verification requires an explicit Git tag")
        tag_commit = verify_remote_release_tag(
            project_root,
            tag,
            expected_commit=expected_tag_commit,
            git_runner=git_runner,
        )
    elif expected_tag_commit is not None:
        raise ReleaseContractError(
            "--expected-tag-commit requires tag-origin or remote-tag verification"
        )

    if (image_name is None) != (image_tags is None):
        raise ReleaseContractError("--image-name and --image-tags must be provided together")
    if image_name is not None and image_tags is not None:
        if (tag is None) == (master_commit is None):
            raise ReleaseContractError(
                "published image metadata requires exactly one release tag or master commit"
            )
        expected_tags = (
            expected_image_tags
            if tag is not None
            else master_image_tags_for_commit(cast(str, master_commit))
        )
        validate_image_metadata(
            image_name=image_name,
            metadata_tags=image_tags,
            expected_tags=expected_tags,
        )
    elif master_commit is not None:
        raise ReleaseContractError("--master-commit requires image name and tag metadata")

    return ReleaseContract(
        version=version,
        image_tags=expected_image_tags,
        tag_commit=tag_commit,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--tag", help="Git release tag, including its leading v")
    parser.add_argument("--image-name", help="Fully qualified GHCR image name")
    parser.add_argument("--image-tags", help="Newline-delimited docker/metadata-action output")
    parser.add_argument("--master-commit", help="Exact master commit used for edge and sha aliases")
    parser.add_argument(
        "--verify-tag-origin",
        action="store_true",
        help="Fetch origin/master and require the dereferenced release tag to equal it",
    )
    parser.add_argument(
        "--verify-remote-tag",
        action="store_true",
        help="Fetch and dereference only the exact remote release tag in an isolated ref",
    )
    parser.add_argument(
        "--expected-tag-commit",
        help="Require the freshly fetched remote tag to match this exact commit",
    )
    parser.add_argument("--github-output", type=Path, help="Append the validated version here")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        contract = validate_release_contract(
            args.project_root.resolve(),
            tag=args.tag,
            image_name=args.image_name,
            image_tags=args.image_tags,
            master_commit=args.master_commit,
            verify_tag_origin=args.verify_tag_origin,
            verify_remote_tag=args.verify_remote_tag,
            expected_tag_commit=args.expected_tag_commit,
        )
        if args.github_output is not None:
            with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
                output.write(f"version={contract.version}\n")
                if contract.tag_commit is not None:
                    output.write(f"tag_commit={contract.tag_commit}\n")
    except (OSError, SyntaxError, tomllib.TOMLDecodeError, ReleaseContractError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    aliases = (
        master_image_tags_for_commit(args.master_commit)
        if args.master_commit is not None
        else contract.image_tags
    )
    context = "Master" if args.master_commit is not None else f"Release v{contract.version}"
    print(f"{context} contract valid: GHCR aliases {', '.join(aliases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
