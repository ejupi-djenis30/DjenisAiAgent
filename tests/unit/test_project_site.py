"""Regression tests for the public project site."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import pytest
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


def test_hero_title_type_scale_is_continuous_across_the_mobile_breakpoint() -> None:
    styles = (SITE_ROOT / "styles.css").read_text(encoding="utf-8")
    bridge_match = re.search(r"--hero-title-bridge:\s*(?P<value>[\d.]+)rem", styles)
    desktop_match = re.search(
        r"^h1\s*\{[^}]*font-size:\s*clamp\(var\(--hero-title-bridge\),\s*"
        r"(?P<fluid>[\d.]+)vw,\s*(?P<ceiling>[\d.]+)rem\)",
        styles,
        re.MULTILINE,
    )
    mobile_match = re.search(
        r"@media\s*\(max-width:\s*680px\)\s*\{(?P<body>.*?)^\}",
        styles,
        re.MULTILINE | re.DOTALL,
    )

    assert bridge_match is not None
    assert desktop_match is not None
    assert mobile_match is not None

    mobile_title_match = re.search(
        r"^\s*h1\s*\{[^}]*font-size:\s*clamp\((?P<floor>[\d.]+)rem,\s*"
        r"(?P<fluid>[\d.]+)vw,\s*var\(--hero-title-bridge\)\)",
        mobile_match.group("body"),
        re.MULTILINE,
    )
    assert mobile_title_match is not None

    root_font_size = 16.0
    bridge = float(bridge_match.group("value")) * root_font_size
    desktop_fluid = float(desktop_match.group("fluid")) / 100
    desktop_ceiling = float(desktop_match.group("ceiling")) * root_font_size
    mobile_floor = float(mobile_title_match.group("floor")) * root_font_size
    mobile_fluid = float(mobile_title_match.group("fluid")) / 100

    def title_size(viewport: int) -> float:
        if viewport <= 680:
            return min(max(mobile_floor, viewport * mobile_fluid), bridge)
        return min(max(bridge, viewport * desktop_fluid), desktop_ceiling)

    sizes = {viewport: title_size(viewport) for viewport in (320, 375, 680, 681, 900)}

    assert sizes[320] == pytest.approx(59.2)
    assert sizes[375] == pytest.approx(67.5)
    assert sizes[900] == pytest.approx(77.4)
    assert abs(sizes[681] - sizes[680]) <= 0.1
    assert list(sizes.values()) == sorted(sizes.values())


def test_hero_title_wrap_space_is_continuous_across_the_mobile_breakpoint() -> None:
    styles = (SITE_ROOT / "styles.css").read_text(encoding="utf-8")
    container_match = re.search(
        r"^\.site-header,\s*main > section,\s*footer\s*\{(?P<body>[^}]*)\}",
        styles,
        re.MULTILINE,
    )
    mobile_match = re.search(
        r"@media\s*\(max-width:\s*680px\)\s*\{(?P<body>.*?)^\}",
        styles,
        re.MULTILINE | re.DOTALL,
    )
    page_inset_match = re.search(
        r"--page-inset:\s*clamp\((?P<floor>[\d.]+)px,\s*"
        r"(?P<fluid>[\d.]+)vw,\s*(?P<ceiling>[\d.]+)px\)",
        styles,
    )

    assert container_match is not None
    assert mobile_match is not None

    width_pattern = re.compile(
        r"width:\s*min\(1500px,\s*calc\(100%\s*-\s*"
        r"(?P<inset>var\(--page-inset\)|[\d.]+px)\)\)"
    )
    compact_width_pattern = re.compile(r"width:\s*min\(100%\s*-\s*(?P<inset>[\d.]+px),\s*1500px\)")
    base_width_match = width_pattern.search(container_match.group("body"))
    mobile_container_match = re.search(
        r"\.site-header,\s*main > section,\s*footer\s*\{(?P<body>[^}]*)\}",
        mobile_match.group("body"),
    )
    mobile_width_match = (
        (
            width_pattern.search(mobile_container_match.group("body"))
            or compact_width_pattern.search(mobile_container_match.group("body"))
        )
        if mobile_container_match is not None
        else None
    )

    assert base_width_match is not None

    def inset_for(token: str, viewport: int) -> float:
        if token != "var(--page-inset)":
            return float(token.removesuffix("px"))
        assert page_inset_match is not None
        floor = float(page_inset_match.group("floor"))
        fluid = viewport * float(page_inset_match.group("fluid")) / 100
        ceiling = float(page_inset_match.group("ceiling"))
        return min(max(floor, fluid), ceiling)

    def title_width(viewport: int) -> float:
        inset_token = base_width_match.group("inset")
        if viewport <= 680 and mobile_width_match is not None:
            inset_token = mobile_width_match.group("inset")
        content_width = viewport - inset_for(inset_token, viewport)
        return min(content_width, 800.0)

    widths = {viewport: title_width(viewport) for viewport in (320, 375, 680, 681, 900)}

    assert abs(widths[681] - widths[680]) <= 1.0, (
        "The title's available width must not jump across the 680/681px breakpoint."
    )
    assert page_inset_match is not None
    assert widths[320] == pytest.approx(292.0)
    assert widths[375] == pytest.approx(347.0)
    assert widths[680] >= 630.0
    assert widths[900] == pytest.approx(800.0)
    assert list(widths.values()) == sorted(widths.values())
