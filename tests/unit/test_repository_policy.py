"""Regression tests for repository automation policy."""

from __future__ import annotations

import re
import tomllib
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


def test_websocket_minimum_matches_uvicorn_sansio_runtime() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)
    with (PROJECT_ROOT / "uv.lock").open("rb") as lock_file:
        lock = tomllib.load(lock_file)

    docker_requirements = (PROJECT_ROOT / "requirements-docker.txt").read_text(encoding="utf-8")
    optional_dependencies = project["project"]["optional-dependencies"]

    for extra in ("web", "full"):
        websocket_requirements = [
            requirement
            for requirement in optional_dependencies[extra]
            if requirement.startswith("websockets")
        ]
        assert websocket_requirements == ["websockets>=13.0"]

    project_packages = [
        package for package in lock["package"] if package["name"] == "djenis-ai-agent"
    ]
    assert len(project_packages) == 1

    locked_project = project_packages[0]
    locked_requirements = locked_project["metadata"]["requires-dist"]
    for extra in ("web", "full"):
        websocket_requirements = [
            requirement
            for requirement in locked_requirements
            if requirement["name"] == "websockets"
            and requirement.get("marker") == f"extra == '{extra}'"
        ]
        assert websocket_requirements == [
            {
                "name": "websockets",
                "marker": f"extra == '{extra}'",
                "specifier": ">=13.0",
            }
        ]
        resolved_websocket_edges = [
            dependency
            for dependency in locked_project["optional-dependencies"][extra]
            if dependency["name"] == "websockets"
        ]
        assert resolved_websocket_edges == [{"name": "websockets"}]

    locked_websockets = [package for package in lock["package"] if package["name"] == "websockets"]
    assert len(locked_websockets) == 1
    assert tuple(map(int, locked_websockets[0]["version"].split("."))) >= (13, 0)

    assert "websockets>=13.0" in docker_requirements
