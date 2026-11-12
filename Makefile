# NextHire AI Backend - Modular Monolith Makefile
#
# Ported from hgs-backend, which mirrors sp-company-backend's target names so
# muscle memory carries over between all three. The venv path is detected
# (venv/Scripts on Windows, venv/bin on POSIX). `seed` loads demo data rather
# than HGS's CMS export.

# ==========================================
# CONFIGURATION
# ==========================================

PROJECT_NAME := nexthire-backend
APP_PORT := 8002
APP_HOST := localhost

# Windows venvs put executables in Scripts/, POSIX in bin/.
ifeq ($(OS),Windows_NT)
	VENV_BIN := venv/Scripts
	PY_BOOTSTRAP := python
else
	VENV_BIN := venv/bin
	PY_BOOTSTRAP := python3
endif

PY := ./$(VENV_BIN)/python

# ==========================================
# COLORS FOR OUTPUT
# ==========================================

RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m

# ==========================================
# HELP
# ==========================================

.PHONY: help
help: ## Show this help message
	@echo "$(BLUE)NextHire AI Backend - Commands$(NC)"
	@echo "======================================"
	@echo "$(YELLOW)Quick Start:$(NC)"
	@echo "  make setup           # create venv + install dependencies"
	@echo "  cp .env.example .env # then fill in DATABASE_URL and SECRET_KEY"
	@echo "  make db-up           # start MongoDB (docker)"
	@echo "  make run             # start the API on :$(APP_PORT)"
	@echo ""
	@echo "$(YELLOW)Before a PR:$(NC)"
	@echo "  make quick-check     # format, lint, types, security, tests"
	@echo ""
	@echo "$(YELLOW)All Commands:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "$(GREEN)%-22s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ==========================================
# DEVELOPMENT ENVIRONMENT
# ==========================================

.PHONY: setup
setup: ## Setup dev environment (venv + dependencies)
	@echo "$(BLUE)Setting up dev environment...$(NC)"
	@$(PY_BOOTSTRAP) -m venv venv
	@$(PY) -m pip install --upgrade pip
	@$(PY) -m pip install -r requirements.txt
	@echo "$(GREEN)Development environment setup completed$(NC)"
	@echo "$(YELLOW)Next: cp .env.example .env and fill in DATABASE_URL + SECRET_KEY$(NC)"

.PHONY: install
install: ## Install dependencies into an existing venv
	@echo "$(BLUE)Installing dependencies...$(NC)"
	@$(PY) -m pip install --upgrade pip
	@$(PY) -m pip install -r requirements.txt
	@echo "$(GREEN)Dependencies installed$(NC)"

.PHONY: run
run: ## Run the application locally
	@echo "$(BLUE)Starting on http://$(APP_HOST):$(APP_PORT)$(NC)"
	@echo "$(BLUE)API docs: http://$(APP_HOST):$(APP_PORT)/docs$(NC)"
	@$(PY) -m uvicorn src.api.app:app --host 0.0.0.0 --port $(APP_PORT) --reload --log-level info

# ==========================================
# DATABASE
# ==========================================
# MongoDB runs in Docker (docker-compose.yml, service `mongo`, host port 27018).
# There are no migrations: indexes are created on API startup, or by db-indexes.

.PHONY: db-up
db-up: ## Start the MongoDB container
	@docker compose up -d mongo

.PHONY: db-down
db-down: ## Stop the MongoDB container (data is kept in the volume)
	@docker compose stop mongo

.PHONY: db-shell
db-shell: ## Open mongosh inside the container
	@docker compose exec mongo mongosh -u nexthire -p nexthire --authenticationDatabase admin nexthire

.PHONY: db-indexes
db-indexes: ## Create any missing indexes
	@PYTHONPATH=. $(PY) -c "from src.shared.infrastructure.database import ensure_indexes; ensure_indexes()"
	@echo "$(GREEN)Indexes ensured$(NC)"

# ==========================================
# SEED DATA
# ==========================================

.PHONY: seed
seed: ## Load demo sources, jobs and a demo seeker (dev only, idempotent)
	@$(PY) scripts/seed_demo_data.py

.PHONY: seed-dry
seed-dry: ## Show what `make seed` would write, without writing it
	@$(PY) scripts/seed_demo_data.py --dry-run

# IDEMPOTENT and keyed by natural key (email, slug). An existing row is NEVER
# updated — the same rule hgs-backend's seeds follow — so edits made through
# the dashboard survive a re-run.

# ==========================================
# TESTING
# ==========================================

.PHONY: test
test: ## Run all tests
	@$(PY) -m pytest tests/ -v --no-cov

.PHONY: test-unit
test-unit: ## Run unit tests only
	@$(PY) -m pytest tests/unit/ -v --no-cov

.PHONY: test-integration
test-integration: ## Run integration tests only
	@$(PY) -m pytest tests/integration/ -v --no-cov

.PHONY: test-cov
test-cov: ## Run tests with a coverage report and the 80% gate
	@$(PY) -m pytest tests/ --cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=80
	@echo "$(GREEN)Coverage report: htmlcov/index.html$(NC)"

# ==========================================
# CODE QUALITY
# ==========================================

.PHONY: format
format: ## Format code with ruff
	@$(PY) -m ruff format src/ tests/ scripts/ main.py
	@echo "$(GREEN)Code formatted$(NC)"

.PHONY: lint
lint: ## Run ruff check with autofix
	@$(PY) -m ruff check . --fix
	@echo "$(GREEN)Lint complete$(NC)"

.PHONY: typecheck
typecheck: ## Run mypy
	@$(PY) -m mypy src/ scripts/ --ignore-missing-imports

.PHONY: security
security: ## Run bandit security analysis
	@$(PY) -m bandit -r src/ --ini .bandit

.PHONY: quick-check
quick-check: ## Full local gate: format, lint, types, security, tests
	@echo "$(BLUE)[1/5] Format check...$(NC)"
	@$(PY) -m ruff format --check . || (echo "$(RED)Run 'make format'$(NC)"; exit 1)
	@echo "$(BLUE)[2/5] Lint...$(NC)"
	@$(PY) -m ruff check .
	@echo "$(BLUE)[3/5] Type check...$(NC)"
	@$(PY) -m mypy src/ scripts/ --ignore-missing-imports
	@echo "$(BLUE)[4/5] Security...$(NC)"
	@$(PY) -m bandit -r src/ --ini .bandit -q
	@echo "$(BLUE)[5/5] Tests...$(NC)"
	@$(PY) -m pytest tests/ -q --no-cov
	@echo "$(GREEN)ALL CHECKS PASSED$(NC)"

# ==========================================
# HOUSEKEEPING
# ==========================================

.PHONY: clean
clean: ## Clean up temporary files and caches
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage
	@echo "$(GREEN)Cleanup completed$(NC)"
