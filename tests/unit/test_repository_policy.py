"""Regression tests for repository automation policy."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKOUT_ACTION = "uses: actions/checkout@"
HARDENED_CHECKOUT_PATTERN = re.compile(
    r"uses: actions/checkout@[^\n]+\n\s+with:\n\s+persist-credentials: false"
)


def test_dependabot_updates_the_canonical_uv_lockfile() -> None:
    configuration = (PROJECT_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert 'package-ecosystem: "uv"' in configuration
    assert 'package-ecosystem: "pip"' not in configuration


def test_every_checkout_drops_persisted_credentials() -> None:
    workflow_directory = PROJECT_ROOT / ".github" / "workflows"
    workflow_files = sorted((*workflow_directory.glob("*.yml"), *workflow_directory.glob("*.yaml")))
    checkout_count = 0

    for workflow_file in workflow_files:
        workflow = workflow_file.read_text(encoding="utf-8")
        checkout_count += workflow.count(CHECKOUT_ACTION)
        assert workflow.count(CHECKOUT_ACTION) == len(
            HARDENED_CHECKOUT_PATTERN.findall(workflow)
        ), workflow_file

    assert checkout_count > 0
