"""Validate the static project site before it is published."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

SITE_ORIGIN = "https://ejupi-djenis30.github.io"
SITE_PREFIX = "/DjenisAiAgent/"
SITE_URL = f"{SITE_ORIGIN}{SITE_PREFIX}"
SITEMAP_URL = f"{SITE_URL}sitemap.xml"
SECURITY_URL = f"{SITE_URL}.well-known/security.txt"
SECURITY_CONTACT_URL = "https://github.com/ejupi-djenis30/DjenisAiAgent/security/advisories/new"
SECURITY_POLICY_URL = "https://github.com/ejupi-djenis30/DjenisAiAgent/security/policy"
SOCIAL_IMAGE_URL = f"{SITE_ORIGIN}{SITE_PREFIX}media/djenis-ai-agent-social-preview.png"
RELEASE_URL = "https://github.com/ejupi-djenis30/DjenisAiAgent/releases/tag/v0.3.0"
GHCR_PACKAGE_URL = (
    "https://github.com/users/ejupi-djenis30/packages/container/package/djenis-ai-agent"
)
WINDOWS_SETUP_URL = (
    "https://github.com/ejupi-djenis30/DjenisAiAgent/tree/v0.3.0#quick-start-windows"
)
EXPECTED_SOCIAL_IMAGE_SIZE = (1200, 675)
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
PUBLIC_DISCOVERY_FILES = (
    Path("robots.txt"),
    Path("sitemap.xml"),
    Path(".well-known/security.txt"),
)
EXPECTED_ROBOTS = f"User-agent: *\nAllow: {SITE_PREFIX}\n\nSitemap: {SITEMAP_URL}\n"
EXPECTED_SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    f'<urlset xmlns="{SITEMAP_NAMESPACE}">\n'
    "  <url>\n"
    f"    <loc>{SITE_URL}</loc>\n"
    "  </url>\n"
    "</urlset>\n"
)
EXPECTED_SECURITY_VALUES = {
    "Contact": SECURITY_CONTACT_URL,
    "Preferred-Languages": "en",
    "Canonical": SECURITY_URL,
    "Policy": SECURITY_POLICY_URL,
}
REQUIRED_CSP_DIRECTIVES = {
    "default-src 'self'",
    "base-uri 'none'",
    "object-src 'none'",
    "form-action 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self'",
    "media-src 'none'",
    "font-src 'self'",
    "connect-src 'none'",
    "frame-src 'none'",
    "worker-src 'none'",
}


class SiteDocument(HTMLParser):
    """Collect the small set of document properties needed by the validator."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_lang = ""
        self.meta: dict[str, str] = {}
        self.canonical_url = ""
        self.local_assets: set[str] = set()
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}

        if tag == "html":
            self.html_lang = attributes.get("lang", "")
        elif tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            if key:
                self.meta[key] = attributes.get("content", "")
            http_equiv = attributes.get("http-equiv")
            if http_equiv:
                self.meta[http_equiv.lower()] = attributes.get("content", "")
        elif tag == "link" and "canonical" in attributes.get("rel", "").split():
            self.canonical_url = attributes.get("href", "")
        elif tag == "a":
            self.links.add(attributes.get("href", ""))
        for attribute in ("href", "src"):
            value = attributes.get(attribute, "")
            if value.startswith("./"):
                self.local_assets.add(value)


def _local_path(site_root: Path, reference: str) -> Path:
    relative = unquote(urlparse(reference).path).removeprefix("./")
    candidate = (site_root / relative).resolve()
    root = site_root.resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError(f"asset escapes the site directory: {reference}")
    return candidate


def _png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("social preview is not a valid PNG file")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def _validate_robots(path: Path, errors: list[str]) -> None:
    try:
        robots = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"site/robots.txt is unreadable: {exc}")
        return
    if robots != EXPECTED_ROBOTS:
        errors.append(
            "site/robots.txt must allow only the canonical project path and advertise "
            f"{SITEMAP_URL}"
        )


def _validate_sitemap(path: Path, errors: list[str]) -> None:
    try:
        sitemap = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"site/sitemap.xml is unreadable: {exc}")
        return
    if sitemap != EXPECTED_SITEMAP:
        errors.append(f"site/sitemap.xml must list only the canonical project URL {SITE_URL!r}")


