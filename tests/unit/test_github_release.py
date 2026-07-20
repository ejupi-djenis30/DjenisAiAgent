"""Tests for durable, exact, immutable GitHub Release publication."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
import scripts.publish_github_release as publisher
from scripts.publish_github_release import (
    ApiResponse,
    ReleasePublishError,
    expected_release,
    finalize_release,
    inspect_release_authorization,
    prepare_release_authorization,
)

REPOSITORY = "ejupi-djenis30/DjenisAiAgent"
IMAGE = "ghcr.io/ejupi-djenis30/djenis-ai-agent"
DIGEST = f"sha256:{'a' * 64}"
COMMIT = "b" * 40


def _expected(*, draft: bool = False, digest: str = DIGEST) -> dict[str, object]:
    return expected_release(
        tag="v0.2.1",
        target_commit=COMMIT,
        image=IMAGE,
        version="0.2.1",
        digest=digest,
        draft=draft,
    )


def _actual(
    expected: Mapping[str, object],
    *,
    release_id: int = 41,
    immutable: bool | None = None,
) -> dict[str, object]:
    draft = bool(expected["draft"])
    return {
        "id": release_id,
        "tag_name": expected["tag_name"],
        "target_commitish": "master",
        "name": expected["name"],
        "body": expected["body"],
        "draft": draft,
        "prerelease": False,
        "immutable": (not draft) if immutable is None else immutable,
        "assets": [],
    }


def _tag_ref(commit: str = COMMIT) -> ApiResponse:
    return ApiResponse(200, {"object": {"type": "commit", "sha": commit}})


def _inventory(*releases: Mapping[str, object]) -> ApiResponse:
    return ApiResponse(200, [dict(release) for release in releases])


@pytest.mark.parametrize(
    "image",
    [
        "https://ghcr.io/owner/image",
        "ghcr.io/owner",
        "ghcr.io/owner/image:latest",
        f"ghcr.io/owner/image@sha256:{'a' * 64}",
        "ghcr.io/owner/image\n```\nuntrusted release notes",
        "ghcr.io/owner/../image",
        "ghcr.io/Owner/image",
    ],
)
def test_release_image_must_be_an_exact_normalized_ghcr_repository(image: str) -> None:
    with pytest.raises(ReleasePublishError, match="normalized GHCR name"):
        expected_release(
            tag="v0.2.1",
            target_commit=COMMIT,
            image=image,
            version="0.2.1",
            digest=DIGEST,
        )


def test_inspect_absent_release_exports_recoverable_new_state() -> None:
    paths: list[str] = []

    def transport(method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        paths.append(path)
        if "/git/ref/tags/" in path:
            return _tag_ref()
        assert method == "GET"
        return _inventory()

    state = inspect_release_authorization(
        repository=REPOSITORY,
        tag="v0.2.1",
        target_commit=COMMIT,
        image=IMAGE,
        version="0.2.1",
        transport=transport,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    assert state.state == "absent"
    assert state.digest is None
    assert paths[0].endswith("/git/ref/tags/v0.2.1")


def test_inspect_exact_draft_recovers_its_authorized_digest() -> None:
    draft = _expected(draft=True)

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        return _inventory(_actual(draft))

    state = inspect_release_authorization(
        repository=REPOSITORY,
        tag="v0.2.1",
        target_commit=COMMIT,
        image=IMAGE,
        version="0.2.1",
        transport=transport,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    assert state.state == "draft"
    assert state.release_id == 41
    assert state.digest == DIGEST


def test_inspect_finds_an_old_draft_on_the_second_inventory_page() -> None:
    draft = _expected(draft=True)
    unrelated = [
        {"id": 1000 + index, "tag_name": f"notes-{index}", "draft": False} for index in range(100)
    ]
    pages: list[str] = []

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        pages.append(path)
        if path.endswith("page=1"):
            return ApiResponse(200, unrelated)
        return _inventory(_actual(draft))

    state = inspect_release_authorization(
        repository=REPOSITORY,
        tag="v0.2.1",
        target_commit=COMMIT,
        image=IMAGE,
        version="0.2.1",
        transport=transport,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    assert state.state == "draft"
    assert any("page=2" in path for path in pages)
    assert all("/releases/tags/" not in path for path in pages)


def test_duplicate_exact_tag_across_inventory_pages_fails_closed() -> None:
    draft = _actual(_expected(draft=True))
    first_page = [
        {"id": 1000 + index, "tag_name": f"notes-{index}", "draft": False} for index in range(99)
    ]
    first_page.append(draft)

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        return ApiResponse(200, first_page) if path.endswith("page=1") else _inventory(draft)

    with pytest.raises(ReleasePublishError, match="multiple Releases"):
        inspect_release_authorization(
            repository=REPOSITORY,
            tag="v0.2.1",
            target_commit=COMMIT,
            image=IMAGE,
            version="0.2.1",
            transport=transport,
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )


def test_non_array_release_inventory_fails_closed() -> None:
    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        return ApiResponse(200, {"tag_name": "v0.2.1"})

    with pytest.raises(ReleasePublishError, match="inventory must be a JSON array"):
        inspect_release_authorization(
            repository=REPOSITORY,
            tag="v0.2.1",
            target_commit=COMMIT,
            image=IMAGE,
            version="0.2.1",
            transport=transport,
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )


def test_release_inventory_page_cap_fails_instead_of_claiming_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publisher, "MAX_RELEASE_PAGES", 2)
    full_page = [
        {"id": 1000 + index, "tag_name": f"notes-{index}", "draft": False} for index in range(100)
    ]

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        return ApiResponse(200, full_page)

    with pytest.raises(ReleasePublishError, match="bounded 2-page search"):
        inspect_release_authorization(
            repository=REPOSITORY,
            tag="v0.2.1",
            target_commit=COMMIT,
            image=IMAGE,
            version="0.2.1",
            transport=transport,
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )


def test_other_draft_blocks_a_new_release_sequence() -> None:
    other_draft = {"id": 40, "tag_name": "v0.2.0", "draft": True}

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        return _inventory(other_draft)

    with pytest.raises(ReleasePublishError, match="must be completed first"):
        inspect_release_authorization(
            repository=REPOSITORY,
            tag="v0.2.1",
            target_commit=COMMIT,
            image=IMAGE,
            version="0.2.1",
            transport=transport,
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )


def test_newer_published_release_blocks_an_older_draft_retry() -> None:
    current_draft = _actual(_expected(draft=True))
    newer_published = {"id": 42, "tag_name": "v0.2.2", "draft": False}

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        return _inventory(current_draft, newer_published)

    with pytest.raises(ReleasePublishError, match="newer published Releases"):
        inspect_release_authorization(
            repository=REPOSITORY,
            tag="v0.2.1",
            target_commit=COMMIT,
            image=IMAGE,
            version="0.2.1",
            transport=transport,
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )


def test_inspect_recovers_a_recent_publish_until_it_is_immutable_and_latest() -> None:
    published = _expected()
    mutable = _actual(published, immutable=False)
    immutable = _actual(published, immutable=True)
    release_reads = iter((mutable, immutable))
    sleeps: list[float] = []

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        if "?per_page=" in path:
            return _inventory(mutable)
        if path.endswith("/latest"):
            return ApiResponse(200, {"id": 41})
        return ApiResponse(200, next(release_reads))

    state = inspect_release_authorization(
        repository=REPOSITORY,
        tag="v0.2.1",
        target_commit=COMMIT,
        image=IMAGE,
        version="0.2.1",
        transport=transport,
        retry_delays=(60,),
        sleep=sleeps.append,
    )

    assert state.state == "published"
    assert sleeps == [60.0]


def test_historical_published_inspection_does_not_require_latest() -> None:
    published = _expected()
    newer_published = {"id": 42, "tag_name": "v0.2.2", "draft": False}
    paths: list[str] = []

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        paths.append(path)
        if "/git/ref/tags/" in path:
            return _tag_ref()
        if "?per_page=" in path:
            return _inventory(_actual(published), newer_published)
        raise AssertionError(f"historical inspection made an unexpected request: {path}")

    state = inspect_release_authorization(
        repository=REPOSITORY,
        tag="v0.2.1",
        target_commit=COMMIT,
        image=IMAGE,
        version="0.2.1",
        transport=transport,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    assert state.state == "published"
    assert all(not path.endswith("/latest") for path in paths)


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("body", "stale digest", "consistent OCI digest"),
        ("assets", [{"name": "unexpected.zip"}], "asset inventory"),
        ("prerelease", True, "prerelease"),
        ("immutable", True, "immutable state"),
    ],
)
def test_partial_or_incoherent_draft_authorization_fails_closed(
    field: str, bad_value: object, message: str
) -> None:
    draft = _expected(draft=True)
    actual = _actual(draft)
    actual[field] = bad_value

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        return _inventory(actual)

    with pytest.raises(ReleasePublishError, match=message):
        inspect_release_authorization(
            repository=REPOSITORY,
            tag="v0.2.1",
            target_commit=COMMIT,
            image=IMAGE,
            version="0.2.1",
            transport=transport,
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )


def test_prepare_creates_an_exact_non_latest_draft_before_alias_promotion() -> None:
    draft = _expected(draft=True)
    published = _expected()
    calls: list[tuple[str, str, Mapping[str, object] | None]] = []

    def transport(method: str, path: str, payload: Mapping[str, object] | None) -> ApiResponse:
        calls.append((method, path, payload))
        if "/git/ref/tags/" in path:
            return _tag_ref()
        if method == "GET":
            return _inventory()
        return ApiResponse(201, _actual(draft))

    state = prepare_release_authorization(
        repository=REPOSITORY,
        draft_expected=draft,
        published_expected=published,
        transport=transport,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    post = next(call for call in calls if call[0] == "POST")
    assert post[2] == draft
    assert draft["draft"] is True
    assert draft["make_latest"] == "false"
    assert state == type(state)("draft", 41, DIGEST)


def test_prepare_reuses_exact_draft_without_requiring_current_master() -> None:
    draft = _expected(draft=True)
    published = _expected()
    methods: list[str] = []

    def transport(method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        methods.append(method)
        if "/git/ref/tags/" in path:
            return _tag_ref()
        return _inventory(_actual(draft))

    state = prepare_release_authorization(
        repository=REPOSITORY,
        draft_expected=draft,
        published_expected=published,
        transport=transport,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    assert state.state == "draft"
    assert methods == ["GET", "GET"]


def test_prepare_conflict_is_resolved_only_from_exact_remote_state() -> None:
    draft = _expected(draft=True)
    responses = iter(
        (
            _tag_ref(),
            _inventory(),
            ApiResponse(422, {"message": "already_exists"}),
            _inventory(_actual(draft)),
        )
    )

    state = prepare_release_authorization(
        repository=REPOSITORY,
        draft_expected=draft,
        published_expected=_expected(),
        transport=lambda _method, _path, _payload: next(responses),
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    assert state.state == "draft"


def test_finalize_publishes_same_draft_then_waits_for_immutable_latest_state() -> None:
    draft = _expected(draft=True)
    published = _expected()
    calls: list[tuple[str, str, Mapping[str, object] | None]] = []
    published_mutable = _actual(published, immutable=False)
    published_immutable = _actual(published, immutable=True)
    release_reads = iter((published_mutable, published_mutable, published_immutable))
    sleeps: list[float] = []

    def transport(method: str, path: str, payload: Mapping[str, object] | None) -> ApiResponse:
        calls.append((method, path, payload))
        if "/git/ref/tags/" in path:
            return _tag_ref()
        if "?per_page=" in path:
            return _inventory(_actual(draft))
        if path.endswith("/latest"):
            return ApiResponse(200, {"id": 41})
        if method == "PATCH":
            return ApiResponse(200, next(release_reads))
        return ApiResponse(200, next(release_reads))

    state = finalize_release(
        repository=REPOSITORY,
        draft_expected=draft,
        published_expected=published,
        transport=transport,
        retry_delays=(60,),
        sleep=sleeps.append,
    )

    patch = next(call for call in calls if call[0] == "PATCH")
    assert patch[1].endswith("/releases/41")
    assert patch[2] is not None
    assert patch[2]["draft"] is False
    assert patch[2]["make_latest"] == "true"
    assert "generate_release_notes" not in patch[2]
    assert sleeps == [60.0]
    assert state.state == "published"


def test_finalize_exact_published_release_is_an_idempotent_no_patch() -> None:
    published = _expected()
    methods: list[str] = []
    paths: list[str] = []
    newer_published = {"id": 42, "tag_name": "v0.2.2", "draft": False}

    def transport(method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        methods.append(method)
        paths.append(path)
        if "/git/ref/tags/" in path:
            return _tag_ref()
        if "?per_page=" in path:
            return _inventory(_actual(published), newer_published)
        return ApiResponse(200, _actual(published))

    state = finalize_release(
        repository=REPOSITORY,
        draft_expected=_expected(draft=True),
        published_expected=published,
        transport=transport,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    assert state.state == "published"
    assert "PATCH" not in methods
    assert all(not path.endswith("/latest") for path in paths)


def test_finalize_fails_if_durable_draft_was_removed() -> None:
    responses = iter(
        (
            _tag_ref(),
            _inventory(),
        )
    )

    with pytest.raises(ReleasePublishError, match="authorization is missing"):
        finalize_release(
            repository=REPOSITORY,
            draft_expected=_expected(draft=True),
            published_expected=_expected(),
            transport=lambda _method, _path, _payload: next(responses),
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )


def test_finalize_fails_closed_when_publication_never_becomes_immutable() -> None:
    published = _expected()

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return _tag_ref()
        if "?per_page=" in path:
            return _inventory(_actual(published, immutable=False))
        return ApiResponse(200, _actual(published, immutable=False))

    with pytest.raises(ReleasePublishError, match="did not become immutable"):
        finalize_release(
            repository=REPOSITORY,
            draft_expected=_expected(draft=True),
            published_expected=published,
            transport=transport,
            retry_delays=(30, 30),
            sleep=lambda _delay: None,
        )


def test_remote_tag_target_must_match_before_release_state_is_read() -> None:
    calls = 0

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        nonlocal calls
        calls += 1
        return _tag_ref("c" * 40)

    with pytest.raises(ReleasePublishError, match="unexpected commit"):
        inspect_release_authorization(
            repository=REPOSITORY,
            tag="v0.2.1",
            target_commit=COMMIT,
            image=IMAGE,
            version="0.2.1",
            transport=transport,
            retry_delays=(60,),
            sleep=lambda _delay: None,
        )

    assert calls == 1


def test_annotated_remote_tag_is_dereferenced_to_the_exact_commit() -> None:
    tag_object = "d" * 40

    def transport(_method: str, path: str, _payload: Mapping[str, object] | None) -> ApiResponse:
        if "/git/ref/tags/" in path:
            return ApiResponse(200, {"object": {"type": "tag", "sha": tag_object}})
        if f"/git/tags/{tag_object}" in path:
            return ApiResponse(200, {"object": {"type": "commit", "sha": COMMIT}})
        return _inventory()

    state = inspect_release_authorization(
        repository=REPOSITORY,
        tag="v0.2.1",
        target_commit=COMMIT,
        image=IMAGE,
        version="0.2.1",
        transport=transport,
        retry_delays=(60,),
        sleep=lambda _delay: None,
    )

    assert state.state == "absent"
