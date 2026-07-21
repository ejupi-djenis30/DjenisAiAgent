"""Regression tests for the public project site."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from scripts.publish_github_release import release_body
from scripts.validate_site import EXPECTED_SOCIAL_IMAGE_SIZE, _png_dimensions, validate_site

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SITE_ROOT = PROJECT_ROOT / "site"


def test_project_site_passes_release_validator() -> None:
    assert validate_site(SITE_ROOT) == []


def test_release_validator_requires_canonical_url_and_visible_keyboard_focus() -> None:
    with tempfile.TemporaryDirectory() as folder:
        site_copy = Path(folder) / "site"
        shutil.copytree(SITE_ROOT, site_copy)
        index_path = site_copy / "index.html"
        index_path.write_text(
            index_path.read_text(encoding="utf-8").replace(
                '<link rel="canonical" href="https://ejupi-djenis30.github.io/DjenisAiAgent/">',
                "",
            ),
            encoding="utf-8",
        )
        styles_path = site_copy / "styles.css"
        styles_path.write_text(
            styles_path.read_text(encoding="utf-8").replace(
                ".demo-steps button:focus-visible,", ".demo-steps button:focus-within,"
            ),
            encoding="utf-8",
        )

        errors = validate_site(site_copy)

    assert "canonical URL must be 'https://ejupi-djenis30.github.io/DjenisAiAgent/'" in errors
    assert "keyboard focus style is missing: .demo-steps button:focus-visible" in errors


def test_social_preview_has_declared_dimensions() -> None:
    preview = SITE_ROOT / "media" / "djenis-ai-agent-social-preview.png"
    assert preview.is_file()
    assert _png_dimensions(preview) == EXPECTED_SOCIAL_IMAGE_SIZE


def test_setup_cta_targets_the_existing_readme_section() -> None:
    site_html = (SITE_ROOT / "index.html").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Quick start: Windows" in readme
    assert "DjenisAiAgent#quick-start-windows" in site_html


def test_release_body_uses_the_pinned_browser_enabled_compose_stack() -> None:
    body = release_body(
        image="ghcr.io/example/djenis-ai-agent",
        version="0.2.1",
        digest=f"sha256:{'a' * 64}",
        target_commit="b" * 40,
    )

    assert "## Browser-enabled stack (recommended)" in body
    assert (
        "https://raw.githubusercontent.com/ejupi-djenis30/DjenisAiAgent/"
        f"{'b' * 40}/docker-compose.yml"
    ) in body
    assert "curl --fail --silent --show-error --location \\\n" in body
    assert 'DJENIS_WEB_AUTH_TOKEN="$(openssl rand -hex 24)"' in body
    assert f'DJENIS_AGENT_IMAGE="ghcr.io/example/djenis-ai-agent@sha256:{"a" * 64}"' in body
    assert "docker compose -f compose.yaml pull" in body
    assert "docker compose -f compose.yaml up --no-build" in body
    assert "http://127.0.0.1:8008" in body

    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "image: ${DJENIS_AGENT_IMAGE:-djenis-ai-agent:latest}" in compose
    assert "SELENIUM_REMOTE_URL: http://chrome:4444/wd/hub" in compose


def test_release_body_keeps_the_image_only_control_plane_on_loopback() -> None:
    body = release_body(
        image="ghcr.io/example/djenis-ai-agent",
        version="0.2.1",
        digest=f"sha256:{'a' * 64}",
        target_commit="b" * 40,
    )

    assert "## Image-only control plane" in body
    assert "without browser automation" in body
    assert "-p 127.0.0.1:8000:8000" in body
    assert "-p 8000:8000" not in body
    assert "-e DJENIS_WEB_AUTH_TOKEN" in body
    assert "-e DJENIS_PERMISSION_TIER=observe" in body


def test_walkthrough_tabs_support_standard_keyboard_navigation() -> None:
    app = (SITE_ROOT / "app.js").read_text(encoding="utf-8")

    for key in ("ArrowLeft", "ArrowRight", "Home", "End"):
        assert f"{key}:" in app
    assert 'panel.setAttribute("aria-labelledby", tabs[index].id)' in app


def test_project_site_uses_the_interactive_walkthrough_without_a_video_reel() -> None:
    site_html = (SITE_ROOT / "index.html").read_text(encoding="utf-8")

    assert "<video" not in site_html.lower()
    assert list(SITE_ROOT.rglob("*.mp4")) == []


def test_project_site_keeps_small_controls_readable_and_touch_accessible() -> None:
    styles = (SITE_ROOT / "styles.css").read_text(encoding="utf-8")

    console_rule = re.search(r"\.console-bar\s*\{(?P<body>[^}]*)\}", styles)
    control_rule = re.search(r"\.demo-control\s*\{(?P<body>[^}]*)\}", styles)

    assert console_rule is not None
    assert "color: var(--muted)" in console_rule.group("body")
    assert control_rule is not None
    assert "min-height: 44px" in control_rule.group("body")
