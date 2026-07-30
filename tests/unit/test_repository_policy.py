"""Regression tests for repository automation policy."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKOUT_ACTION = "uses: actions/checkout@"
HARDENED_CHECKOUT_PATTERN = re.compile(
    r"uses: actions/checkout@[^\n]+\n\s+with:\n\s+persist-credentials: false"
)
PUBLIC_ATTRIBUTION_FILES = (
    Path("pyproject.toml"),
    Path("LICENSE"),
    Path("README.md"),
    Path("site/index.html"),
)
SAFE_PERMISSION_TIER = "observe"


def test_dependabot_updates_the_canonical_uv_lockfile() -> None:
    configuration = (PROJECT_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert 'package-ecosystem: "uv"' in configuration
    assert 'package-ecosystem: "pip"' not in configuration


def test_public_metadata_uses_collective_attribution() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)

    assert project["project"]["authors"] == [
        {"name": "Ejupi Labs"},
        {"name": "DjenisAiAgent contributors"},
    ]

    for relative_path in PUBLIC_ATTRIBUTION_FILES:
        content = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

        assert "djenis ejupi" not in content.casefold(), relative_path
        assert "Ejupi Labs" in content, relative_path
        assert "DjenisAiAgent contributors" in content, relative_path

    site = (PROJECT_ROOT / "site/index.html").read_text(encoding="utf-8")
    assert 'href="https://github.com/ejupi-djenis30">' not in site


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


def test_release_quality_gate_runs_the_complete_unit_suite() -> None:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
    )
    verify_commands = "\n".join(
        str(step["run"]) for step in workflow["jobs"]["verify"]["steps"] if "run" in step
    )

    complete_suite_commands = re.findall(
        r"^\s*uv run --frozen --no-sync pytest tests/unit\s*$",
        verify_commands,
        flags=re.MULTILINE,
    )
    assert len(complete_suite_commands) == 1
    assert "tests/unit/test_" not in verify_commands
    assert "verify-windows" in workflow["jobs"]
    assert workflow["jobs"]["candidate"]["needs"] == [
        "verify",
        "verify-windows",
        "release-preflight",
    ]
    windows_commands = "\n".join(
        str(step["run"]) for step in workflow["jobs"]["verify-windows"]["steps"] if "run" in step
    )
    assert "uv run --frozen --no-sync pytest tests/unit" in windows_commands


def test_portable_matrix_does_not_use_a_manual_test_allowlist() -> None:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    commands = "\n".join(
        str(step["run"]) for step in workflow["jobs"]["portable-tests"]["steps"] if "run" in step
    )

    assert "uv run --frozen --no-sync pytest tests/unit" in commands
    assert "tests/unit/test_" not in commands


def test_pre_commit_quality_hooks_match_the_locked_toolchain() -> None:
    configuration = yaml.safe_load(
        (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    with (PROJECT_ROOT / "uv.lock").open("rb") as lock_file:
        lock = tomllib.load(lock_file)

    locked_versions = {package["name"]: package["version"] for package in lock["package"]}
    repositories = {repository["repo"]: repository for repository in configuration["repos"]}

    ruff = repositories["https://github.com/astral-sh/ruff-pre-commit"]
    assert ruff["rev"] == f"v{locked_versions['ruff']}"
    ruff_hooks = {hook["id"]: hook for hook in ruff["hooks"]}
    assert set(ruff_hooks) == {"ruff-check", "ruff-format"}
    assert ruff_hooks["ruff-check"].get("args") == ["--fix"]
    for hook in ruff_hooks.values():
        assert "files" not in hook
        assert "exclude" not in hook

    mypy = repositories["https://github.com/pre-commit/mirrors-mypy"]
    assert mypy["rev"] == f"v{locked_versions['mypy']}"
    mypy_hooks = {hook["id"]: hook for hook in mypy["hooks"]}
    assert set(mypy_hooks) == {"mypy"}
    mypy_hook = mypy_hooks["mypy"]
    assert mypy_hook.get("additional_dependencies") == [
        f"types-Pillow=={locked_versions['types-pillow']}"
    ]
    assert mypy_hook.get("args") == ["src", "scripts"]
    assert mypy_hook.get("pass_filenames") is False
    assert "files" not in mypy_hook
    assert "exclude" not in mypy_hook


def test_make_quality_targets_cover_the_ci_python_scope() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    assert re.search(r"^PYTHON_PATHS\s*:=\s*src tests scripts main\.py$", makefile, re.MULTILINE)
    assert re.search(r"^MYPY_PATHS\s*:=\s*src scripts$", makefile, re.MULTILINE)
    assert re.search(r"^SECURITY_PATHS\s*:=\s*src scripts main\.py$", makefile, re.MULTILINE)
    assert "\t$(RUFF) check $(PYTHON_PATHS)" in makefile
    assert "\t$(RUFF) format $(PYTHON_PATHS)" in makefile
    assert "\t$(RUFF) format --check $(PYTHON_PATHS)" in makefile
    assert "\t$(MYPY) $(MYPY_PATHS)" in makefile
    assert "\t$(BANDIT) -r $(SECURITY_PATHS)" in makefile


def test_make_python_tools_use_the_frozen_locked_environment() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    assert re.search(r"^UV_RUN\s*:=\s*\$\(UV\) run --frozen --no-sync$", makefile, re.MULTILINE)
    for variable, command in (
        ("PYTHON", "python"),
        ("PYTEST", "pytest"),
        ("RUFF", "ruff"),
        ("MYPY", "mypy"),
        ("BANDIT", "bandit"),
        ("PIP_AUDIT", "pip-audit"),
    ):
        assert re.search(rf"^{variable}\s*:=\s*\$\(UV_RUN\) {command}$", makefile, re.MULTILINE)

    assert "\t$(UV) sync --frozen --extra web --extra browser" in makefile
    assert "\t$(UV) sync --frozen --extra full --extra dev" in makefile
    assert "\t$(UV_RUN) pre-commit install" in makefile


def test_local_ci_runs_lock_and_repository_contract_validators() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    assert re.search(r"^ci-local:\s+validate check security test-ci\b", makefile, re.MULTILINE)
    assert "\t$(UV) lock --check" in makefile
    assert "\t$(PYTHON) scripts/validate_site.py" in makefile
    assert "\t$(PYTHON) scripts/validate_release.py" in makefile
    assert re.search(
        r"^validate:\s+lock-check validate-site validate-release\b", makefile, re.MULTILINE
    )


def test_compose_exposes_only_the_hardened_loopback_gateway() -> None:
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    networks = compose["networks"]

    agent = services["djenis-agent"]
    assert "ports" not in agent
    assert set(agent["networks"]) == {"djenis-control"}
    assert networks["djenis-control"]["internal"] is True

    gateway = services["gateway"]
    assert gateway["image"] == (
        "nginxinc/nginx-unprivileged:1.30.0-alpine@sha256:"
        "808f7846d21a9c94cf53833e8807a00a33fd0b65cc47fb05b79efe366c2d201f"
    )
    assert gateway["read_only"] is True
    assert gateway["cap_drop"] == ["ALL"]
    assert gateway["security_opt"] == ["no-new-privileges:true"]
    assert gateway["ports"] == ["127.0.0.1:8008:8080"]
    assert set(gateway["networks"]) == {"djenis-control", "console-ingress"}
    assert "./deploy/nginx.conf:/etc/nginx/nginx.conf:ro" in gateway["volumes"]

    host_facing_services = {name for name, service in services.items() if "ports" in service}
    assert host_facing_services == {"gateway"}


def test_permission_tier_defaults_and_operator_documentation_stay_safe() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    env_defaults = re.findall(
        r'^DJENIS_PERMISSION_TIER="(?P<tier>[^"]+)"$',
        env_example,
        flags=re.MULTILINE,
    )
    image_defaults = re.findall(
        r"^\s*DJENIS_PERMISSION_TIER=(?P<tier>[^\s\\]+)\s*\\?$",
        dockerfile,
        flags=re.MULTILINE,
    )
    documentation_defaults = re.findall(
        r"^\| `DJENIS_PERMISSION_TIER` \| `(?P<tier>[^`]+)` \|",
        readme,
        flags=re.MULTILINE,
    )

    assert env_defaults == [SAFE_PERMISSION_TIER]
    assert image_defaults == [SAFE_PERMISSION_TIER]
    assert documentation_defaults == [SAFE_PERMISSION_TIER]

    defaults = {
        ".env.example": env_defaults[0],
        "Dockerfile": image_defaults[0],
        "docker-compose.yml": compose["services"]["djenis-agent"]["environment"][
            "DJENIS_PERMISSION_TIER"
        ],
        "README.md": documentation_defaults[0],
    }
    assert defaults == {
        ".env.example": SAFE_PERMISSION_TIER,
        "Dockerfile": SAFE_PERMISSION_TIER,
        "docker-compose.yml": "${DJENIS_PERMISSION_TIER:-observe}",
        "README.md": SAFE_PERMISSION_TIER,
    }

    readiness_check = "Invoke-RestMethod http://127.0.0.1:8008/ready"
    compose_json = "docker compose config --format json"
    exact_default_pattern = (
        r"""Select-String -Pattern '^\s*"DJENIS_PERMISSION_TIER":\s*"""
        r""""(?<tier>[^"]+)"[,]?\s*$'"""
    )
    inspect_container = 'docker inspect --format "{{json .Config.Env}}" djenis-agent'
    elevation = '$env:DJENIS_PERMISSION_TIER = "interact"'
    reset = '$env:DJENIS_PERMISSION_TIER = "observe"'
    recreate = (
        "docker compose up -d --no-deps --force-recreate --wait --wait-timeout 120 djenis-agent"
    )
    assert readme.index(readiness_check) < readme.index(compose_json)
    assert readme.index(compose_json) < readme.index(elevation)
    assert readme.index(elevation) < readme.index(reset)
    assert readme.count(recreate) == 2
    assert readme.count(readiness_check) == 3
    assert readme.count(compose_json) == 2
    assert readme.count(exact_default_pattern) == 2
    assert "ConvertFrom-Json -AsHashtable" not in readme
    assert readme.count(inspect_container) == 2
    assert readme.count("$LASTEXITCODE -ne 0") >= 6
    assert readme.count('$containerTier -ne "DJENIS_PERMISSION_TIER=') == 2
    assert "Select-String -SimpleMatch" not in readme
    assert readme.count("Remove-Item Env:DJENIS_PERMISSION_TIER") == 2
    assert "retains its tier across agent, Docker daemon, and host restarts" in readme
    assert "Readiness is checked after the new agent starts" in readme
    assert "assume that the `interact` container\nis still active and run the reset block" in readme
    assert "one-session" not in readme
    assert "defaults to `interact`" not in readme


