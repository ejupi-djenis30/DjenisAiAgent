"""Regression tests for the public project site."""

from __future__ import annotations

from pathlib import Path

from scripts.validate_site import EXPECTED_SOCIAL_IMAGE_SIZE, _png_dimensions, validate_site

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SITE_ROOT = PROJECT_ROOT / "site"


def test_project_site_passes_release_validator() -> None:
    assert validate_site(SITE_ROOT) == []


def test_social_preview_has_declared_dimensions() -> None:
    preview = SITE_ROOT / "media" / "djenis-ai-agent-social-preview.png"
    assert preview.is_file()
    assert _png_dimensions(preview) == EXPECTED_SOCIAL_IMAGE_SIZE


def test_setup_cta_targets_the_existing_readme_section() -> None:
    site_html = (SITE_ROOT / "index.html").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Quick start: Windows" in readme
    assert "DjenisAiAgent#quick-start-windows" in site_html


def test_release_run_command_includes_web_authentication() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
        encoding="utf-8"
    )

    assert 'DJENIS_WEB_AUTH_TOKEN="$(openssl rand -hex 24)"' in workflow
    assert "-e DJENIS_WEB_AUTH_TOKEN" in workflow


def test_walkthrough_tabs_support_standard_keyboard_navigation() -> None:
    app = (SITE_ROOT / "app.js").read_text(encoding="utf-8")

    for key in ("ArrowLeft", "ArrowRight", "Home", "End"):
        assert f"{key}:" in app
    assert 'panel.setAttribute("aria-labelledby", tabs[index].id)' in app
