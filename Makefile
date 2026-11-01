# Groundwork. `make help` lists targets. Two ways to run:
#   make dev                         development (needs Postgres, uv; Node 22 from slice 3)
#   docker compose --profile full up  Docker only: Postgres, API and web in containers
SHELL := /bin/bash
UV ?= uv
BACKEND := backend
PSQL_SUPERUSER ?= psql -d postgres
.DEFAULT_GOAL := help

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

doctor: ## Check prerequisites and print how to install anything missing
	@ok=1; \
	command -v $(UV) >/dev/null || { echo "missing: uv          install: curl -LsSf https://astral.sh/uv/install.sh | sh"; ok=0; }; \
	command -v psql >/dev/null || { echo "missing: Postgres     install: brew install postgresql@16 && brew services start postgresql@16 (or use docker compose)"; ok=0; }; \
	pg_isready -q 2>/dev/null || { echo "not running: Postgres  start it: brew services start postgresql@16 (or: docker compose up -d db)"; ok=0; }; \
	node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>18||(a===18&&b>=18)?0:1)' 2>/dev/null \
	  || echo "web app (slice 3) needs Node >= 18.18:  brew install node@22  (keg-only; does not replace your node)"; \
	command -v docker >/dev/null || echo "optional: Docker, for 'docker compose --profile full up'"; \
	[ -f .env ] || echo "missing: .env           run: make setup"; \
	[ $$ok = 1 ] && echo "doctor: core prerequisites present" || { echo "doctor: fix the items above"; exit 1; }

setup: ## Create .env with fresh dev secrets and install Python dependencies
	@[ -f .env ] || { cp .env.example .env; \
	  sed -i.bak "s|^GROUNDWORK_DEV_HMAC_SECRET=.*|GROUNDWORK_DEV_HMAC_SECRET=$$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')|; s|^GROUNDWORK_ADMIN_TOKEN=.*|GROUNDWORK_ADMIN_TOKEN=$$(python3 -c 'import secrets;print(secrets.token_urlsafe(16))')|" .env && rm -f .env.bak; \
	  echo "created .env (add ANTHROPIC_API_KEY to run the live planner)"; }
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

dev: setup db-setup migrate seed api ## Everything, then the API (web joins in slice 3)

demo: ## Slice-1 demo: chain, gate, critical path, then event A as a run
	cd $(BACKEND) && $(UV) run groundwork demo

demo-offline: ## The same demo straight from the fixture folder, no database
	cd $(BACKEND) && $(UV) run groundwork demo --offline

inspect: ## Validate a site folder: make inspect SITE=path/to/your-site
	cd $(BACKEND) && $(UV) run groundwork inspect $(abspath $(SITE))

test: ## Lint, types, import boundaries and the test suite
	cd $(BACKEND) && $(UV) run ruff check groundwork tests migrations && $(UV) run pyright && $(UV) run lint-imports && $(UV) run pytest

.PHONY: help doctor setup db-setup migrate seed api dev demo demo-offline inspect test
