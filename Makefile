.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PYTHON      := python
PIP         := pip
PYTEST      := pytest
RUFF        := ruff
MYPY        := mypy
DOCKER      := docker
COMPOSE     := docker compose
IMAGE_NAME  := djenis-ai-agent
IMAGE_TAG   := latest

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
.PHONY: help
help: ## Show this help message
	@echo ""
	@echo "DjenisAiAgent — available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
.PHONY: install
install: ## Install core + web + browser dependencies
	$(PIP) install -e ".[web,browser]"

.PHONY: install-dev
install-dev: ## Install all dependencies including dev tools
	$(PIP) install -e ".[full,dev]"

.PHONY: install-pre-commit
install-pre-commit: ## Install pre-commit hooks
	pre-commit install

# ---------------------------------------------------------------------------
# Code Quality
# ---------------------------------------------------------------------------
.PHONY: lint
lint: ## Run ruff linter
	$(RUFF) check src/ tests/ main.py

.PHONY: format
format: ## Auto-format code with ruff
	$(RUFF) format src/ tests/ main.py

.PHONY: format-check
format-check: ## Check formatting without modifying files
	$(RUFF) format --check src/ tests/ main.py

.PHONY: type-check
type-check: ## Run mypy type checker
	$(MYPY) src/ --ignore-missing-imports

.PHONY: check
check: lint format-check type-check ## Run all code quality checks

.PHONY: security-bandit
security-bandit: ## Run Bandit security scan
	bandit -r src/

.PHONY: security-deps
security-deps: ## Run dependency vulnerability audit
	pip-audit

.PHONY: security
security: security-bandit security-deps ## Run all security checks

.PHONY: ci-local
ci-local: check security test-ci ## Run the main CI checks locally

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
.PHONY: test
test: ## Run unit tests
	$(PYTEST) tests/unit/ -v

.PHONY: test-all
test-all: ## Run all tests (unit + integration)
	$(PYTEST) tests/ -v

.PHONY: test-cov
test-cov: ## Run unit tests with coverage report
	$(PYTEST) tests/unit/ --cov=src --cov-report=term-missing --cov-report=html

.PHONY: test-ci
test-ci: ## Run tests in CI mode (no integration, with coverage)
	$(PYTEST) tests/unit/ -m "not integration" --cov=src --cov-report=xml -q

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
.PHONY: run
run: ## Run the agent in CLI mode (set COMMAND env var)
	$(PYTHON) main.py --command "$(COMMAND)"

.PHONY: run-web
run-web: ## Start the web server (port 8000)
	$(PYTHON) main.py --web

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
.PHONY: docker-build
docker-build: ## Build the Docker image
	$(DOCKER) build -t $(IMAGE_NAME):$(IMAGE_TAG) .

.PHONY: docker-run
docker-run: ## Run the container in web mode
	$(DOCKER) run --rm -p 8000:8000 \
		--env-file .env \
		$(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: docker-up
docker-up: ## Start all services with docker compose
	$(COMPOSE) up --build

.PHONY: docker-down
docker-down: ## Stop and remove docker compose services
	$(COMPOSE) down

.PHONY: docker-logs
docker-logs: ## Tail docker compose logs
	$(COMPOSE) logs -f

.PHONY: docker-clean
docker-clean: ## Remove built images and stopped containers
	$(DOCKER) image rm $(IMAGE_NAME):$(IMAGE_TAG) 2>/dev/null || true
	$(DOCKER) container prune -f

# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------
.PHONY: clean
clean: ## Remove Python bytecode, caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/ .coverage coverage.xml dist/ build/ *.egg-info

.PHONY: clean-all
clean-all: clean docker-clean ## Remove everything including Docker artifacts
