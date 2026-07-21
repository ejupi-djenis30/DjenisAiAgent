"""Create or verify one exact, asset-free GitHub Release."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http.client import HTTPResponse, HTTPSConnection
from pathlib import Path
from typing import Literal, cast
from urllib.parse import quote, urlsplit

TAG_PATTERN = re.compile(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
DIGEST_PATTERN: re.Pattern[str] = re.compile(r"sha256:[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
RELEASE_PAGE_SIZE = 100
MAX_RELEASE_PAGES = 100
GHCR_IMAGE_PATTERN = re.compile(
    r"ghcr\.io/"
    r"[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*)+"
)


class ReleasePublishError(RuntimeError):
    """Raised when GitHub Release state is absent, ambiguous, or inconsistent."""


@dataclass(frozen=True)
class ApiResponse:
    """One GitHub API response."""

    status: int
    body: object
    retry_after: int | None = None


@dataclass(frozen=True)
class ReleaseState:
    """Exact durable authorization state observed on GitHub."""

    state: Literal["absent", "draft", "published"]
    release_id: int | None = None
    digest: str | None = None


Transport = Callable[[str, str, Mapping[str, object] | None], ApiResponse]
Sleep = Callable[[float], None]


def release_body(*, image: str, version: str, digest: str, target_commit: str) -> str:
    """Build deterministic release notes tied to one scanned OCI digest."""

    return f"""## Docker image

Pull the immutable release alias:

```bash
docker pull {image}:{version}
```

Authorized source commit: `{target_commit}`

## Browser-enabled stack (recommended)

Browser automation requires the repository's pinned Selenium service. Download the Compose definition from the exact authorized commit, then run it with the verified application digest:

```bash
mkdir -p djenis-ai-agent-release && cd djenis-ai-agent-release
curl --fail --silent --show-error --location \\
  https://raw.githubusercontent.com/ejupi-djenis30/DjenisAiAgent/{target_commit}/docker-compose.yml \\
  --output compose.yaml
export GEMINI_API_KEY="your-key"
export DJENIS_WEB_AUTH_TOKEN="$(openssl rand -hex 24)"
export DJENIS_AGENT_IMAGE="{image}@{digest}"
docker compose -f compose.yaml pull
docker compose -f compose.yaml up --no-build
```

Open `http://127.0.0.1:8008`. Compose publishes the console on loopback only and provides the pinned Chromium Selenium service used by the browser tools.

## Image-only control plane

Use this only when you need the authenticated web console without browser automation, Windows UI Automation, or host display capture:

```bash
export GEMINI_API_KEY="your-key"
export DJENIS_WEB_AUTH_TOKEN="$(openssl rand -hex 24)"
docker run --rm \\
  -p 127.0.0.1:8000:8000 \\
  -e GEMINI_API_KEY \\
  -e DJENIS_WEB_AUTH_TOKEN \\
  -e DJENIS_PERMISSION_TIER=observe \\
  {image}@{digest}
```

