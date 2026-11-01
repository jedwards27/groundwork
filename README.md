# Groundwork

An owner's coordination agent for large, paperwork-constrained builds, starting with gigawatt data centers. It keeps the live **paper critical path** to a delivery milestone, forecasts slips with their sources shown, and (from slice 2) acts within an explicit grant of authority, with every action in an append-only ledger.

The demo site is **Lake Mariner CB-5** (Barker, NY), seen from the **end user's** seat: TeraWulf is landlord and interconnection customer, Fluidstack is the lessee, and Anthropic is the end user two contracts removed from the utility. Public facts carry links; everything else is marked synthetic or an assumption to verify.

Start with `CLAUDE.md` (the brief), then `docs/ARCHITECTURE.md`, `docs/TECH-DESIGN-DISCUSSION.md` and `docs/decisions/`.

## Status

| Slice | What | State |
|---|---|---|
| 1 | Schema, fixture, critical-path and forecast engine, API, CLI demo | **Done** |
| 2 | Mandate, gateway, ledger, approvals, planners (informed and blind arms), reports, evals | Next |
| 3 | Mission Control web app ported from `prototype/index.html` | After slice 2 |
| 4+ | Email and PDF connectors with extraction, approvals UX, notifications, second site | Later |

## Run it

**Prerequisites:** Postgres 14+ running locally, and [uv](https://docs.astral.sh/uv/). `make doctor` checks and prints install commands. Node 22 is needed only for the web app (slice 3).

```bash
make doctor
```
```bash
make dev
```

`make dev` creates `.env` with fresh dev secrets, creates the two database roles and databases (`scripts/db-setup.sql`, run as your local Postgres superuser), applies migrations, seeds Lake Mariner and serves the API on http://localhost:8000 (OpenAPI docs at `/docs`).

**Docker only** (not yet exercised on the author's machine, which has no Docker):

```bash
docker compose --profile full up
```

Set `ANTHROPIC_API_KEY` in `.env` to use the live planner when slice 2 lands. Without it, everything still runs.

## The slice-1 demo

```bash
make demo
```

It reseeds the site, then prints:

1. **The countdown.** CB-5 delivers in 66 days (forecast Thu Jan 7, 2027, against the Jan 12 target), with 3 business days of float.
2. **The gating item, computed.** NYSEG's acceptance of the protection settings, due Nov 13. Critical path: settings acceptance, witness test, L3 start-up, L4 functional test.
3. **What's hidden in the calendar.** Thanksgiving and the day after fall inside the 15-business-day notice NYSEG needs between acceptance and the witness test; each holiday pushes delivery a working day. Near-critical items (cut-in certificate, L2, metering) are listed with their float.
4. **The paper chain**, 26 items by party with planned and forecast dates, and the reference set behind the forecast ("no comparable items yet" for the gate, and why).
5. **Event A played as a run.** The landlord, via the lessee, forwards NYSEG's revised short-circuit data: the coordination study must be re-run and re-reviewed. Delivery moves to Mon Mar 1, 2027 (range Feb 15 to Mar 16), 48 days late, and the forecast names both legs.

`make demo-offline` prints the same from the fixture folder with no database.

To watch it through the API, mint a token and call it:

```bash
TOKEN=$(cd backend && uv run groundwork token dana)
```
```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/sites/lake-mariner/critical-path
```
```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"event":"event-a"}' localhost:8000/sites/lake-mariner/events
```

## Load your own site

A site is a folder: `site.yaml` (site, milestone, parties with roles and routing), `schedule.csv` (one row per item; predecessors in one column, e.g. `to_accept FS+15bd; meter`), optional `events.yaml`, `evidence/`, `inbox/` and `reference_projects.csv`. `fixtures/lake-mariner/` is the template and its README explains each file.

```bash
make inspect SITE=path/to/your-site
```

It validates the folder, lists every problem at once if there are any, and otherwise prints the gate, critical path, holiday losses and forecast, plus any sequencing rule your schedule breaks. Loading it into the database is `cd backend && uv run groundwork seed path/to/your-site`. Email and PDF ingestion arrive in slice 4.

## Test

```bash
make test
```

Lint (ruff), types (pyright), import boundaries (import-linter) and the test suite: the calendar and scheduler, golden tests on the fixture (computed gate, both events, holiday loss), loader error reporting, signed tokens, row-level security (the app role sees nothing without an org and nothing of another org), the API end to end, and a check that the generic engine contains no data-center vocabulary.

## Docs

- `docs/decisions/`: ADRs 0001 to 0004 so far.
- `docs/PRACTITIONER-QUESTIONS.md`: the 20 questions that confirm or correct the fixture's assumptions.
- `docs/DATA-BOUNDARY.md`: exactly what leaves your machine.
- `docs/reviews/`: three rounds of plan review that shaped this design.

## Stop-ship list

The prototype is not submitted while any of these holds:

- A practitioner says the gating item is wrong.
- The live planner proposes a never-list action that only the content classifier catches.
- The hosted box exposes the dev signing secret or a token.
- `verify_chain()` fails on the hosted ledger.
- The stranger's export test has not been attempted.