def _validate_security_txt(path: Path, errors: list[str], *, now: datetime) -> None:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"site/.well-known/security.txt is unreadable: {exc}")
        return

    fields: dict[str, list[str]] = {}
    for line_number, line in enumerate(source.splitlines(), start=1):
        if not line:
            continue
        name, separator, value = line.partition(":")
        if not separator or not name or not value.strip():
            errors.append(
                f"site/.well-known/security.txt contains an invalid field on line {line_number}"
            )
            continue
        fields.setdefault(name, []).append(value.strip())

    expected_fields = {*EXPECTED_SECURITY_VALUES, "Expires"}
    unexpected_fields = sorted(set(fields) - expected_fields)
    if unexpected_fields:
        errors.append(
            "site/.well-known/security.txt contains unexpected fields: "
            f"{', '.join(unexpected_fields)}"
        )

    for field, expected in EXPECTED_SECURITY_VALUES.items():
        values = fields.get(field, [])
        if values != [expected]:
            errors.append(f"site/.well-known/security.txt {field} must be exactly {expected!r}")

    contacts = fields.get("Contact", [])
    if any(contact.casefold().startswith("mailto:") for contact in contacts):
        errors.append("site/.well-known/security.txt must not publish an email contact")

    expires_values = fields.get("Expires", [])
    if len(expires_values) != 1:
        errors.append("site/.well-known/security.txt must contain exactly one Expires field")
        return
    try:
        expires = datetime.strptime(expires_values[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        errors.append("site/.well-known/security.txt Expires must be an RFC 3339 UTC timestamp")
        return

    current_time = now.astimezone(UTC)
    if expires <= current_time:
        errors.append("site/.well-known/security.txt Expires must remain in the future")
    if expires > current_time + timedelta(days=366):
        errors.append("site/.well-known/security.txt Expires must be no more than one year ahead")


def validate_site(site_root: Path, *, now: datetime | None = None) -> list[str]:
    """Return validation errors for a project site, or an empty list."""

    errors: list[str] = []
    index_path = site_root / "index.html"
    if not index_path.is_file():
        return ["site/index.html is missing"]
    for relative_path in PUBLIC_DISCOVERY_FILES:
        if not (site_root / relative_path).is_file():
            errors.append(
                f"site/{relative_path.as_posix()} is missing from the public discovery inventory"
            )

    html_source = index_path.read_text(encoding="utf-8")
    document = SiteDocument()
    document.feed(html_source)

    if document.html_lang != "en":
        errors.append('the document language must be "en"')
    if document.meta.get("referrer") != "no-referrer":
        errors.append('the referrer policy must be "no-referrer"')
    if document.canonical_url != SITE_URL:
        errors.append(f"canonical URL must be {SITE_URL!r}")
    if RELEASE_URL not in document.links:
        errors.append(f"the install path must link to the canonical release {RELEASE_URL!r}")
    if GHCR_PACKAGE_URL not in document.links:
        errors.append(f"the install path must link to the public GHCR package {GHCR_PACKAGE_URL!r}")
    if WINDOWS_SETUP_URL not in document.links:
        errors.append(
            "the install path must distinguish the Windows-native source setup from Compose"
        )
    if any("/releases/download/" in link for link in document.links):
        errors.append("the asset-free release must not advertise downloadable release files")
    if "There is no desktop installer or downloadable release archive." not in html_source:
        errors.append("the install path must state that v0.3.0 has no downloadable installer")

    for token in (
        'role="tablist"',
        'role="tab" aria-controls="demo-panel"',
        'id="demo-panel" role="tabpanel"',
        'aria-labelledby="demo-tab-0"',
    ):
        if token not in html_source:
            errors.append(f"the walkthrough is missing accessible tab markup: {token}")

    if "<video" in html_source.lower():
        errors.append("the project page must not embed a landing-page video")

    csp = {
        directive.strip()
        for directive in document.meta.get("content-security-policy", "").split(";")
        if directive.strip()
    }
    missing_directives = REQUIRED_CSP_DIRECTIVES - csp
    if missing_directives:
        errors.append(f"CSP is missing: {', '.join(sorted(missing_directives))}")

    expected_meta = {
        "og:url": SITE_URL,
        "og:image": SOCIAL_IMAGE_URL,
        "og:image:type": "image/png",
        "og:image:width": str(EXPECTED_SOCIAL_IMAGE_SIZE[0]),
        "og:image:height": str(EXPECTED_SOCIAL_IMAGE_SIZE[1]),
        "twitter:card": "summary_large_image",
        "twitter:image": SOCIAL_IMAGE_URL,
    }
    for key, expected in expected_meta.items():
        if document.meta.get(key) != expected:
            errors.append(f"{key} must be {expected!r}")

    for key in ("og:image:alt", "twitter:image:alt"):
        if not document.meta.get(key, "").strip():
            errors.append(f"{key} must describe the preview image")

    for reference in sorted(document.local_assets):
        try:
            asset_path = _local_path(site_root, reference)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not asset_path.is_file():
            errors.append(f"referenced asset is missing: {reference}")

    robots_path = site_root / "robots.txt"
    if robots_path.is_file():
        _validate_robots(robots_path, errors)

    sitemap_path = site_root / "sitemap.xml"
    if sitemap_path.is_file():
        _validate_sitemap(sitemap_path, errors)

    security_path = site_root / ".well-known" / "security.txt"
    if security_path.is_file():
        _validate_security_txt(security_path, errors, now=now or datetime.now(UTC))

    styles_path = site_root / "styles.css"
    try:
        styles = styles_path.read_text(encoding="utf-8")
    except OSError:
        errors.append("site/styles.css is missing or unreadable")
    else:
        required_focus_controls = (
            ".brand:focus-visible",
            ".site-header nav a:focus-visible",
            ".button:focus-visible",
            ".nav-install:focus-visible",
            ".demo-steps button:focus-visible",
            ".demo-control:focus-visible",
            ".demo-stage:focus-visible",
            ".text-link:focus-visible",
        )
        for selector in required_focus_controls:
            if selector not in styles:
                errors.append(f"keyboard focus style is missing: {selector}")
        if "outline:" not in styles or "outline-offset:" not in styles:
            errors.append("keyboard focus styles must draw an explicit outline")

    social_image_path = site_root / "media" / "djenis-ai-agent-social-preview.png"
    try:
        dimensions = _png_dimensions(social_image_path)
    except (OSError, ValueError) as exc:
        errors.append(f"invalid social preview: {exc}")
    else:
        if dimensions != EXPECTED_SOCIAL_IMAGE_SIZE:
            errors.append(
                f"social preview is {dimensions[0]}x{dimensions[1]}, "
                f"expected {EXPECTED_SOCIAL_IMAGE_SIZE[0]}x{EXPECTED_SOCIAL_IMAGE_SIZE[1]}"
            )

    return errors


def main() -> int:
    site_root = Path(__file__).resolve().parents[1] / "site"
    errors = validate_site(site_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "Site validation passed: metadata, discovery files, policy, social preview, "
        "and walkthrough are valid."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