Trivy scanned the digest used above before alias promotion. Its SPDX SBOM and BuildKit SLSA provenance were checked, then GitHub OIDC provenance was signed and cryptographically verified before any public alias changed.
"""


def _release_digest(body: object) -> str:
    if not isinstance(body, str):
        raise ReleasePublishError("release body must be text")
    matches = DIGEST_PATTERN.findall(body)
    if len(matches) != 2 or matches[0] != matches[1]:
        raise ReleasePublishError("release body must contain one consistent OCI digest")
    return cast(str, matches[0])


def expected_release(
    *,
    tag: str,
    target_commit: str,
    image: str,
    version: str,
    digest: str,
    draft: bool = False,
) -> dict[str, object]:
    """Return the exact mutable fields accepted for this release."""

    if TAG_PATTERN.fullmatch(tag) is None or tag != f"v{version}":
        raise ReleasePublishError("release tag must exactly match v<project version>")
    if COMMIT_PATTERN.fullmatch(target_commit) is None:
        raise ReleasePublishError("release target must be an exact 40-character commit SHA")
    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise ReleasePublishError("release digest must be a canonical SHA-256 OCI digest")
    if GHCR_IMAGE_PATTERN.fullmatch(image) is None:
        raise ReleasePublishError("release image must be a normalized GHCR name")
    return {
        "tag_name": tag,
        "target_commitish": target_commit,
        "name": tag,
        "body": release_body(
            image=image,
            version=version,
            digest=digest,
            target_commit=target_commit,
        ),
        "draft": draft,
        "prerelease": False,
        "generate_release_notes": False,
        "make_latest": "false" if draft else "true",
    }


def _verify_release_payload(
    actual: Mapping[str, object],
    expected: Mapping[str, object],
    *,
    expected_immutable: bool | None,
) -> int:
    for field in ("tag_name", "name", "body", "draft", "prerelease"):
        if actual.get(field) != expected[field]:
            raise ReleasePublishError(
                f"existing release has unexpected {field}: {actual.get(field)!r}"
            )
    assets = actual.get("assets")
    if assets != []:
        raise ReleasePublishError("release asset inventory must be exactly empty")
    if expected_immutable is not None and actual.get("immutable") is not expected_immutable:
        raise ReleasePublishError(
            "release has unexpected immutable state: "
            f"expected={expected_immutable}, actual={actual.get('immutable')!r}"
        )
    release_id = actual.get("id")
    if not isinstance(release_id, int) or release_id <= 0:
        raise ReleasePublishError("release response is missing a valid numeric id")
    return release_id


def _object(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ReleasePublishError(f"{label} must be a JSON object")
    return value


def _array(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ReleasePublishError(f"{label} must be a JSON array")
    return value


def _response_message(response: ApiResponse) -> object:
    if isinstance(response.body, dict):
        return response.body.get("message", "no diagnostic")
    return "non-object response"


def _request_with_retry(
    transport: Transport,
    method: str,
    path: str,
    payload: Mapping[str, object] | None,
    *,
    retry_delays: Sequence[int],
    accepted: set[int],
    sleep: Sleep,
) -> ApiResponse:
    for attempt in range(len(retry_delays) + 1):
        response = transport(method, path, payload)
        if response.status in accepted:
            return response
        transient = response.status == 429 or 500 <= response.status <= 599
        if transient and attempt < len(retry_delays):
            delay = response.retry_after or retry_delays[attempt]
            sleep(float(delay))
            continue
        message = _response_message(response)
        raise ReleasePublishError(
            f"GitHub API {method} {path} returned {response.status}: {message}"
        )
    raise ReleasePublishError("unreachable retry state")


def _wait_for_release(
    transport: Transport,
    path: str,
    *,
    retry_delays: Sequence[int],
    sleep: Sleep,
) -> ApiResponse:
    """Poll through 404 and server lag after an ambiguous create result."""

    for attempt in range(len(retry_delays) + 1):
        response = transport("GET", path, None)
        if response.status == 200:
            return response
        transient = response.status in {404, 429} or 500 <= response.status <= 599
        if transient and attempt < len(retry_delays):
            sleep(float(response.retry_after or retry_delays[attempt]))
            continue
        message = _response_message(response)
        raise ReleasePublishError(
            f"GitHub API GET {path} remained unavailable ({response.status}): {message}"
        )
    raise ReleasePublishError("unreachable release visibility retry state")


def _wait_for_latest(
    transport: Transport,
    path: str,
    release_id: int,
    *,
    retry_delays: Sequence[int],
    sleep: Sleep,
) -> None:
    """Wait for the latest endpoint to converge to the explicitly latest release."""

    last_id: object = None
    for attempt in range(len(retry_delays) + 1):
        response = transport("GET", path, None)
        if response.status == 200:
            last_id = _object(response.body, label="latest Release response").get("id")
            if last_id == release_id:
                return
        elif response.status not in {404, 429} and not 500 <= response.status <= 599:
            message = _response_message(response)
            raise ReleasePublishError(
                f"GitHub API GET {path} returned {response.status}: {message}"
            )
        if attempt < len(retry_delays):
            sleep(float(response.retry_after or retry_delays[attempt]))
    raise ReleasePublishError(
        "release did not become the repository's explicit latest release; "
        f"expected id={release_id}, observed id={last_id!r}"
    )


def _wait_for_immutable_release(
    transport: Transport,
    path: str,
    expected: Mapping[str, object],
    *,
    retry_delays: Sequence[int],
    sleep: Sleep,
) -> int:
    """Wait until the exact published Release is reported immutable."""

    last_immutable: object = None
    for attempt in range(len(retry_delays) + 1):
        response = transport("GET", path, None)
        if response.status == 200:
            actual = _object(response.body, label="published Release response")
            release_id = _verify_release_payload(
                actual,
                expected,
                expected_immutable=None,
            )
            last_immutable = actual.get("immutable")
            if last_immutable is True:
                return release_id
            if last_immutable is not False:
                raise ReleasePublishError(
                    "published release response is missing a boolean immutable state"
                )
        elif response.status not in {404, 429} and not 500 <= response.status <= 599:
            message = _response_message(response)
            raise ReleasePublishError(
                f"GitHub API GET {path} returned {response.status}: {message}"
            )
        if attempt < len(retry_delays):
            sleep(float(response.retry_after or retry_delays[attempt]))
    raise ReleasePublishError(
        "published release did not become immutable within the bounded retry window; "
        f"observed immutable={last_immutable!r}"
    )


def _verify_remote_tag_target(
    transport: Transport,
    *,
    repository: str,
    tag: str,
    expected_commit: str,
    retry_delays: Sequence[int],
    sleep: Sleep,
) -> None:
    """Dereference the remote lightweight or annotated tag to one exact commit."""

    ref_path = f"/repos/{repository}/git/ref/tags/{quote(tag, safe='')}"
    response = _wait_for_release(
        transport,
        ref_path,
        retry_delays=retry_delays,
        sleep=sleep,
    )
    response_body = _object(response.body, label="Git tag ref response")
    git_object = _object(response_body.get("object"), label="Git tag ref object")
    seen: set[str] = set()
    for _depth in range(8):
        object_type = git_object.get("type")
        sha = git_object.get("sha")
        if not isinstance(sha, str) or COMMIT_PATTERN.fullmatch(sha) is None:
            raise ReleasePublishError("Git tag object is missing an exact commit SHA")
        if sha in seen:
            raise ReleasePublishError("Git tag object graph contains a cycle")
        seen.add(sha)
        if object_type == "commit":
            if sha != expected_commit:
                raise ReleasePublishError(
                    "remote release tag resolves to an unexpected commit: "
                    f"expected={expected_commit}, actual={sha}"
                )
            return
        if object_type != "tag":
            raise ReleasePublishError(
                f"Git tag resolves to unsupported object type {object_type!r}"
            )
        response = _request_with_retry(
            transport,
            "GET",
            f"/repos/{repository}/git/tags/{sha}",
            None,
            retry_delays=retry_delays,
            accepted={200},
            sleep=sleep,
        )
        response_body = _object(response.body, label="annotated Git tag response")
        git_object = _object(response_body.get("object"), label="annotated Git tag object")
    raise ReleasePublishError("annotated Git tag chain exceeds the eight-object safety limit")


def _validate_publication_context(
    *,
    repository: str,
    tag: str,
    target_commit: str,
    transport: Transport,
    retry_delays: Sequence[int],
    sleep: Sleep,
) -> tuple[str, str]:
    """Validate the repository name and bind the remote tag to one exact commit."""

    if REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise ReleasePublishError("repository must be in owner/name form")
    _verify_remote_tag_target(
        transport,
        repository=repository,
        tag=tag,
        expected_commit=target_commit,
        retry_delays=retry_delays,
        sleep=sleep,
    )
    base = f"/repos/{repository}/releases"
    return base, tag


def _find_release_by_tag(
    transport: Transport,
    *,
    base: str,
    tag: str,
    retry_delays: Sequence[int],
    sleep: Sleep,
) -> tuple[ApiResponse, bool]:
    """Find one visible draft or published Release without trusting tag lookup for drafts."""

    releases: list[Mapping[str, object]] = []
    matches: list[Mapping[str, object]] = []
    for page in range(1, MAX_RELEASE_PAGES + 1):
        page_path = f"{base}?per_page={RELEASE_PAGE_SIZE}&page={page}"
        response = _request_with_retry(
            transport,
            "GET",
            page_path,
            None,
            retry_delays=retry_delays,
            accepted={200},
            sleep=sleep,
        )
        inventory = _array(response.body, label="Release inventory")
        for index, item in enumerate(inventory):
            release = _object(item, label=f"Release inventory item {index}")
            releases.append(release)
            if release.get("tag_name") == tag:
                matches.append(release)
        if len(inventory) < RELEASE_PAGE_SIZE:
            break
    else:
        raise ReleasePublishError(
            f"Release inventory exceeded the bounded {MAX_RELEASE_PAGES}-page search"
        )

    if len(matches) > 1:
        raise ReleasePublishError(f"multiple Releases use the exact tag {tag!r}")
    current = matches[0] if matches else None
    expect_latest = _guard_release_sequence(releases, tag=tag, current=current)
    if not matches:
        return (
            ApiResponse(404, {"message": "Release not found in authenticated inventory"}),
            expect_latest,
        )
    return ApiResponse(200, current), expect_latest


def _wait_for_release_by_tag(
    transport: Transport,
    *,
    base: str,
    tag: str,
    retry_delays: Sequence[int],
    sleep: Sleep,
) -> tuple[ApiResponse, bool]:
    """Poll the authenticated inventory after an ambiguous create result."""

    for attempt in range(len(retry_delays) + 1):
        current, expect_latest = _find_release_by_tag(
            transport,
            base=base,
            tag=tag,
            retry_delays=retry_delays,
            sleep=sleep,
        )
        if current.status == 200:
            return current, expect_latest
        if attempt < len(retry_delays):
            sleep(float(retry_delays[attempt]))
    raise ReleasePublishError(f"Release {tag!r} remained absent from the authenticated inventory")


def _semver(tag: object) -> tuple[int, int, int] | None:
    if not isinstance(tag, str) or TAG_PATTERN.fullmatch(tag) is None:
        return None
    major, minor, patch = tag.removeprefix("v").split(".")
    return int(major), int(minor), int(patch)


def _guard_release_sequence(
    inventory: Sequence[Mapping[str, object]],
    *,
    tag: str,
    current: Mapping[str, object] | None,
) -> bool:
    """Prevent unfinished or out-of-order releases from rolling aliases backward."""

    current_is_published = current is not None and current.get("draft") is False
    target_version = _semver(tag)
    if target_version is None:
        raise ReleasePublishError("release tag must be canonical SemVer")

    other_drafts: list[str] = []
    newer_published: list[str] = []
    for release in inventory:
        release_tag = release.get("tag_name")
        version = _semver(release_tag)
        if version is None:
            continue
        draft = release.get("draft")
        if draft is not True and draft is not False:
            raise ReleasePublishError(
                f"canonical Release {release_tag!r} is missing a boolean draft state"
            )
        if draft is True and release_tag != tag:
            other_drafts.append(str(release_tag))
        elif draft is False and version > target_version:
            newer_published.append(str(release_tag))

    if not current_is_published and other_drafts:
        raise ReleasePublishError(
            "another canonical draft Release must be completed first: "
            + ", ".join(sorted(other_drafts))
        )
    if not current_is_published and newer_published:
        raise ReleasePublishError(
            f"release {tag} cannot continue after newer published Releases: "
            + ", ".join(sorted(newer_published))
        )
    return not newer_published


def _observe_release_state(
    current: ApiResponse,
    *,
    draft_expected: Mapping[str, object],
    published_expected: Mapping[str, object],
    digest: str,
    transport: Transport,
    release_base: str,
    expect_latest: bool,
    retry_delays: Sequence[int],
    sleep: Sleep,
) -> ReleaseState:
    if current.status == 404:
        return ReleaseState("absent")
    actual = _object(current.body, label="Release response")
    draft = actual.get("draft")
    if draft is True:
        release_id = _verify_release_payload(
            actual,
            draft_expected,
            expected_immutable=False,
        )
        return ReleaseState("draft", release_id, digest)
    if draft is False:
        release_id = _verify_release_payload(
            actual,
            published_expected,
            expected_immutable=None,
        )
        immutable = actual.get("immutable")
        if immutable is False:
            recovered_id = _wait_for_immutable_release(
                transport,
                f"{release_base}/{release_id}",
                published_expected,
                retry_delays=retry_delays,
                sleep=sleep,
            )
            if recovered_id != release_id:
                raise ReleasePublishError("immutable Release recovery returned a different id")
        elif immutable is not True:
            raise ReleasePublishError(
                "published release response is missing a boolean immutable state"
            )
        if expect_latest:
            _wait_for_latest(
                transport,
                f"{release_base}/latest",
                release_id,
                retry_delays=retry_delays,
                sleep=sleep,
            )
        return ReleaseState("published", release_id, digest)
    raise ReleasePublishError("release response is missing a boolean draft state")


def inspect_release_authorization(
    *,
    repository: str,
    tag: str,
    target_commit: str,
    image: str,
    version: str,
    transport: Transport,
    retry_delays: Sequence[int],
    sleep: Sleep = time.sleep,
) -> ReleaseState:
    """Inspect an absent, exact draft, or exact immutable published Release."""

    expected_release(
        tag=tag,
        target_commit=target_commit,
        image=image,
        version=version,
        digest=f"sha256:{'0' * 64}",
    )
    base, validated_tag = _validate_publication_context(
        repository=repository,
        tag=tag,
        target_commit=target_commit,
        transport=transport,
        retry_delays=retry_delays,
        sleep=sleep,
    )
    current, expect_latest = _find_release_by_tag(
        transport,
        base=base,
        tag=validated_tag,
        retry_delays=retry_delays,
        sleep=sleep,
    )
    if current.status == 404:
        return ReleaseState("absent")
    current_body = _object(current.body, label="Release response")
    digest = _release_digest(current_body.get("body"))
    published_expected = expected_release(
        tag=tag,
        target_commit=target_commit,
        image=image,
        version=version,
        digest=digest,
    )
    draft_expected = expected_release(
        tag=tag,
        target_commit=target_commit,
        image=image,
        version=version,
        digest=digest,
        draft=True,
    )
    return _observe_release_state(
        current,
        draft_expected=draft_expected,
        published_expected=published_expected,
        digest=_release_digest(published_expected.get("body")),
        transport=transport,
        release_base=base,
        expect_latest=expect_latest,
        retry_delays=retry_delays,
        sleep=sleep,
    )


def prepare_release_authorization(
    *,
    repository: str,
    draft_expected: Mapping[str, object],
    published_expected: Mapping[str, object],
    transport: Transport,
    retry_delays: Sequence[int],
    sleep: Sleep = time.sleep,
) -> ReleaseState:
    """Create or verify the exact draft that durably authorizes alias promotion."""

    tag = str(published_expected["tag_name"])
    target_commit = str(published_expected["target_commitish"])
    base, validated_tag = _validate_publication_context(
        repository=repository,
        tag=tag,
        target_commit=target_commit,
        transport=transport,
        retry_delays=retry_delays,
        sleep=sleep,
    )
    current, expect_latest = _find_release_by_tag(
        transport,
        base=base,
        tag=validated_tag,
        retry_delays=retry_delays,
        sleep=sleep,
    )

    if current.status == 404:
        created = _request_with_retry(
            transport,
            "POST",
            base,
            draft_expected,
            retry_delays=retry_delays,
            accepted={201, 422},
            sleep=sleep,
        )
        if created.status == 201:
            current = created
        else:
            current, expect_latest = _wait_for_release_by_tag(
                transport,
                base=base,
                tag=validated_tag,
                retry_delays=retry_delays,
                sleep=sleep,
            )

    return _observe_release_state(
        current,
        draft_expected=draft_expected,
        published_expected=published_expected,
        digest=_release_digest(published_expected.get("body")),
        transport=transport,
        release_base=base,
        expect_latest=expect_latest,
        retry_delays=retry_delays,
        sleep=sleep,
    )


def finalize_release(
    *,
    repository: str,
    draft_expected: Mapping[str, object],
    published_expected: Mapping[str, object],
    transport: Transport,
    retry_delays: Sequence[int],
    sleep: Sleep = time.sleep,
) -> ReleaseState:
    """Publish the exact authorized draft, then verify latest and immutability."""

    tag = str(published_expected["tag_name"])
    target_commit = str(published_expected["target_commitish"])
    base, validated_tag = _validate_publication_context(
        repository=repository,
        tag=tag,
        target_commit=target_commit,
        transport=transport,
        retry_delays=retry_delays,
        sleep=sleep,
    )
    current, expect_latest = _find_release_by_tag(
        transport,
        base=base,
        tag=validated_tag,
        retry_delays=retry_delays,
        sleep=sleep,
    )
    if current.status == 404:
        raise ReleasePublishError("durable draft Release authorization is missing")

    current_body = _object(current.body, label="Release response")
    if current_body.get("draft") is True:
        release_id = _verify_release_payload(
            current_body,
            draft_expected,
            expected_immutable=False,
        )
        finalization_payload = {
            field: published_expected[field]
            for field in (
                "tag_name",
                "target_commitish",
                "name",
                "body",
                "draft",
                "prerelease",
                "make_latest",
            )
        }
        current = _request_with_retry(
            transport,
            "PATCH",
            f"{base}/{release_id}",
            finalization_payload,
            retry_delays=retry_delays,
            accepted={200},
            sleep=sleep,
        )
        patched_body = _object(current.body, label="updated Release response")
        patched_id = _verify_release_payload(
            patched_body,
            published_expected,
            expected_immutable=None,
        )
        if patched_id != release_id:
            raise ReleasePublishError("Release update returned a different numeric id")
    elif current_body.get("draft") is False:
        release_id = _verify_release_payload(
            current_body,
            published_expected,
            expected_immutable=None,
        )
    else:
        raise ReleasePublishError("release response is missing a boolean draft state")

    release_id = _wait_for_immutable_release(
        transport,
        f"{base}/{release_id}",
        published_expected,
        retry_delays=retry_delays,
        sleep=sleep,
    )
    if expect_latest:
        _wait_for_latest(
            transport,
            f"{base}/latest",
            release_id,
            retry_delays=retry_delays,
            sleep=sleep,
        )
    digest = _release_digest(published_expected.get("body"))
    return ReleaseState("published", release_id, digest)


class GitHubTransport:
    """Small HTTPS-only GitHub REST transport that never logs its token."""

    def __init__(self, *, api_url: str, token: str, timeout: int = 30) -> None:
        parsed = urlsplit(api_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
            raise ReleasePublishError("GitHub API URL must be an HTTPS origin")
        self._host = parsed.hostname
        self._port = parsed.port
        self._prefix = parsed.path.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._context = ssl.create_default_context()

    def __call__(self, method: str, path: str, payload: Mapping[str, object] | None) -> ApiResponse:
        connection = HTTPSConnection(
            self._host,
            self._port,
            timeout=self._timeout,
            context=self._context,
        )
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "djenis-ai-agent-release/1",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, f"{self._prefix}{path}", body=body, headers=headers)
            response: HTTPResponse = connection.getresponse()
            raw = response.read()
            status = response.status
            retry_header = response.getheader("Retry-After")
        finally:
            connection.close()
        try:
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReleasePublishError("GitHub API returned non-JSON content") from exc
        if not isinstance(decoded, dict | list):
            raise ReleasePublishError("GitHub API returned a non-object/non-array JSON document")
        retry_after = int(retry_header) if retry_header and retry_header.isdigit() else None
        return ApiResponse(status, decoded, retry_after)


def _retry_delays(raw: str) -> tuple[int, ...]:
    try:
        delays = tuple(int(value) for value in raw.split())
    except ValueError as exc:
        raise ReleasePublishError("retry delays must contain only integers") from exc
    if (
        not delays
        or any(value <= 0 for value in delays)
        or delays != tuple(sorted(delays))
        or not 60 <= sum(delays) <= 120
    ):
        raise ReleasePublishError(
            "retry delays must be positive, nondecreasing, and total 60-120 seconds"
        )
    return delays


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("inspect", "prepare", "finalize"))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--api-url", default="https://api.github.com")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--digest")
    parser.add_argument("--retry-delays", default="2 4 8 10 10 10 10 10 10 10 10")
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if not args.token:
            raise ReleasePublishError("GITHUB_TOKEN is required")
        transport = GitHubTransport(api_url=args.api_url, token=args.token)
        retry_delays = _retry_delays(args.retry_delays)
        if args.phase == "inspect":
            state = inspect_release_authorization(
                repository=args.repository,
                tag=args.tag,
                target_commit=args.target_commit,
                image=args.image,
                version=args.version,
                transport=transport,
                retry_delays=retry_delays,
            )
        else:
            if args.digest is None:
                raise ReleasePublishError("--digest is required for prepare and finalize phases")
            published_expected = expected_release(
                tag=args.tag,
                target_commit=args.target_commit,
                image=args.image,
                version=args.version,
                digest=args.digest,
            )
            draft_expected = expected_release(
                tag=args.tag,
                target_commit=args.target_commit,
                image=args.image,
                version=args.version,
                digest=args.digest,
                draft=True,
            )
        if args.phase == "prepare":
            state = prepare_release_authorization(
                repository=args.repository,
                draft_expected=draft_expected,
                published_expected=published_expected,
                transport=transport,
                retry_delays=retry_delays,
            )
        elif args.phase == "finalize":
            state = finalize_release(
                repository=args.repository,
                draft_expected=draft_expected,
                published_expected=published_expected,
                transport=transport,
                retry_delays=retry_delays,
            )
        if args.github_output is not None:
            with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
                output.write(f"state={state.state}\n")
                if state.release_id is not None:
                    output.write(f"release_id={state.release_id}\n")
                if state.digest is not None:
                    output.write(f"digest={state.digest}\n")
    except (OSError, ReleasePublishError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    release_label = state.release_id if state.release_id is not None else "absent"
    print(f"GitHub Release {args.tag} state={state.state} id={release_label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
