# Groundwork architecture

The system as built on Nov 4, 2026. The ADRs in `docs/decisions/` say why each choice was made.

## The shape

One Python process (FastAPI) serves the API under `/api` and the built web app, over one Postgres. The same code runs in three places:

- **The Claude plugin,** on the person's laptop. It uses an embedded Postgres under `~/.groundwork`, and Claude in the app is the planner (ADR 0008, ADR 0010).
- **`make dev`,** on a developer's machine, with a local Postgres.
- **The hosted demo,** on one Fly.io machine with a Neon Postgres. It holds only the demo project (ADR 0007, ADR 0009).

What happens when a message arrives:

```
message ─▶ run row ─▶ apply it ─▶ plan ─▶ gateway ─▶ allow: executor (dry run)
                         │          │        │       ask:   wait for a named approval
                         ▼          │        │       deny:  handed to the person
                    forecaster      │        ▼
                  (critical path)   │     ledger (hash chain) ─▶ receipts
                                    ▼        ▲
                              Claude, or a   │
                              written plan   └─ the agent's report is checked against it
```

## The pieces

- **Project data** (`db/models.py`, migrations 0001 to 0007). Orgs, sites (projects), parties, people, items (steps) and their dependencies, events (messages), runs, plans, mandates, actions, decisions, approvals and ledger entries. The tables are relational, and the graph is built in memory per request (ADR 0002).
- **Loader** (`ingest/site_loader.py`). A project is a folder: `site.yaml`, `schedule.csv`, messages and evidence. `groundwork inspect` validates one and lists every problem.
- **Forecaster** (`core/cpm.py`, `service/views.py`). A deterministic critical path on the project's working calendar, with delays as ranges (ADR 0003). `core` imports nothing else from Groundwork.
- **Run pipeline** (`service/pipeline.py`). A played message becomes a `run` row. The run applies the message, plans, decides, executes and reports, then checks the report against the ledger. Each phase commits and appends a step. Runs are background tasks in the same process (ADR 0004).
- **Planners** (`agent/`). Claude makes one structured-output call per plan (ADR 0006). The demo message plays a written plan. In the plugin, Claude in the app plans through Groundwork's tools.
- **Mandate and gateway** (`policy/`). Pure functions that decide allow, ask or deny for each action and cite the mandate clause.
- **Approvals** (`approvals/`). An approval is bound to the action's content hash, the mandate version, the approvers for its kind, and an expiry.
- **Executors** (`executors/`). Dry run only. Each records what it would have sent, under an idempotency key.
- **Ledger** (`ledger/`). Append-only and hash-chained over RFC 8785 canonical JSON. A trigger refuses updates and deletes, and a receipt re-checks one record (`docs/LEDGER.md`).
- **Web app** (`web/`). Vite, React 19, Base Web, react-query and Apache ECharts. Every word it shows lives in `web/copy/` (ADR 0009).
- **Plugin** (`plugin/`, `backend/groundwork/local/`). Skills, an MCP server, drafts the person confirms in the web app, and an outbound guard hook (ADR 0008, ADR 0011).

## Boundaries enforced in code

- Six import contracts run in `make test`. The agent can't reach executors, approvals, the ledger or the database. The gateway can't reach the database, the ledger, a model client or executors.
- Row-level security covers every org-scoped table. The app role owns no tables and has no BYPASSRLS, and a missing org setting returns no rows (ADR 0007).
- Each project is its own org, with its own ledger chain.

## Not built yet

- Sending: everything runs in dry run.
- More than one worker: runs are in-process tasks, swept at start-up if a restart interrupts them.
- Accounts and teams: sign-in is a demo switch on the hosted site and a page token on a laptop.
- Reading PDFs.
