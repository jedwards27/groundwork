# Groundwork. `make help` lists targets. Two ways to run:
#   make dev                         development (needs Postgres, uv and Node 20+)
#   sh scripts/new-env.sh && docker compose --profile full up --build
#                                     Docker only: Postgres, API and Mission Control in containers
SHELL := /bin/bash
UV ?= uv
BACKEND := backend
PSQL_SUPERUSER ?= psql -d postgres
NPM ?= npm
.DEFAULT_GOAL := help

help: ## List targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

doctor: ## Check prerequisites and print how to install anything missing
	@ok=1; \
	command -v $(UV) >/dev/null || { echo "missing: uv          install: curl -LsSf https://astral.sh/uv/install.sh | sh"; ok=0; }; \
	command -v psql >/dev/null || { echo "missing: Postgres     install: brew install postgresql@16 && brew services start postgresql@16 (or use docker compose)"; ok=0; }; \
	pg_isready -q 2>/dev/null || { echo "not running: Postgres  start it: brew services start postgresql@16 (or: docker compose up -d db)"; ok=0; }; \
	node -e 'process.exit(Number(process.versions.node.split(".")[0])>=20?0:1)' 2>/dev/null \
	  || { echo "missing: Node 20+ (for Mission Control; you have $$(node --version 2>/dev/null || echo none))  install: Node 22 LTS from https://nodejs.org or nvm install 22"; ok=0; }; \
	command -v docker >/dev/null || echo "optional: Docker, for 'docker compose --profile full up'"; \
	[ -f .env ] || echo "missing: .env           run: make setup"; \
	[ $$ok = 1 ] && echo "doctor: core prerequisites present" || { echo "doctor: fix the items above"; exit 1; }

setup: ## Create .env with fresh dev secrets and install Python dependencies
	@sh scripts/new-env.sh
	cd $(BACKEND) && $(UV) sync

db-setup: ## Create the owner and app roles and the databases (local Postgres superuser)
	$(PSQL_SUPERUSER) -v ON_ERROR_STOP=1 -f scripts/db-setup.sql

migrate: ## Apply migrations to the dev and test databases
	cd $(BACKEND) && $(UV) run alembic upgrade head
	cd $(BACKEND) && $(UV) run alembic -x url=$$($(UV) run python -c 'from groundwork.config import get_settings as g; print(g().test_database_owner_url)') upgrade head

seed: ## Load the Lake Mariner fixture (replaces the demo org's data)
	cd $(BACKEND) && $(UV) run groundwork seed

api: ## Run the API on :8000
	cd $(BACKEND) && $(UV) run groundwork serve --reload

web-install: ## Install the web app's dependencies (Node 20+)
	cd web && $(NPM) ci --no-fund --no-audit

web: ## Run Mission Control on :3000 (needs the API on :8000)
	cd web && NEXT_TELEMETRY_DISABLED=1 $(NPM) run dev

web-build: ## Production build of Mission Control (also type-checks it)
	cd web && NEXT_TELEMETRY_DISABLED=1 $(NPM) run typecheck && NEXT_TELEMETRY_DISABLED=1 $(NPM) run build

e2e: ## Browser walkthrough of the demo against the real API (starts servers if needed; uses installed Chrome)
	cd web && $(NPM) run e2e

types: ## Regenerate web/openapi.json and the web client's types from the API
	cd $(BACKEND) && $(UV) run python -c "import json; from groundwork.api.app import app; print(json.dumps(app.openapi(), indent=1))" > ../web/openapi.json
	cd web && $(NPM) run types

dev: setup db-setup migrate seed web-install ## Everything: API on :8000 and Mission Control on :3000
	@echo "API http://localhost:8000/docs · Mission Control http://localhost:3000"
	@trap 'kill 0' EXIT; (cd $(BACKEND) && $(UV) run groundwork serve) & (cd web && NEXT_TELEMETRY_DISABLED=1 $(NPM) run dev) & wait

demo: ## Slice-1 demo: chain, gate, critical path, then event A as a run
	cd $(BACKEND) && $(UV) run groundwork demo

demo-offline: ## The same demo straight from the fixture folder, no database
	cd $(BACKEND) && $(UV) run groundwork demo --offline

inspect: ## Validate a site folder: make inspect SITE=path/to/your-site
	cd $(BACKEND) && $(UV) run groundwork inspect $(abspath $(SITE))

test: ## Lint, types, import boundaries and the test suite
	cd $(BACKEND) && $(UV) run ruff check groundwork tests evals migrations && $(UV) run pyright && $(UV) run lint-imports && $(UV) run pytest

.PHONY: help doctor setup db-setup migrate seed api web web-install web-build e2e types dev demo demo-offline inspect test
