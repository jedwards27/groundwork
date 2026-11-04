# 0001. Python API and worker, Next.js web, one OpenAPI contract

**Status:** accepted (Nov 1, 2026; decided by Jude). Settles ARCHITECTURE §4 and §2.7. The Next.js half is superseded by ADR 0009 (one Vite app, served by the API).

**Context.** Two languages were on the table: TypeScript end to end, or a Python backend with a Next.js front end. The backend's hardest code is scheduling math, extraction and evals, all of which Python does well; the front end is a port of the prototype's control room, which React does well. The risk of two languages is the shared contract (mandate, action, plan, ledger entry) drifting between them.

**Options.** (a) TypeScript everywhere: one toolchain, shared types for free, weaker for data and evals. (b) Python backend + Next.js: best tool per side, contract must be generated. (c) Python everywhere with server-rendered HTML: one language, loses the prototype's interactive UI.

**Decision.** (b). FastAPI, pydantic v2, SQLAlchemy 2 with psycopg 3 (synchronous; asyncpg was dropped because transaction-local `set_config` for row-level security is simpler to get right synchronously), Alembic, networkx for graph traversal. The contract is the set of pydantic models in `backend/groundwork/schemas/`; FastAPI publishes them in `/openapi.json`; the web client is generated from that document with openapi-typescript and openapi-fetch. Code layout makes the safety boundary visible: `groundwork.core` imports nothing else from the project, and import-linter enforces it in `make test` (more contracts arrive with slice 2: the planner has no import path to executors, ingestion has none to approvals).

**Consequences.** Two toolchains, so `make doctor` checks for both and the Docker profile hides them from someone who only wants to run it. A generated-types freshness check joins `make test` in slice 3. Evals and extraction live in the language best suited to them from the start.
