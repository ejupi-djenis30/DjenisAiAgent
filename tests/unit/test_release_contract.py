"""Regression tests for the release version, workflow, and container contract."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tarfile
from pathlib import Path

import pytest
from scripts.validate_release import (
    ReleaseContractError,
    image_tags_for_version,
    master_image_tags_for_commit,
    validate_ci_workflow_text,
    validate_image_metadata,
    validate_local_only_dependency_contract,
    validate_pages_workflow_text,
    validate_rehearsal_oci_archive,
    validate_release_contract,
    validate_release_documentation,
    validate_repository_workflows,
    validate_tag_ruleset_text,
    validate_workflow_text,
    verify_rehearsal_source,
    verify_release_tag_origin,
    verify_remote_release_tag,
)
from scripts.verify_github_tag import GitHubTagVerificationError, verify_github_release_tag

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCKER_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "docker-publish.yml"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
PAGES_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "pages.yml"
TAG_RULESET = PROJECT_ROOT / ".github" / "rulesets" / "immutable-v-tags.json"
IMAGE_NAME = "ghcr.io/ejupi-djenis30/djenis-ai-agent"


def _docker_workflow() -> str:
    return DOCKER_WORKFLOW.read_text(encoding="utf-8")


def _copy_workflows(destination: Path) -> Path:
    workflow_root = destination / ".github" / "workflows"
    shutil.copytree(PROJECT_ROOT / ".github" / "workflows", workflow_root)
    return workflow_root


def _json_blob(document: object) -> tuple[str, bytes]:
    raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()}", raw


def _write_rehearsal_oci(
    destination: Path,
    *,
    predicates: tuple[str, ...] = (
        "https://spdx.dev/Document",
        "https://slsa.dev/provenance/v1",
    ),
) -> tuple[Path, str]:
    image_digest, image_manifest = _json_blob(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "digest": f"sha256:{'c' * 64}",
                "size": 2,
            },
            "layers": [],
        }
    )
    attestation_digest, attestation_manifest = _json_blob(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "layers": [
                {
                    "mediaType": "application/vnd.in-toto+json",
                    "digest": f"sha256:{index:064x}",
                    "size": 2,
                    "annotations": {"in-toto.io/predicate-type": predicate},
                }
                for index, predicate in enumerate(predicates, start=1)
            ],
        }
    )
    index_document = {
        "schemaVersion": 2,
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": image_digest,
                "size": len(image_manifest),
            },
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": attestation_digest,
                "size": len(attestation_manifest),
                "annotations": {
                    "vnd.docker.reference.type": "attestation-manifest",
                    "vnd.docker.reference.digest": image_digest,
                },
            },
        ],
    }
    index_raw = json.dumps(index_document, separators=(",", ":"), sort_keys=True).encode()
    archive_path = destination / "rehearsal.oci.tar"
    members = {
        "index.json": index_raw,
        "oci-layout": b'{"imageLayoutVersion":"1.0.0"}',
        f"blobs/sha256/{image_digest.removeprefix('sha256:')}": image_manifest,
        f"blobs/sha256/{attestation_digest.removeprefix('sha256:')}": attestation_manifest,
    }
    with tarfile.open(archive_path, mode="w") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return archive_path, image_digest


def test_repository_contract_matches_v0_3_0_and_release_image_aliases() -> None:
    expected_tags = ("0.3.0", "0.3", "0", "latest")
    metadata_tags = "\n".join(f"{IMAGE_NAME}:{tag}" for tag in expected_tags)

    contract = validate_release_contract(
        PROJECT_ROOT,
        tag="v0.3.0",
        image_name=IMAGE_NAME,
        image_tags=metadata_tags,
    )

    assert contract.version == "0.3.0"
    assert contract.image_tags == expected_tags


def test_repository_contract_accepts_only_the_exact_master_aliases() -> None:
    commit = "a" * 40
    metadata_tags = f"{IMAGE_NAME}:edge\n{IMAGE_NAME}:sha-aaaaaaa"

    contract = validate_release_contract(
        PROJECT_ROOT,
        master_commit=commit,
        image_name=IMAGE_NAME,
        image_tags=metadata_tags,
    )

    assert contract.version == "0.3.0"


def test_git_tag_must_match_the_project_version_exactly() -> None:
    with pytest.raises(ReleaseContractError, match=r"Git tag must be v0\.3\.0"):
        validate_release_contract(PROJECT_ROOT, tag="v0.2.0")


def test_rehearsal_source_requires_local_event_and_fresh_master_to_match() -> None:
    commit = "a" * 40
    calls: list[tuple[str, ...]] = []

    def runner(arguments: tuple[str, ...]) -> str:
        calls.append(arguments)
        if arguments[:1] == ("fetch",):
            return ""
        if arguments == ("rev-parse", "HEAD^{commit}"):
            return commit
        if arguments == (
            "rev-parse",
            "refs/djenis-release-verification/rehearsal/master^{commit}",
        ):
            return commit
        raise AssertionError(arguments)

    source = verify_rehearsal_source(
        PROJECT_ROOT,
        expected_commit=commit,
        event_ref="refs/heads/master",
        default_branch="master",
        git_runner=runner,
    )

    assert source == commit
    assert calls[0] == (
        "fetch",
        "--atomic",
        "--force",
        "--no-tags",
        "--no-write-fetch-head",
        "origin",
        "+refs/heads/master:refs/djenis-release-verification/rehearsal/master",
    )


@pytest.mark.parametrize(
    ("event_ref", "default_branch", "message"),
    [
        ("refs/heads/feature", "master", "dispatched from refs/heads/master"),
        ("refs/heads/master", "main", "master to remain the default branch"),
    ],
)
def test_rehearsal_source_rejects_non_default_dispatches(
    event_ref: str,
    default_branch: str,
    message: str,
) -> None:
    with pytest.raises(ReleaseContractError, match=message):
        verify_rehearsal_source(
            PROJECT_ROOT,
            expected_commit="a" * 40,
            event_ref=event_ref,
            default_branch=default_branch,
            git_runner=lambda _arguments: pytest.fail("unsafe source must fail before fetch"),
        )


def test_rehearsal_source_rejects_a_stale_dispatch_sha() -> None:
    commits = iter(("", "a" * 40, "b" * 40))

    with pytest.raises(ReleaseContractError, match="local HEAD, event SHA"):
        verify_rehearsal_source(
            PROJECT_ROOT,
            expected_commit="a" * 40,
            event_ref="refs/heads/master",
            default_branch="master",
            git_runner=lambda _arguments: next(commits),
        )


def test_rehearsal_oci_archive_binds_digest_sbom_and_provenance(tmp_path: Path) -> None:
    archive, digest = _write_rehearsal_oci(tmp_path)

    validate_rehearsal_oci_archive(archive, expected_digest=digest)

    with pytest.raises(ReleaseContractError, match="Buildx-reported digest"):
        validate_rehearsal_oci_archive(archive, expected_digest=f"sha256:{'f' * 64}")


def test_rehearsal_oci_archive_fails_when_provenance_is_missing(tmp_path: Path) -> None:
    archive, digest = _write_rehearsal_oci(
        tmp_path,
        predicates=("https://spdx.dev/Document",),
    )

    with pytest.raises(ReleaseContractError, match=r"slsa\.dev/provenance"):
        validate_rehearsal_oci_archive(archive, expected_digest=digest)


@pytest.mark.parametrize(
    "invalid",
    [
        "\n".join(
            [
                f"{IMAGE_NAME}:v0.2.1",
                f"{IMAGE_NAME}:0.2",
                f"{IMAGE_NAME}:0",
                f"{IMAGE_NAME}:latest",
            ]
        ),
        "\n".join(
            [
                f"{IMAGE_NAME}:0.2.1",
                f"{IMAGE_NAME}:0.2",
                f"{IMAGE_NAME}:0",
            ]
        ),
        "\n".join(
            [
                f"{IMAGE_NAME}:0.2.1",
                f"{IMAGE_NAME}:0.2",
                f"{IMAGE_NAME}:0",
                f"{IMAGE_NAME}:latest",
                f"{IMAGE_NAME}:edge",
            ]
        ),
    ],
)
def test_image_metadata_requires_exact_aliases(invalid: str) -> None:
    expected_tags = image_tags_for_version("0.2.1")

    with pytest.raises(ReleaseContractError, match="does not match"):
        validate_image_metadata(
            image_name=IMAGE_NAME,
            metadata_tags=invalid,
            expected_tags=expected_tags,
        )


def test_master_image_metadata_accepts_only_edge_and_the_exact_short_sha() -> None:
    commit = "ABCDEF1234567890ABCDEF1234567890ABCDEF12"
    expected_tags = master_image_tags_for_commit(commit)

    validate_image_metadata(
        image_name=IMAGE_NAME,
        metadata_tags=f"{IMAGE_NAME}:edge\n{IMAGE_NAME}:sha-abcdef1",
        expected_tags=expected_tags,
    )
    with pytest.raises(ReleaseContractError, match="does not match"):
        validate_image_metadata(
            image_name=IMAGE_NAME,
            metadata_tags=f"{IMAGE_NAME}:latest\n{IMAGE_NAME}:sha-abcdef1",
            expected_tags=expected_tags,
        )


def test_workflow_comments_cannot_satisfy_semver_flavor_contract() -> None:
    workflow = _docker_workflow()
    broken = workflow.replace(
        "          flavor: latest=false\n",
        "          # flavor: latest=false\n",
    )
    assert broken != workflow

    errors = validate_workflow_text(broken)

    assert "metadata-action must disable automatic latest for SemVer tags" in errors


def test_release_candidate_requires_the_complete_windows_runtime_gate() -> None:
    workflow = _docker_workflow()
    partial_suite = workflow.replace(
        "        id: windows-tests\n        run: uv run --frozen --no-sync pytest tests/unit\n",
        "        id: windows-tests\n"
        "        run: uv run --frozen --no-sync pytest tests/unit/test_config.py\n",
        1,
    )
    detached_candidate = workflow.replace(
        "needs: [verify, verify-windows, release-preflight]",
        "needs: [verify, release-preflight]",
        1,
    )

    assert "verify-windows must execute the complete Windows unit suite" in (
        validate_workflow_text(partial_suite)
    )
    assert (
        "candidate job must depend on verify, verify-windows, and release-preflight"
        in validate_workflow_text(detached_candidate)
    )


def test_master_and_release_image_aliases_are_strictly_separated() -> None:
    workflow = _docker_workflow()

    assert (
        "type=raw,value=latest,enable=${{ github.event_name == 'push' && "
        "startsWith(github.ref, 'refs/tags/v') }}" in workflow
    )
    assert (
        "type=raw,value=edge,enable=${{ github.event_name == 'push' && "
        "github.ref == 'refs/heads/master' }}" in workflow
    )
    assert (
        "type=sha,prefix=sha-,format=short,enable=${{ github.event_name == 'push' && "
        "github.ref == 'refs/heads/master' }}" in workflow
    )
    assert "id: validate-master-image-tags" in workflow
    assert '--master-commit "${GITHUB_SHA}"' in workflow

    broken = workflow.replace(
        "type=raw,value=edge,enable=${{ github.event_name == 'push' && "
        "github.ref == 'refs/heads/master' }}",
        "type=raw,value=latest,enable=${{ github.event_name == 'push' && "
        "github.ref == 'refs/heads/master' }}",
        1,
    )
    assert (
        "metadata-action tags must be release-only latest and SemVer aliases plus master-only edge and sha"
        in validate_workflow_text(broken)
    )

    broken_runtime_gate = workflow.replace(
        '--master-commit "${GITHUB_SHA}"',
        '--master-commit "deadbeef"',
        1,
    )
    assert "master image metadata must be runtime-validated as edge and sha only" in (
        validate_workflow_text(broken_runtime_gate)
    )

    soft_runtime_gate = workflow.replace(
        "        id: validate-master-image-tags\n",
        "        id: validate-master-image-tags\n        continue-on-error: ${{ true }}\n",
        1,
    )
    assert "master image metadata must be runtime-validated as edge and sha only" in (
        validate_workflow_text(soft_runtime_gate)
    )


def test_workflow_dispatch_requires_the_exact_unreleased_tag() -> None:
    workflow = _docker_workflow()
    wrong_default = workflow.replace("        default: v0.3.0\n", "        default: v0.2.2\n", 1)
    optional = workflow.replace("        required: true\n", "        required: false\n", 1)

    expected = "docker-publish workflow_dispatch must require expected_tag with default v0.3.0"
    assert expected in validate_workflow_text(wrong_default)
    assert expected in validate_workflow_text(optional)


def test_rehearsal_is_offline_fail_closed_and_source_bound() -> None:
    workflow = _docker_workflow()
    publish_build = workflow.replace(
        "          outputs: type=oci,dest=${{ runner.temp }}/djenis-ai-agent-rehearsal.oci.tar\n",
        "          push: true\n          tags: ghcr.io/example/rehearsal:latest\n",
        1,
    )
    weak_source = workflow.replace(
        '          --expected-rehearsal-commit "${GITHUB_SHA}"\n',
        '          --expected-rehearsal-commit "deadbeef"\n',
        1,
    )
    mutating_phase = workflow.replace(
        "          --phase rehearse\n",
        "          --phase prepare\n",
        1,
    )
    missing_attestation = workflow.replace("          sbom: true\n", "          sbom: false\n", 1)
    missing_oci_layout_check = workflow.replace(
        '          test -f "${RUNNER_TEMP}/djenis-ai-agent-rehearsal.oci/index.json"\n',
        "",
        1,
    )
    wrong_scan_target = workflow.replace(
        "          input: ${{ runner.temp }}/djenis-ai-agent-rehearsal.oci\n",
        "          input: ${{ runner.temp }}/djenis-ai-agent-rehearsal.oci.tar\n",
        1,
    )

    assert "rehearsal must build an offline OCI archive with SBOM and provenance" in (
        validate_workflow_text(publish_build)
    )
    assert "rehearsal source must bind expected_tag to local HEAD and current origin/master" in (
        validate_workflow_text(weak_source)
    )
    mutation_errors = validate_workflow_text(mutating_phase)
    assert (
        "rehearsal must render source-bound release evidence without a GitHub token"
        in mutation_errors
    )
    assert "rehearsal must not contain any external release mutation command" in mutation_errors
    assert "rehearsal must build an offline OCI archive with SBOM and provenance" in (
        validate_workflow_text(missing_attestation)
    )
    assert (
        "rehearsal must extract and validate the local OCI layout before scanning"
        in validate_workflow_text(missing_oci_layout_check)
    )
    assert "rehearsal Trivy scan must fail closed over the local OCI layout" in (
        validate_workflow_text(wrong_scan_target)
    )


def test_manual_dispatch_cannot_enter_any_publication_job() -> None:
    workflow = _docker_workflow()
    publish_gate = (
        "    if: github.event_name == 'push' && "
        "(github.ref == 'refs/heads/master' || startsWith(github.ref, 'refs/tags/v'))\n"
    )
    dispatch_can_publish = workflow.replace(
        publish_gate,
        "    if: github.ref == 'refs/heads/master' || startsWith(github.ref, 'refs/tags/v')\n",
    )
    tag_dispatch_can_publish = workflow.replace(
        "    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')\n",
        "    if: startsWith(github.ref, 'refs/tags/v')\n",
        1,
    )
    master_dispatch_can_publish = workflow.replace(
        "    if: github.event_name == 'push' && github.ref == 'refs/heads/master'\n",
        "    if: github.ref == 'refs/heads/master'\n",
        1,
    )

    assert dispatch_can_publish != workflow
    assert tag_dispatch_can_publish != workflow
    assert master_dispatch_can_publish != workflow
    assert "release-preflight must depend on verify and use the publish ref gate" in (
        validate_workflow_text(dispatch_can_publish)
    )
    assert "release preflight must resolve the exact isolated remote tag" in validate_workflow_text(
        tag_dispatch_can_publish
    )
    assert (
        "master image metadata must be runtime-validated as edge and sha only"
        in validate_workflow_text(master_dispatch_can_publish)
    )


def test_publication_runs_for_one_ref_are_serialized_without_cancellation() -> None:
    workflow = _docker_workflow()
    broken = workflow.replace("  cancel-in-progress: false\n", "  cancel-in-progress: true\n", 1)

    assert "publication runs for one ref must serialize without cancellation" in (
        validate_workflow_text(broken)
    )


def test_release_protocol_requires_preflight_draft_promotion_and_finalization() -> None:
    workflow = _docker_workflow()
    broken_preflight = workflow.replace(
        "        id: inspect-release-authorization\n", "        id: ignored\n", 1
    )
    broken_source = workflow.replace(
        "        id: authorize-new-source\n", "        id: ignored\n", 1
    )
    broken_draft = workflow.replace("        id: prepare-release\n", "        id: ignored\n", 1)
    broken_alias = workflow.replace(
        "        id: authorize-alias-mutation\n", "        id: ignored\n", 1
    )
    broken_release = workflow.replace("        id: finalize-release\n", "        id: ignored\n", 1)

    assert (
        "release-preflight job must contain exactly one step with id 'inspect-release-authorization'"
        in validate_workflow_text(broken_preflight)
    )
    assert "release-preflight job must contain exactly one step with id 'authorize-new-source'" in (
        validate_workflow_text(broken_source)
    )
    assert "authorize-release job must contain exactly one step with id 'prepare-release'" in (
        validate_workflow_text(broken_draft)
    )
    assert (
        "promote-release job must contain exactly one step with id 'authorize-alias-mutation'"
        in (validate_workflow_text(broken_alias))
    )
    assert "release job must contain exactly one step with id 'finalize-release'" in (
        validate_workflow_text(broken_release)
    )


def test_draft_is_created_only_after_candidate_provenance_is_verified() -> None:
    workflow = _docker_workflow()
    broken = workflow.replace(
        "    needs: [verify, release-preflight, candidate, attest]\n",
        "    needs: [verify, release-preflight, candidate]\n",
        1,
    )

    assert "authorize-release must wait for verified provenance and remain tag-only" in (
        validate_workflow_text(broken)
    )


def test_remote_tag_recheck_is_immediately_before_each_external_mutation() -> None:
    workflow = _docker_workflow()
    broken_draft = workflow.replace(
        "      - name: Create or verify exact draft Release authorization\n",
        "      - name: Unreviewed step between authorization and draft\n"
        "        run: echo unsafe-gap\n\n"
        "      - name: Create or verify exact draft Release authorization\n",
        1,
    )
    broken_alias = workflow.replace(
        "      - name: Promote aliases with immutable version preflight\n",
        "      - name: Unreviewed step between authorization and mutation\n"
        "        run: echo unsafe-gap\n\n"
        "      - name: Promote aliases with immutable version preflight\n",
        1,
    )
    broken_release = workflow.replace(
        "      - name: Finalize or verify exact asset-free Release\n",
        "      - name: Unreviewed step between authorization and Release\n"
        "        run: echo unsafe-gap\n\n"
        "      - name: Finalize or verify exact asset-free Release\n",
        1,
    )

    assert "exact signed remote tag must be verified immediately before draft authorization" in (
        validate_workflow_text(broken_draft)
    )
    assert (
        "tag origin and SSH signature must be rechecked immediately before first alias mutation"
        in (validate_workflow_text(broken_alias))
    )
    assert "authorized signed remote tag must be rechecked immediately before finalization" in (
        validate_workflow_text(broken_release)
    )


def test_every_release_mutation_requires_the_github_verified_ssh_tag_gate() -> None:
    workflow = _docker_workflow()
    broken_token = workflow.replace(
        "          GITHUB_TOKEN: ${{ github.token }}\n",
        "          GITHUB_TOKEN: untrusted\n",
        1,
    )
    soft_failure = workflow.replace(
        "        id: verify-signed-tag\n",
        "        id: verify-signed-tag\n        continue-on-error: ${{ true }}\n",
        1,
    )

    expected = "release preflight must require an annotated GitHub-verified SSH release tag"
    assert expected in validate_workflow_text(broken_token)
    assert expected in validate_workflow_text(soft_failure)


def test_release_mutations_cannot_bypass_failed_dependencies_with_an_if_override() -> None:
    workflow = _docker_workflow()
    draft_bypass = workflow.replace(
        "        id: prepare-release\n        shell: bash\n",
        "        id: prepare-release\n        if: always()\n        shell: bash\n",
        1,
    )
    final_bypass = workflow.replace(
        "        id: finalize-release\n        shell: bash\n",
        "        id: finalize-release\n        if: always()\n        shell: bash\n",
        1,
    )

    assert "draft authorization must be prepared only after verified provenance" in (
        validate_workflow_text(draft_bypass)
    )
    assert "Release must finalize the exact immutable, retrying, asset-free draft" in (
        validate_workflow_text(final_bypass)
    )


def test_initial_remote_tag_must_match_the_event_source_commit() -> None:
    workflow = _docker_workflow()
    broken = workflow.replace(
        '          --expected-tag-commit "${GITHUB_SHA}"\n',
        '          --expected-tag-commit "deadbeef"\n',
        1,
    )

    assert "release preflight must resolve the exact isolated remote tag" in (
        validate_workflow_text(broken)
    )


def test_alias_promotion_rechecks_the_durable_release_digest() -> None:
    workflow = _docker_workflow()
    broken = workflow.replace(
        "        id: recheck-release-authorization\n",
        "        id: ignored-release-authorization\n",
        1,
    )

    assert (
        "promote-release job must contain exactly one step with id "
        "'recheck-release-authorization'" in validate_workflow_text(broken)
    )


def test_release_tag_check_requires_full_history() -> None:
    workflow = _docker_workflow()
    broken = workflow.replace("          fetch-depth: 0\n", "          fetch-depth: 1\n", 1)

    errors = validate_workflow_text(broken)

    assert "verify checkout must fetch full history for tag dereferencing" in errors


def test_candidate_is_digest_only_and_never_promotes_an_alias() -> None:
    workflow = _docker_workflow()
    output = (
        "          outputs: type=image,name=${{ steps.image.outputs.name }},"
        "push-by-digest=true,name-canonical=true,push=true\n"
    )
    tagged_build = workflow.replace(
        output,
        "          push: true\n          tags: ${{ steps.meta.outputs.tags }}\n",
    )
    premature_promotion = workflow.replace(
        "      - name: Scan exact candidate digest\n",
        "      - name: Premature alias mutation\n"
        "        run: docker push example.invalid/image:stable\n\n"
        "      - name: Scan exact candidate digest\n",
    )

    assert "candidate image must be pushed by digest without a public alias" in (
        validate_workflow_text(tagged_build)
    )
    assert "candidate build must not publish Docker tags" in (validate_workflow_text(tagged_build))
    assert "candidate job must never mutate a public image alias" in (
        validate_workflow_text(premature_promotion)
    )


def test_ghcr_retry_window_must_cover_60_to_120_seconds() -> None:
    workflow = _docker_workflow()
    broken = workflow.replace(
        '          ATTESTATION_RETRY_DELAYS: "2 4 8 10 10 10 10 10 10 10 10"\n',
        '          ATTESTATION_RETRY_DELAYS: "2 4 8"\n',
        1,
    )
    assert broken != workflow

    errors = validate_workflow_text(broken)

    assert (
        "attest reused attestation retry delays must be nondecreasing and total 60-120 seconds"
        in errors
    )


def test_oidc_attestation_signs_digest_with_minimal_permissions() -> None:
    workflow = _docker_workflow()
    missing_permission = workflow.replace("      id-token: write\n", "", 1)
    wrong_subject = workflow.replace(
        "          subject-digest: ${{ needs.candidate.outputs.digest }}\n",
        "          subject-digest: ${{ needs.verify.outputs.version }}\n",
    )

    assert "attest must use exact least-privilege OIDC permissions" in (
        validate_workflow_text(missing_permission)
    )
    assert "attest must sign the scanned candidate digest with GitHub OIDC" in (
        validate_workflow_text(wrong_subject)
    )


def test_oidc_verification_binds_signature_to_source_and_signer_workflow() -> None:
    workflow = _docker_workflow()
    broken = workflow.replace(
        '--signer-workflow "${GITHUB_REPOSITORY}/.github/workflows/docker-publish.yml"',
        '--signer-workflow "untrusted/example/.github/workflows/release.yml"',
    )
    assert broken != workflow

    errors = validate_workflow_text(broken)

    assert (
        "attest Sigstore verification must bind digest, source, workflow, and OIDC identity"
        in errors
    )


def test_reused_digest_requires_identity_bound_attestation_before_signing() -> None:
    workflow = _docker_workflow()
    missing_preflight = workflow.replace(
        "        id: verify-reused-attestation\n", "        id: ignored\n", 1
    )
    wrong_condition = workflow.replace(
        "        if: needs.candidate.outputs.reused == 'true'\n",
        "        if: needs.candidate.outputs.reused != 'true'\n",
        1,
    )
    missing_binding = workflow.replace(
        '              --source-digest "${AUTHORIZED_COMMIT}" \\\n',
        "",
        1,
    )
    soft_failure = workflow.replace(
        "        shell: bash\n        env:\n          ATTESTATION_RETRY_DELAYS:",
        "        continue-on-error: true\n        shell: bash\n        env:\n          ATTESTATION_RETRY_DELAYS:",
        1,
    )
    signer_bypass = workflow.replace(
        "        if: needs.candidate.outputs.reused != 'true'\n",
        "        if: always()\n",
        1,
    )

    expected = "attest must verify identity-bound pre-existing provenance before reuse"
    assert "attest job must contain exactly one step with id 'verify-reused-attestation'" in (
        validate_workflow_text(missing_preflight)
    )
    assert expected in validate_workflow_text(wrong_condition)
    assert expected in validate_workflow_text(missing_binding)
    assert expected in validate_workflow_text(soft_failure)
    assert "attest signing must not bypass trusted reuse provenance verification" in (
        validate_workflow_text(signer_bypass)
    )


@pytest.mark.parametrize(
    ("trusted", "untrusted"),
    [
        ('image_uri="oci://${PUBLISHED_IMAGE}@${PUBLISHED_DIGEST}"', 'image_uri="tag:latest"'),
        ('--repo "${GITHUB_REPOSITORY}"', '--repo "untrusted/example"'),
        (
            '--signer-workflow "${GITHUB_REPOSITORY}/.github/workflows/docker-publish.yml"',
            '--signer-workflow "untrusted/example/.github/workflows/release.yml"',
        ),
        ('--source-digest "${AUTHORIZED_COMMIT}"', '--source-digest "deadbeef"'),
        ('--source-ref "${GITHUB_REF}"', '--source-ref "refs/heads/untrusted"'),
        ("--bundle-from-oci", "--bundle-from-disk bundle.jsonl"),
    ],
)
def test_reused_attestation_preflight_rejects_each_weakened_binding(
    trusted: str, untrusted: str
) -> None:
    workflow = _docker_workflow()
    broken = workflow.replace(trusted, untrusted, 1)

    assert "attest must verify identity-bound pre-existing provenance before reuse" in (
        validate_workflow_text(broken)
    )


def test_reused_attestation_preflight_cannot_soft_fail_or_run_after_signing() -> None:
    workflow = _docker_workflow()
    soft_fail = workflow.replace(
        "              --deny-self-hosted-runners; then\n",
        "              --deny-self-hosted-runners || true; then\n",
        1,
    )
    marker = "        id: temporary-reuse-preflight\n"
    reordered = workflow.replace("        id: verify-reused-attestation\n", marker, 1)
    reordered = reordered.replace(
        "        id: github-attestation\n", "        id: verify-reused-attestation\n", 1
    )
    reordered = reordered.replace(marker, "        id: github-attestation\n", 1)

    assert "attest must verify identity-bound pre-existing provenance before reuse" in (
        validate_workflow_text(soft_fail)
    )
    assert "attest must verify reused provenance before any OIDC signing action" in (
        validate_workflow_text(reordered)
    )


def test_draft_recovery_digest_is_selected_without_rebuilding() -> None:
    workflow = _docker_workflow()
    broken_gate = workflow.replace(
        "          needs.release-preflight.outputs.state == 'none' ||\n"
        "          (needs.release-preflight.outputs.state == 'absent' &&\n"
        "          steps.release-state.outputs.exists != 'true')\n",
        "          steps.release-state.outputs.exists != 'true'\n",
        1,
    )
    broken_selection = workflow.replace(
        "          AUTHORIZED_DIGEST: ${{ needs.release-preflight.outputs.digest }}\n",
        "",
        1,
    )

    assert (
        "a rerun must reuse its draft digest or immutable alias instead of rebuilding"
        in validate_workflow_text(broken_gate)
    )
    assert "candidate selection must reuse the remote digest or select the build" in (
        validate_workflow_text(broken_selection)
    )


def test_published_release_rerun_cannot_rewrite_moving_aliases() -> None:
    workflow = _docker_workflow()
    broken = workflow.replace(
        "        if: steps.recheck-release-authorization.outputs.state == 'draft'\n",
        "        if: always()\n",
        1,
    )

    assert "published release reruns must not rewrite moving image aliases" in (
        validate_workflow_text(broken)
    )


def test_actionlint_is_pinned_checksummed_and_executed_by_ci() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert validate_ci_workflow_text(workflow) == []

    broken = workflow.replace(
        "        run: '\"${RUNNER_TEMP}/actionlint\"'\n",
        "        # run: actionlint\n        run: echo skipped\n",
    )
    assert broken != workflow

    errors = validate_ci_workflow_text(broken)

    assert "CI lint job must execute actionlint over all workflows" in errors


def test_local_only_dependency_contract_rejects_an_extra_core_sdk(tmp_path: Path) -> None:
    project_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    docker_text = (PROJECT_ROOT / "requirements-docker.txt").read_text(encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(project_text, encoding="utf-8")
    (tmp_path / "requirements-docker.txt").write_text(docker_text, encoding="utf-8")
    assert validate_local_only_dependency_contract(tmp_path) == []

    (tmp_path / "pyproject.toml").write_text(
        project_text.replace(
            "dependencies = [",
            'dependencies = [\n    "hosted-model-sdk>=1.0.0",',
            1,
        ),
        encoding="utf-8",
    )

    errors = validate_local_only_dependency_contract(tmp_path)

    assert "pyproject.toml must use the exact audited local-only core dependency set" in errors


@pytest.mark.parametrize(
    ("trusted", "untrusted"),
    [
        (
            "DJENIS_LOCAL_LLM_ENDPOINT=http://ollama:11434",
            "DJENIS_LOCAL_LLM_ENDPOINT=http://model.example:11434",
        ),
        ("DJENIS_LOCAL_LLM_CONTEXT_TOKENS=65536", "DJENIS_LOCAL_LLM_CONTEXT_TOKENS=32768"),
        ('"qwen3vl.context_length": 262144', '"qwen3vl.context_length": 32768'),
        ("http://localhost:8000/ready", "http://localhost:8000/not-ready"),
    ],
)
def test_local_runtime_smoke_cannot_lose_preflight_contract(trusted: str, untrusted: str) -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    broken = workflow.replace(trusted, untrusted, 1)
    assert broken != workflow

    errors = validate_ci_workflow_text(broken)

    assert "CI Docker smoke must exercise fail-closed local-model preflight and readiness" in errors


def test_ci_rejects_reintroduced_provider_credentials() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    broken = workflow + "\n# PROVIDER_API_KEY=forbidden\n"

    errors = validate_ci_workflow_text(broken)

    assert "CI local-model smoke must not configure a provider credential" in errors


@pytest.mark.parametrize(
    ("trusted", "untrusted"),
    [
        ("            --cov=src \\\n", "            --cov=tests \\\n"),
        (
            "          uv run --frozen --no-sync coverage report > coverage-summary.txt\n",
            "          echo coverage-skipped > coverage-summary.txt\n",
        ),
    ],
)
def test_local_coverage_gate_cannot_silently_lose_controls(trusted: str, untrusted: str) -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    broken = workflow.replace(trusted, untrusted, 1)
    assert broken != workflow

    errors = validate_ci_workflow_text(broken)

    assert "CI must retain its authoritative fail-closed local coverage gate" in errors


def test_ci_rejects_unconfigured_external_coverage_publication() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    external_upload = workflow.replace(
        "\n  docker-build:\n",
        "\n      - name: Unconfigured external upload\n"
        "        uses: codecov/codecov-action@"
        "fb8b3582c8e4def4969c97caa2f19720cb33a72f\n\n"
        "  docker-build:\n",
        1,
    )
    secret_backed = workflow.replace(
        "\n  docker-build:\n",
        "\n      - name: Secret-backed external upload\n"
        "        run: echo external-upload-disabled\n"
        "        env:\n"
        "          CODECOV_TOKEN: placeholder\n\n"
        "  docker-build:\n",
        1,
    )
    unneeded_oidc = workflow.replace(
        "  windows-coverage:\n"
        "    name: Windows Coverage Gate\n"
        "    runs-on: windows-latest\n"
        "    permissions:\n"
        "      contents: read\n",
        "  windows-coverage:\n"
        "    name: Windows Coverage Gate\n"
        "    runs-on: windows-latest\n"
        "    permissions:\n"
        "      contents: read\n"
        "      id-token: write\n",
        1,
    )

    expected = "must not claim external coverage publication before the repository is configured"
    assert expected in " ".join(validate_ci_workflow_text(external_upload))
    assert expected in " ".join(validate_ci_workflow_text(secret_backed))
    assert "exact least-privilege local gate permissions" in " ".join(
        validate_ci_workflow_text(unneeded_oidc)
    )


def test_coverage_artifact_must_remain_complete_and_inspectable() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    incomplete = workflow.replace("            coverage.xml\n", "", 1)
    assert incomplete != workflow

    assert "complete inspectable local coverage artifacts" in " ".join(
        validate_ci_workflow_text(incomplete)
    )


def test_all_repository_actions_are_full_sha_pinned() -> None:
    assert validate_repository_workflows(PROJECT_ROOT) == []


def test_pages_release_contract_retains_the_hidden_security_inventory() -> None:
    workflow = PAGES_WORKFLOW.read_text(encoding="utf-8")
    assert validate_pages_workflow_text(workflow) == []

    broken = workflow.replace(
        "          include-hidden-files: true\n",
        "          include-hidden-files: false\n",
        1,
    )
    assert broken != workflow

    errors = validate_pages_workflow_text(broken)

    assert "Pages artifact must upload the complete site inventory, including .well-known" in errors


@pytest.mark.parametrize(
    "unpinned_action",
    ("actions/checkout@main", "softprops/action-gh-release@v3"),
)
def test_repository_workflow_validator_rejects_symbolic_action_refs(
    tmp_path: Path, unpinned_action: str
) -> None:
    workflow_root = _copy_workflows(tmp_path)
    workflow_path = workflow_root / "ci.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    broken, replacements = re.subn(
        r"actions/checkout@[0-9a-f]{40}",
        unpinned_action,
        workflow,
        count=1,
    )
    assert replacements == 1
    workflow_path.write_text(broken, encoding="utf-8")

    errors = validate_repository_workflows(tmp_path)

    assert any("action must be pinned to a full commit SHA" in error for error in errors)


def test_repository_workflow_validator_rejects_extra_id_token_permission(
    tmp_path: Path,
) -> None:
    workflow_root = _copy_workflows(tmp_path)
    workflow_path = workflow_root / "docker-publish.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    broken = workflow.replace(
        "    permissions:\n      contents: read\n      packages: write\n",
        "    permissions:\n      contents: read\n      id-token: write\n      packages: write\n",
        1,
    )
    workflow_path.write_text(broken, encoding="utf-8")

    errors = validate_repository_workflows(tmp_path)

    assert any("candidate permissions must be exactly" in error for error in errors)


def test_checked_in_ruleset_makes_existing_v_tags_immutable() -> None:
    ruleset = TAG_RULESET.read_text(encoding="utf-8")
    assert validate_tag_ruleset_text(ruleset) == []

    bypassed = ruleset.replace('"bypass_actors": []', '"bypass_actors": [{"actor_id": 5}]')
    update_allowed = ruleset.replace(
        '"update_allows_fetch_and_merge": false',
        '"update_allows_fetch_and_merge": true',
    )

    assert "release tag ruleset must not declare bypass actors" in (
        validate_tag_ruleset_text(bypassed)
    )
    assert "release tag update rule must be fail-closed" in (
        validate_tag_ruleset_text(update_allowed)
    )


def test_tag_origin_dereferences_tag_and_compares_exact_origin_master() -> None:
    commit = "a" * 40
    calls: list[tuple[str, ...]] = []
    remote_tag_ref = "refs/djenis-release-verification/tags/v0.2.1"
    remote_master_ref = "refs/djenis-release-verification/heads/master"

    def run_git(arguments: tuple[str, ...]) -> str:
        calls.append(arguments)
        if arguments == ("rev-parse", f"{remote_tag_ref}^{{commit}}"):
            return commit
        if arguments == ("rev-parse", f"{remote_master_ref}^{{commit}}"):
            return commit
        return ""

    origin = verify_release_tag_origin(PROJECT_ROOT, "v0.2.1", git_runner=run_git)

    assert origin.tag_commit == commit
    assert origin.master_commit == commit
    assert calls[0] == (
        "fetch",
        "--atomic",
        "--force",
        "--no-tags",
        "--no-write-fetch-head",
        "origin",
        f"+refs/tags/v0.2.1:{remote_tag_ref}",
        f"+refs/heads/master:{remote_master_ref}",
    )


def test_tag_origin_fails_closed_when_master_differs_or_cannot_resolve() -> None:
    tag_commit = "a" * 40
    master_commit = "b" * 40
    remote_tag_ref = "refs/djenis-release-verification/tags/v0.2.1"
    remote_master_ref = "refs/djenis-release-verification/heads/master"

    def mismatched(arguments: tuple[str, ...]) -> str:
        if arguments == ("rev-parse", f"{remote_tag_ref}^{{commit}}"):
            return tag_commit
        if arguments == ("rev-parse", f"{remote_master_ref}^{{commit}}"):
            return master_commit
        return ""

    with pytest.raises(ReleaseContractError, match="must equal origin/master exactly"):
        verify_release_tag_origin(PROJECT_ROOT, "v0.2.1", git_runner=mismatched)

    with pytest.raises(ReleaseContractError, match="could not dereference release tag"):
        verify_release_tag_origin(PROJECT_ROOT, "v0.2.1", git_runner=lambda _arguments: "")


def test_remote_tag_rebind_fetches_only_exact_tag_into_isolated_ref() -> None:
    commit = "a" * 40
    calls: list[tuple[str, ...]] = []
    remote_tag_ref = "refs/djenis-release-verification/tags/v0.2.1"

    def run_git(arguments: tuple[str, ...]) -> str:
        calls.append(arguments)
        if arguments == ("rev-parse", f"{remote_tag_ref}^{{commit}}"):
            return commit
        return ""

    assert (
        verify_remote_release_tag(
            PROJECT_ROOT,
            "v0.2.1",
            expected_commit=commit,
            git_runner=run_git,
        )
        == commit
    )
    assert calls[0] == (
        "fetch",
        "--force",
        "--no-tags",
        "--no-write-fetch-head",
        "origin",
        f"+refs/tags/v0.2.1:{remote_tag_ref}",
    )
    assert all("refs/tags/v0.2.1^{commit}" not in call for call in calls)


def test_remote_tag_rebind_rejects_stale_local_or_changed_remote_state() -> None:
    remote_commit = "b" * 40
    remote_tag_ref = "refs/djenis-release-verification/tags/v0.2.1"

    def changed_remote(arguments: tuple[str, ...]) -> str:
        if arguments == ("rev-parse", f"{remote_tag_ref}^{{commit}}"):
            return remote_commit
        return ""

    with pytest.raises(ReleaseContractError, match="durable authorization commit"):
        verify_remote_release_tag(
            PROJECT_ROOT,
            "v0.2.1",
            expected_commit="a" * 40,
            git_runner=changed_remote,
        )

    def missing_remote(arguments: tuple[str, ...]) -> str:
        if arguments[0] == "fetch":
            raise ReleaseContractError("remote tag missing")
        if arguments == ("rev-parse", "refs/tags/v0.2.1^{commit}"):
            return "a" * 40
        return ""

    with pytest.raises(ReleaseContractError, match="remote tag missing"):
        verify_remote_release_tag(PROJECT_ROOT, "v0.2.1", git_runner=missing_remote)


def test_github_tag_gate_accepts_only_the_exact_annotated_verified_ssh_tag() -> None:
    commit = "a" * 40
    tag_object_sha = "b" * 40
    paths: list[str] = []

    def get_json(path: str) -> object:
        paths.append(path)
        if path.endswith("/git/ref/tags/v0.2.2"):
            return {
                "ref": "refs/tags/v0.2.2",
                "object": {"type": "tag", "sha": tag_object_sha},
            }
        return {
            "sha": tag_object_sha,
            "tag": "v0.2.2",
            "object": {"type": "commit", "sha": commit},
            "verification": {
                "verified": True,
                "reason": "valid",
                "signature": "-----BEGIN SSH SIGNATURE-----\nverified\n-----END SSH SIGNATURE-----",
            },
        }

    assert (
        verify_github_release_tag(
            repository="example/project",
            tag="v0.2.2",
            expected_commit=commit,
            get_json=get_json,
        )
        == tag_object_sha
    )
    assert paths == [
        "/repos/example/project/git/ref/tags/v0.2.2",
        f"/repos/example/project/git/tags/{tag_object_sha}",
    ]


@pytest.mark.parametrize(
    ("ref_type", "verified", "reason", "signature", "target", "message"),
    [
        ("commit", True, "valid", "-----BEGIN SSH SIGNATURE-----", "a" * 40, "annotated"),
        ("tag", False, "unsigned", None, "a" * 40, "report.*valid"),
        ("tag", True, "valid", "-----BEGIN PGP SIGNATURE-----", "a" * 40, "SSH signature"),
        ("tag", True, "valid", "-----BEGIN SSH SIGNATURE-----", "c" * 40, "authorized"),
    ],
)
def test_github_tag_gate_rejects_untrusted_tag_state(
    ref_type: str,
    verified: bool,
    reason: str,
    signature: str | None,
    target: str,
    message: str,
) -> None:
    tag_object_sha = "b" * 40

    def get_json(path: str) -> object:
        if "/git/ref/" in path:
            return {
                "ref": "refs/tags/v0.2.2",
                "object": {"type": ref_type, "sha": tag_object_sha},
            }
        return {
            "sha": tag_object_sha,
            "tag": "v0.2.2",
            "object": {"type": "commit", "sha": target},
            "verification": {
                "verified": verified,
                "reason": reason,
                "signature": signature,
            },
        }

    with pytest.raises(GitHubTagVerificationError, match=message):
        verify_github_release_tag(
            repository="example/project",
            tag="v0.2.2",
            expected_commit="a" * 40,
            get_json=get_json,
        )


def test_release_documentation_rejects_a_v_prefixed_image_tag(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "docker pull ghcr.io/example/djenis-ai-agent:v0.2.1\nSee .github/rulesets/README.md",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("## 0.2.1 - 2026-07-20", encoding="utf-8")

    errors = validate_release_documentation(tmp_path, "0.2.1")

    assert "README.md must not use the v-prefixed Git tag as an image tag" in errors


@pytest.mark.parametrize(
    "removed_token",
    [
        "expected_tag=v0.3.0",
        "non-mutating rehearsal",
        "origin/master",
        "offline OCI archive with SBOM and provenance",
    ],
)
def test_release_documentation_requires_exact_rehearsal_instructions(
    tmp_path: Path, removed_token: str
) -> None:
    for relative_path in (
        Path("README.md"),
        Path("CHANGELOG.md"),
        Path(".github/rulesets/README.md"),
        Path("docs/releases/v0.3.0.md"),
        Path("scripts/publish_github_release.py"),
    ):
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, destination)

    ruleset_readme = tmp_path / ".github" / "rulesets" / "README.md"
    original = ruleset_readme.read_text(encoding="utf-8")
    broken = original.replace(removed_token, "removed-rehearsal-token")
    assert broken != original
    ruleset_readme.write_text(broken, encoding="utf-8")

    errors = validate_release_documentation(tmp_path, "0.3.0")

    assert "release-tag instructions must require the exact non-mutating rehearsal" in errors


@pytest.mark.parametrize(
    "removed_token",
    [
        "mkdir -p djenis-ai-agent-release/deploy",
        "{target_commit}/deploy/nginx.conf",
        "--output deploy/nginx.conf",
    ],
)
def test_release_documentation_rejects_each_missing_gateway_handoff_token(
    tmp_path: Path, removed_token: str
) -> None:
    (tmp_path / "README.md").write_text(
        "docker pull ghcr.io/example/djenis-ai-agent:0.2.1\nSee .github/rulesets/README.md",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("## 0.2.1 - 2026-07-20", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    helper = "\n".join(
        (
            "mkdir -p djenis-ai-agent-release/deploy",
            "{target_commit}/deploy/nginx.conf",
            "--output deploy/nginx.conf",
            "CLI startup and web readiness fail closed",
            "`/health` endpoint remains a process-liveness probe",
        )
    )
    (scripts / "publish_github_release.py").write_text(
        helper.replace(removed_token, "removed-gateway-token", 1),
        encoding="utf-8",
    )

    errors = validate_release_documentation(tmp_path, "0.2.1")

    assert "release notes must fetch the gateway asset from the exact authorized commit" in errors


def test_release_documentation_distinguishes_readiness_from_liveness(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "docker pull ghcr.io/example/djenis-ai-agent:0.2.1\nSee .github/rulesets/README.md",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("## 0.2.1 - 2026-07-20", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "publish_github_release.py").write_text(
        "\n".join(
            (
                "mkdir -p djenis-ai-agent-release/deploy",
                "{target_commit}/deploy/nginx.conf",
                "--output deploy/nginx.conf",
                "startup uses /health for readiness",
            )
        ),
        encoding="utf-8",
    )

    errors = validate_release_documentation(tmp_path, "0.2.1")

    assert "release notes must distinguish readiness from web process liveness" in errors


def test_release_documentation_requires_gateway_asset_from_authorized_commit(
    tmp_path: Path,
) -> None:
    shutil.copy2(PROJECT_ROOT / "README.md", tmp_path / "README.md")
    shutil.copy2(PROJECT_ROOT / "CHANGELOG.md", tmp_path / "CHANGELOG.md")
    scripts_root = tmp_path / "scripts"
    scripts_root.mkdir()
    release_helper = (PROJECT_ROOT / "scripts" / "publish_github_release.py").read_text(
        encoding="utf-8"
    )
    broken = release_helper.replace(
        "{target_commit}/deploy/nginx.conf",
        "{target_commit}/deploy/missing.conf",
        1,
    )
    assert broken != release_helper
    (scripts_root / "publish_github_release.py").write_text(broken, encoding="utf-8")

    errors = validate_release_documentation(tmp_path, "0.2.2")

    assert "release notes must fetch the gateway asset from the exact authorized commit" in errors


def test_release_validator_detects_a_stale_runtime_version(tmp_path: Path) -> None:
    for relative_path in (
        Path("pyproject.toml"),
        Path("uv.lock"),
        Path("src/config.py"),
        Path("README.md"),
        Path("CHANGELOG.md"),
        Path(".github/workflows/docker-publish.yml"),
        Path(".github/workflows/ci.yml"),
        Path(".github/rulesets/immutable-v-tags.json"),
    ):
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, destination)

    config_path = tmp_path / "src" / "config.py"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            'VERSION: str = "0.3.0"',
            'VERSION: str = "0.2.0"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseContractError, match="version sources disagree"):
        validate_release_contract(tmp_path, tag="v0.3.0")


def test_pull_request_template_requires_concrete_review_context() -> None:
    template = (PROJECT_ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")

    for heading in (
        "## Result",
        "## Why",
        "## Validation",
        "## Permissions and security boundaries",
        "## Release and versioning",
    ):
        assert heading in template
    assert "- [ ]" not in template
