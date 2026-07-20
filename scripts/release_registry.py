"""Inspect and promote GHCR aliases without rewriting immutable release tags."""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE_PATTERN = re.compile(r"ghcr\.io/[a-z0-9][a-z0-9._/-]*[a-z0-9]")
NOT_FOUND_MARKERS = (
    "manifest unknown",
    "name unknown",
    "no such manifest",
)
COMMAND_TIMEOUT_SECONDS = 120


class RegistryStateError(RuntimeError):
    """Raised when registry state cannot be established safely."""


@dataclass(frozen=True)
class CommandResult:
    """The observable result of one Docker command."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class AliasState:
    """A confirmed remote alias state."""

    exists: bool
    digest: str | None


CommandRunner = Callable[[tuple[str, ...]], CommandResult]
Sleep = Callable[[float], None]


def _run_command(arguments: tuple[str, ...]) -> CommandResult:
    try:
        completed = subprocess.run(  # nosec B603
            arguments,
            check=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RegistryStateError(f"Docker command could not complete safely: {exc}") from exc
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _is_confirmed_missing(image_ref: str, detail: str) -> bool:
    normalized = detail.lower()
    return any(marker in normalized for marker in NOT_FOUND_MARKERS) or (
        f"{image_ref.lower()}: not found" in normalized
    )


def parse_retry_delays(raw: str) -> tuple[int, ...]:
    """Parse a bounded, nondecreasing retry schedule."""

    try:
        delays = tuple(int(value) for value in raw.split())
    except ValueError as exc:
        raise RegistryStateError("retry delays must contain only integers") from exc
    if (
        not delays
        or any(delay <= 0 for delay in delays)
        or tuple(sorted(delays)) != delays
        or not 60 <= sum(delays) <= 120
    ):
        raise RegistryStateError(
            "retry delays must be positive, nondecreasing, and total 60-120 seconds"
        )
    return delays


def validate_image(image: str) -> str:
    """Accept only a normalized GHCR repository name."""

    if IMAGE_PATTERN.fullmatch(image) is None or image != image.lower():
        raise RegistryStateError(f"invalid normalized GHCR image name: {image!r}")
    return image


def validate_digest(digest: str) -> str:
    """Accept only a canonical SHA-256 OCI digest."""

    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise RegistryStateError(f"invalid OCI digest: {digest!r}")
    return digest


def inspect_alias(
    image_ref: str,
    *,
    runner: CommandRunner = _run_command,
    retry_delays: Sequence[int] = (),
    retry_missing: bool = False,
    sleep: Sleep = time.sleep,
) -> AliasState:
    """Resolve an alias, distinguishing confirmed absence from transient failure."""

    attempts = len(retry_delays) + 1
    last_error = ""
    for attempt in range(attempts):
        result = runner(
            (
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                image_ref,
                "--format",
                "{{ .Manifest.Digest }}",
            )
        )
        if result.returncode == 0:
            digest = result.stdout.strip()
            return AliasState(True, validate_digest(digest))

        last_error = " ".join((result.stdout, result.stderr)).strip()
        missing = _is_confirmed_missing(image_ref, last_error)
        if missing and not retry_missing:
            return AliasState(False, None)
        if attempt < len(retry_delays):
            sleep(float(retry_delays[attempt]))
            continue
        if missing:
            return AliasState(False, None)
        break

    detail = last_error or "Docker returned no diagnostic"
    raise RegistryStateError(f"could not establish remote state for {image_ref}: {detail}")


def immutable_alias_decision(existing: AliasState, candidate_digest: str) -> str:
    """Return create/reuse, or reject an immutable alias bound elsewhere."""

    candidate = validate_digest(candidate_digest)
    if not existing.exists:
        return "create"
    if existing.digest == candidate:
        return "reuse"
    raise RegistryStateError(
        "immutable release alias already resolves to a different digest: "
        f"remote={existing.digest}, candidate={candidate}"
    )


def verify_alias(
    image_ref: str,
    digest: str,
    *,
    runner: CommandRunner = _run_command,
    retry_delays: Sequence[int] = (),
    sleep: Sleep = time.sleep,
) -> None:
    """Require one existing alias to resolve to the exact authorized digest."""

    expected = validate_digest(digest)
    state = inspect_alias(
        image_ref,
        runner=runner,
        retry_delays=retry_delays,
        retry_missing=True,
        sleep=sleep,
    )
    if not state.exists or state.digest != expected:
        raise RegistryStateError(
            f"{image_ref} does not resolve to the authorized digest {expected}"
        )


def _validated_aliases(image: str, aliases: Sequence[str]) -> tuple[str, ...]:
    expected_prefix = f"{image}:"
    normalized = tuple(alias.strip() for alias in aliases if alias.strip())
    if not normalized:
        raise RegistryStateError("promotion requires at least one alias")
    if len(set(normalized)) != len(normalized):
        raise RegistryStateError("promotion aliases must be unique")
    for alias in normalized:
        if not alias.startswith(expected_prefix) or alias == expected_prefix:
            raise RegistryStateError(f"refusing unexpected image alias: {alias}")
    return normalized


def promote_aliases(
    *,
    image: str,
    digest: str,
    aliases: Sequence[str],
    immutable_alias: str | None = None,
    runner: CommandRunner = _run_command,
    retry_delays: Sequence[int] = (),
    sleep: Sleep = time.sleep,
) -> str:
    """Promote one verified digest while treating the release alias as immutable."""

    normalized_image = validate_image(image)
    normalized_digest = validate_digest(digest)
    normalized_aliases = _validated_aliases(normalized_image, aliases)
    aliases_to_write = list(normalized_aliases)
    decision = "not-applicable"

    if immutable_alias is not None:
        if immutable_alias not in normalized_aliases:
            raise RegistryStateError("immutable alias must be present in the promotion set")
        remote = inspect_alias(
            immutable_alias,
            runner=runner,
            retry_delays=retry_delays,
            sleep=sleep,
        )
        decision = immutable_alias_decision(remote, normalized_digest)
        if decision == "reuse":
            aliases_to_write.remove(immutable_alias)

    if aliases_to_write:
        command = ["docker", "buildx", "imagetools", "create"]
        for alias in aliases_to_write:
            command.extend(("--tag", alias))
        command.append(f"{normalized_image}@{normalized_digest}")
        result = runner(tuple(command))
        if result.returncode != 0:
            detail = " ".join((result.stdout, result.stderr)).strip()
            raise RegistryStateError(f"alias promotion failed: {detail or 'no diagnostic'}")

    for alias in normalized_aliases:
        state = inspect_alias(
            alias,
            runner=runner,
            retry_delays=retry_delays,
            retry_missing=True,
            sleep=sleep,
        )
        if not state.exists or state.digest != normalized_digest:
            raise RegistryStateError(
                f"{alias} does not resolve to the verified digest {normalized_digest}"
            )
    return decision


def _write_output(path: Path, *, exists: bool, digest: str | None) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(f"exists={'true' if exists else 'false'}\n")
        output.write(f"digest={digest or ''}\n")


def _parse_aliases(raw: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in raw.splitlines() if line.strip())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--alias", required=True)
    inspect_parser.add_argument("--github-output", required=True, type=Path)
    inspect_parser.add_argument("--retry-delays", default="2 4 8 10 10 10 10 10 10 10 10")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--alias", required=True)
    verify_parser.add_argument("--digest", required=True)
    verify_parser.add_argument("--retry-delays", default="2 4 8 10 10 10 10 10 10 10 10")

    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("--image", required=True)
    promote_parser.add_argument("--digest", required=True)
    promote_parser.add_argument("--aliases", required=True)
    promote_parser.add_argument("--immutable-alias")
    promote_parser.add_argument("--retry-delays", default="2 4 8 10 10 10 10 10 10 10 10")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        delays = parse_retry_delays(args.retry_delays)
        if args.command == "inspect":
            state = inspect_alias(args.alias, retry_delays=delays)
            _write_output(args.github_output, exists=state.exists, digest=state.digest)
            print(
                f"Immutable alias state: {'present at ' + str(state.digest) if state.exists else 'absent'}"
            )
            return 0

        if args.command == "verify":
            verify_alias(args.alias, args.digest, retry_delays=delays)
            print(f"Immutable alias verified at {args.digest}")
            return 0

        decision = promote_aliases(
            image=args.image,
            digest=args.digest,
            aliases=_parse_aliases(args.aliases),
            immutable_alias=args.immutable_alias,
            retry_delays=delays,
        )
        print(f"Aliases verified; immutable alias decision: {decision}")
        return 0
    except RegistryStateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