def test_compose_pins_ollama_and_the_effective_context_contract() -> None:
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    ollama_image = (
        "ollama/ollama:0.32.4@sha256:"
        "10c13eb515db310990527d36ca14a136da4bcc0fbf2bf3b15e9c1f111e9d3cd4"
    )

    assert services["ollama"]["image"] == ollama_image
    assert services["ollama-provision"]["image"] == ollama_image
    assert services["ollama"]["environment"]["OLLAMA_NO_CLOUD"] == "1"
    assert services["djenis-agent"]["environment"]["DJENIS_LOCAL_LLM_CONTEXT_TOKENS"] == (
        "${DJENIS_LOCAL_LLM_CONTEXT_TOKENS:-65536}"
    )


def test_gateway_nginx_routes_each_transport_with_bounded_buffering() -> None:
    configuration_path = PROJECT_ROOT / "deploy" / "nginx.conf"
    assert configuration_path.is_file()
    configuration = configuration_path.read_text(encoding="utf-8")

    def location(selector: str) -> str:
        match = re.search(
            rf"^        location {re.escape(selector)} \{{\n(?P<body>.*?)^        \}}$",
            configuration,
            re.MULTILINE | re.DOTALL,
        )
        assert match is not None, f"missing Nginx location: {selector}"
        return match.group("body")

    root = location("/")
    websocket = location("= /ws")
    stream = location("= /stream")
    transcription = location("= /api/transcribe")

    assert "client_max_body_size 6m;" in configuration
    assert "proxy_pass http://djenis_agent;" in root
    assert 'proxy_set_header Upgrade "";' in root
    assert 'proxy_set_header Connection "";' in root

    assert "proxy_pass http://djenis_agent;" in websocket
    assert "proxy_set_header Upgrade $http_upgrade;" in websocket
    assert "proxy_set_header Connection $connection_upgrade;" in websocket
    assert "proxy_buffering off;" in websocket

    assert "proxy_pass http://djenis_agent;" in stream
    assert "proxy_buffering off;" in stream
    assert "proxy_cache off;" in stream
    assert "gzip off;" in stream

    assert "proxy_pass http://djenis_agent;" in transcription
    assert "proxy_request_buffering off;" in transcription
    assert "proxy_buffering off;" in transcription
