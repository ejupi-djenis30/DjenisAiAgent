"""Regression tests for the release version, workflow, and container contract."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from scripts.validate_release import (
    ReleaseContractError,
    image_tags_for_version,
    master_image_tags_for_commit,
    validate_ci_workflow_text,
    validate_image_metadata,
    validate_release_contract,
    validate_release_documentation,
    validate_repository_workflows,
    validate_tag_ruleset_text,
    validate_workflow_text,
    verify_release_tag_origin,
    verify_remote_release_tag,
)
from scripts.verify_github_tag import GitHubTagVerificationError, verify_github_release_tag

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCKER_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "docker-publish.yml"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
TAG_RULESET = PROJECT_ROOT / ".github" / "rulesets" / "immutable-v-tags.json"
IMAGE_NAME = "ghcr.io/ejupi-djenis30/djenis-ai-agent"


def _docker_workflow() -> str:
    return DOCKER_WORKFLOW.read_text(encoding="utf-8")


def _copy_workflows(destination: Path) -> Path:
    workflow_root = destination / ".github" / "workflows"
    shutil.copytree(PROJECT_ROOT / ".github" / "workflows", workflow_root)
    return workflow_root


def test_repository_contract_matches_v0_2_2_and_release_image_aliases() -> None:
    expected_tags = ("0.2.2", "0.2", "0", "latest")
    metadata_tags = "\n".join(f"{IMAGE_NAME}:{tag}" for tag in expected_tags)

    contract = validate_release_contract(
        PROJECT_ROOT,
        tag="v0.2.2",
        image_name=IMAGE_NAME,
        image_tags=metadata_tags,
    )

    assert contract.version == "0.2.2"
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

    assert contract.version == "0.2.2"


def test_git_tag_must_match_the_project_version_exactly() -> None:
    with pytest.raises(ReleaseContractError, match=r"Git tag must be v0\.2\.2"):
        validate_release_contract(PROJECT_ROOT, tag="v0.2.0")


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


def test_master_and_release_image_aliases_are_strictly_separated() -> None:
    workflow = _docker_workflow()

    assert "type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/v') }}" in workflow
    assert "type=raw,value=edge,enable=${{ github.ref == 'refs/heads/master' }}" in workflow
    assert (
        "type=sha,prefix=sha-,format=short,enable=${{ github.ref == 'refs/heads/master' }}"
        in workflow
    )
    assert "id: validate-master-image-tags" in workflow
    assert '--master-commit "${GITHUB_SHA}"' in workflow

    broken = workflow.replace(
        "type=raw,value=edge,enable=${{ github.ref == 'refs/heads/master' }}",
        "type=raw,value=latest,enable=${{ github.ref == 'refs/heads/master' }}",
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


def test_manual_dispatch_on_an_arbitrary_branch_is_structurally_verify_only() -> None:
    workflow = _docker_workflow()
    gate = "    if: github.ref == 'refs/heads/master' || startsWith(github.ref, 'refs/tags/v')\n"
    broken = workflow.replace(
        gate,
        "    if: startsWith(github.ref, 'refs/tags/v')\n"
        "    # github.ref == 'refs/heads/master' || startsWith(github.ref, 'refs/tags/v')\n",
    )
    assert broken != workflow

    errors = validate_workflow_text(broken)

    assert "release-preflight must depend on verify and use the publish ref gate" in errors
    assert (
        "candidate job must be gated to master or v-prefixed tags so manual runs on arbitrary branches remain verify-only"
        in errors
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


@pytest.mark.parametrize(
    ("trusted", "untrusted"),
    [
        ("          use_oidc: true\n", "          use_oidc: false\n"),
        ("          fail_ci_if_error: true\n", "          fail_ci_if_error: false\n"),
        ("          disable_search: true\n", "          disable_search: false\n"),
    ],
)
def test_codecov_upload_cannot_silently_lose_trust_controls(trusted: str, untrusted: str) -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    broken = workflow.replace(trusted, untrusted, 1)
    assert broken != workflow

    errors = validate_ci_workflow_text(broken)

    assert (
        "CI Codecov upload must use OIDC, one explicit report, and fail on upload errors" in errors
    )


def test_codecov_upload_rejects_secret_tokens_and_missing_oidc_permission() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    secret_backed = workflow.replace(
        "          use_oidc: true\n",
        "          token: ${{ secrets.CODECOV_TOKEN }}\n          use_oidc: true\n",
        1,
    )
    underprivileged = workflow.replace("      id-token: write\n", "", 1)

    assert "must use OIDC, one explicit report, and fail on upload errors" in " ".join(
        validate_ci_workflow_text(secret_backed)
    )
    assert "exact least-privilege Codecov OIDC permissions" in " ".join(
        validate_ci_workflow_text(underprivileged)
    )


def test_codecov_checkout_retains_the_required_history() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    shallow = workflow.replace("          fetch-depth: 2\n", "          fetch-depth: 1\n", 1)
    assert shallow != workflow

    assert "retain enough history without persisted credentials" in " ".join(
        validate_ci_workflow_text(shallow)
    )


def test_all_repository_actions_are_full_sha_pinned() -> None:
    assert validate_repository_workflows(PROJECT_ROOT) == []


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
    broken = workflow.replace(
        "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        unpinned_action,
        1,
    )
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
            'VERSION: str = "0.2.2"',
            'VERSION: str = "0.2.0"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseContractError, match="version sources disagree"):
        validate_release_contract(tmp_path, tag="v0.2.2")


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
