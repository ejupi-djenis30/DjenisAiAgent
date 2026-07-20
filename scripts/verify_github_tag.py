"""Verify that an exact release ref is an annotated, GitHub-verified SSH tag."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
from collections.abc import Callable, Mapping
from http.client import HTTPSConnection
from typing import cast
from urllib.parse import quote, urlsplit

TAG_PATTERN = re.compile(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40,64}")
TAG_OBJECT_PATTERN = re.compile(r"[0-9a-f]{40,64}")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SSH_SIGNATURE_HEADER = "-----BEGIN SSH SIGNATURE-----"
MAX_RESPONSE_BYTES = 1_048_576

JsonGetter = Callable[[str], object]


class GitHubTagVerificationError(RuntimeError):
    """Raised when the remote release tag does not meet the signing contract."""


def _object(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GitHubTagVerificationError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], value)


def verify_github_release_tag(
    *,
    repository: str,
    tag: str,
    expected_commit: str,
    get_json: JsonGetter,
) -> str:
    """Return the tag-object SHA after checking annotation, target, and SSH verification."""

    if REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise GitHubTagVerificationError("repository must use the owner/name form")
    if TAG_PATTERN.fullmatch(tag) is None:
        raise GitHubTagVerificationError("release tag must be stable v-prefixed SemVer")
    if COMMIT_PATTERN.fullmatch(expected_commit) is None:
        raise GitHubTagVerificationError("expected commit must be an exact Git object id")

    ref_path = f"/repos/{repository}/git/ref/tags/{quote(tag, safe='')}"
    ref = _object(get_json(ref_path), label="release tag ref")
    if ref.get("ref") != f"refs/tags/{tag}":
        raise GitHubTagVerificationError("GitHub returned a different release tag ref")

    ref_object = _object(ref.get("object"), label="release tag ref object")
    if ref_object.get("type") != "tag":
        raise GitHubTagVerificationError(
            "release tag must be annotated; lightweight tags are not accepted"
        )
    tag_object_sha = ref_object.get("sha")
    if not isinstance(tag_object_sha, str) or TAG_OBJECT_PATTERN.fullmatch(tag_object_sha) is None:
        raise GitHubTagVerificationError("release tag ref is missing an exact tag-object id")

    tag_object_path = f"/repos/{repository}/git/tags/{tag_object_sha}"
    tag_object = _object(get_json(tag_object_path), label="annotated release tag")
    if tag_object.get("sha") != tag_object_sha or tag_object.get("tag") != tag:
        raise GitHubTagVerificationError("annotated tag object does not match the requested tag")

    target = _object(tag_object.get("object"), label="annotated tag target")
    if target.get("type") != "commit" or target.get("sha") != expected_commit:
        raise GitHubTagVerificationError(
            "annotated release tag must target the exact authorized commit"
        )

    verification = _object(tag_object.get("verification"), label="GitHub tag verification")
    if verification.get("verified") is not True or verification.get("reason") != "valid":
        raise GitHubTagVerificationError(
            "GitHub must report the annotated release tag signature as valid"
        )
    signature = verification.get("signature")
    if not isinstance(signature, str) or not signature.lstrip().startswith(SSH_SIGNATURE_HEADER):
        raise GitHubTagVerificationError("release tag must use a GitHub-verified SSH signature")

    return tag_object_sha


def github_json_getter(*, api_url: str, token: str) -> JsonGetter:
    """Build a bounded authenticated reader for the GitHub REST API."""

    parsed = urlsplit(api_url)
    hostname = parsed.hostname
    if parsed.scheme != "https" or hostname is None or parsed.query or parsed.fragment:
        raise GitHubTagVerificationError("GitHub API URL must be an absolute HTTPS URL")
    if not token.strip():
        raise GitHubTagVerificationError("GITHUB_TOKEN is required for tag verification")
    base_path = parsed.path.rstrip("/")

    def get_json(path: str) -> object:
        connection = HTTPSConnection(
            hostname,
            parsed.port or 443,
            timeout=30,
            context=ssl.create_default_context(),
        )
        try:
            connection.request(
                "GET",
                f"{base_path}{path}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "DjenisAiAgent-release-tag-verifier",
                    "X-GitHub-Api-Version": "2026-03-10",
                },
            )
            response = connection.getresponse()
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        finally:
            connection.close()
        if len(payload) > MAX_RESPONSE_BYTES:
            raise GitHubTagVerificationError("GitHub API response exceeded the size limit")
        if response.status != 200:
            raise GitHubTagVerificationError(
                f"GitHub API returned HTTP {response.status} while reading the release tag"
            )
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubTagVerificationError("GitHub API returned invalid JSON") from exc

    return get_json


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub owner/name")
    parser.add_argument("--api-url", default="https://api.github.com")
    parser.add_argument("--tag", required=True, help="Release tag including the leading v")
    parser.add_argument("--expected-commit", required=True, help="Exact dereferenced commit id")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        tag_object_sha = verify_github_release_tag(
            repository=args.repository,
            tag=args.tag,
            expected_commit=args.expected_commit,
            get_json=github_json_getter(
                api_url=args.api_url,
                token=os.environ.get("GITHUB_TOKEN", ""),
            ),
        )
    except (OSError, GitHubTagVerificationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Verified annotated GitHub SSH tag {args.tag} ({tag_object_sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
