"""Tests for fail-closed GHCR alias state and promotion."""

from __future__ import annotations

import pytest
from scripts.release_registry import (
    AliasState,
    CommandResult,
    RegistryStateError,
    immutable_alias_decision,
    inspect_alias,
    promote_aliases,
    verify_alias,
)

IMAGE = "ghcr.io/ejupi-djenis30/djenis-ai-agent"
DIGEST = f"sha256:{'a' * 64}"
OTHER_DIGEST = f"sha256:{'b' * 64}"


def test_immutable_alias_is_created_only_when_confirmed_absent() -> None:
    assert immutable_alias_decision(AliasState(False, None), DIGEST) == "create"
    assert immutable_alias_decision(AliasState(True, DIGEST), DIGEST) == "reuse"


def test_immutable_alias_mismatch_fails_before_any_registry_mutation() -> None:
    calls: list[tuple[str, ...]] = []

    def run(arguments: tuple[str, ...]) -> CommandResult:
        calls.append(arguments)
        return CommandResult(0, f"{OTHER_DIGEST}\n")

    with pytest.raises(RegistryStateError, match="different digest"):
        promote_aliases(
            image=IMAGE,
            digest=DIGEST,
            aliases=(f"{IMAGE}:0.2.1", f"{IMAGE}:0.2", f"{IMAGE}:0"),
            immutable_alias=f"{IMAGE}:0.2.1",
            runner=run,
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )

    assert len(calls) == 1
    assert calls[0][0:4] == ("docker", "buildx", "imagetools", "inspect")


def test_rerun_reuses_version_alias_without_passing_it_to_imagetools_create() -> None:
    calls: list[tuple[str, ...]] = []

    def run(arguments: tuple[str, ...]) -> CommandResult:
        calls.append(arguments)
        if arguments[3] == "inspect":
            return CommandResult(0, f"{DIGEST}\n")
        return CommandResult(0)

    decision = promote_aliases(
        image=IMAGE,
        digest=DIGEST,
        aliases=(f"{IMAGE}:0.2.1", f"{IMAGE}:0.2", f"{IMAGE}:0"),
        immutable_alias=f"{IMAGE}:0.2.1",
        runner=run,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    create = next(call for call in calls if call[3] == "create")
    assert decision == "reuse"
    assert f"{IMAGE}:0.2.1" not in create
    assert f"{IMAGE}:0.2" in create
    assert f"{IMAGE}:0" in create


def test_transient_inspection_error_retries_then_fails_closed() -> None:
    responses = iter(
        (
            CommandResult(1, stderr="registry temporarily unavailable"),
            CommandResult(1, stderr="registry still unavailable"),
        )
    )
    sleeps: list[float] = []

    with pytest.raises(RegistryStateError, match="could not establish remote state"):
        inspect_alias(
            f"{IMAGE}:0.2.1",
            runner=lambda _arguments: next(responses),
            retry_delays=(60,),
            sleep=sleeps.append,
        )

    assert sleeps == [60.0]


def test_confirmed_manifest_absence_is_not_treated_as_a_transport_failure() -> None:
    state = inspect_alias(
        f"{IMAGE}:0.2.1",
        runner=lambda _arguments: CommandResult(1, stderr="manifest unknown"),
    )

    assert state == AliasState(False, None)


def test_unrelated_not_found_error_is_not_misclassified_as_manifest_absence() -> None:
    with pytest.raises(RegistryStateError, match="could not establish remote state"):
        inspect_alias(
            f"{IMAGE}:0.2.1",
            runner=lambda _arguments: CommandResult(
                1,
                stderr='credential helper "docker-credential-desktop" not found',
            ),
        )


def test_published_release_rerun_verifies_immutable_alias_without_mutation() -> None:
    calls: list[tuple[str, ...]] = []

    def run(arguments: tuple[str, ...]) -> CommandResult:
        calls.append(arguments)
        return CommandResult(0, f"{DIGEST}\n")

    verify_alias(
        f"{IMAGE}:0.2.1",
        DIGEST,
        runner=run,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    assert len(calls) == 1
    assert calls[0][3] == "inspect"


def test_published_release_rerun_rejects_immutable_alias_mismatch() -> None:
    with pytest.raises(RegistryStateError, match="authorized digest"):
        verify_alias(
            f"{IMAGE}:0.2.1",
            DIGEST,
            runner=lambda _arguments: CommandResult(0, f"{OTHER_DIGEST}\n"),
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )
