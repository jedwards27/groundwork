# Groundwork

An owner's coordination agent for large, paperwork-constrained builds, starting with gigawatt data centers. It keeps the live **paper critical path** to a delivery milestone, forecasts slips with their sources shown, and (from slice 2) acts within an explicit grant of authority, with every action in an append-only ledger.

The demo site is **Lake Mariner CB-5** (Barker, NY), seen from the **end user's** seat: TeraWulf is landlord and interconnection customer, Fluidstack is the lessee, and Anthropic is the end user two contracts removed from the utility. Public facts carry links; everything else is marked synthetic or an assumption to verify.

Start with `CLAUDE.md` (the brief), then `docs/ARCHITECTURE.md`, `docs/TECH-DESIGN-DISCUSSION.md` and `docs/decisions/`.

## Status

| Slice | What | State |
|---|---|---|
| 1 | Schema, fixture, critical-path and forecast engine, API, CLI demo | **Done** |
| 2 | Mandate, gateway, ledger, approvals, planners (informed and blind arms), reports, evals | **Done** (live Claude path tested against a fake client only) |
| 3 | Mission Control web app ported from `prototype/index.html`, browser walkthrough, web container | **Done** (Docker profile not yet run: no Docker on the author's machine) |
| Hosting | Fly.io and Neon config, bootstrap, preflight, nightly reset, local rehearsal | **Ready to deploy** (not yet deployed: needs your Fly and Neon accounts) |
| 4+ | Email and PDF connectors with extraction, approvals UX, notifications, second site | Later |

## Run it

**Prerequisites:** Postgres 14+ running locally, [uv](https://docs.astral.sh/uv/), and Node 20 or newer (22 LTS recommended, from nodejs.org or `nvm install 22`) for the web app. `make doctor` checks all three and prints install commands.

```bash
make doctor
```
```bash
make dev
```

`make dev` creates `.env` with fresh dev secrets, creates the two database roles and databases (`scripts/db-setup.sql`, run as your local Postgres superuser), applies migrations, seeds Lake Mariner, installs the web app's packages, and serves the API on http://localhost:8000 (OpenAPI docs at `/docs`) and **Mission Control on http://localhost:3000**. Ctrl-C stops both.

**Docker only.** The first command writes `.env` with fresh secrets and needs only a shell. The containers are written but not yet run, because the author's machine has no Docker; the same production server passes the browser walkthrough outside Docker.

```bash
sh scripts/new-env.sh
```
```bash
docker compose --profile full up --build
```

Every port binds to 127.0.0.1, so nothing is reachable from your network.

**Hosted demo.** Two Fly.io machines and a free Neon Postgres, for about $7 a month. Every visitor gets a private sandbox copy of the demo, kept apart by the same org isolation that separates customers. `docs/HOSTING.md` has every step. `make rehearse-hosted` runs the hosted profile on your machine first, against a throwaway Postgres set up the way Neon's is. Not yet deployed: it needs your Fly and Neon accounts.

```bash
make hosted-bootstrap
```
```bash
make deploy
```

Set `ANTHROPIC_API_KEY` in `.env` to use the live planner (Opus 5.5 plans, Haiku 5.5 classifies outbound text and writes the post-execution report). Without it, everything runs on the hand-written simulated planner, under a banner that says so. Live planning is capped per day (`GROUNDWORK_DAILY_LIVE_RUN_CAP`). `docs/DATA-BOUNDARY.md` lists what is sent.

## Mission Control

Open http://localhost:3000 and pick a demo persona: Dana Ortiz (delivery lead, approver), Priya Raman (counsel, approver) or Sam Okafor (commissioning, viewer). Personas are fictional people seeded with the fixture; anyone using the app can act as any of them, which is why demo login is a switch (`GROUNDWORK_DEMO_LOGIN`) and off for real data. Then:

1. **Read the top of the page.** The countdown, the gating item with its owner and float, and the holidays hidden inside critical-path waits. "Open the status report" shows the source document.
2. **Play event A** from the inbox. Steps stream in as the run works. The countdown moves, and the differential shows four bars: unmitigated, with what ran, if you approve the queue, and the hatched "if the landlord agrees" bar.
3. **Read the plan.** What the agent did alone, what it asked a person, what it refused. One row says "Gateway held this": the agent wanted to act alone and the mandate said ask.
4. **Play the auto-reply** ("approved, please proceed"). The held action stays pending.
5. **Approve it as Dana.** The dialog shows exactly what is being approved and the hash it binds to. It runs in dry run, and the row records who approved it and when.
6. **Move the authority dial.** The compare table shows the same plan under each preset; issuing a new mandate re-decides only open actions.
7. **Check the ledger.** "Chain verified". Then "Tamper with one entry" (local only) and watch verification and the attestation fail. "Reset site" restores the fixture.

## The CLI demo

```bash
make demo
```

It reseeds the site, then prints the same story as text:

1. **The countdown.** CB-5 delivers in 107 days (forecast Wed Feb 17, 2027, against the Feb 22 target), with 3 business days of float. Only the outline is public: TeraWulf says CB-5's first data hall begins energizing in very early January and phased delivery begins in early 2027. The fixture energizes on Jan 6, at the end of NYSEG's witness test, and infers the delivery date from CB-4's pace of about six weeks from start-up to L4.
2. **The gating item, computed.** NYSEG's acceptance of the protection settings, due Dec 4. Critical path: settings acceptance, witness test, L3 start-up, L4 functional test.
3. **What's hidden in the calendar.** Christmas Eve and Christmas Day fall inside the 15-business-day notice NYSEG needs between acceptance and the witness test, Thanksgiving inside NYSEG's review and New Year's Day inside the witness test; each holiday pushes delivery a working day. Everything else feeding the witness test (cut-in certificate, L2, metering) has 17 or more business days of float, so NYSEG's review is the one thing that matters this month.
4. **The paper chain**, 26 items by party with planned and forecast dates, and the reference set behind the forecast ("no comparable items yet" for the gate, and why).
5. **Event A played as a run.** The landlord, via the lessee, forwards NYSEG's revised short-circuit data: the coordination study must be re-run and re-reviewed. Delivery moves to Tue Apr 13, 2027 (range Mar 29 to Apr 28), 50 days late, and the forecast names both legs.

Then the slice-2 beats:

6. **The plan, decided by the gateway.** Eight actions in the end user's seat. Five run alone in dry run, including engaging the end user's own engineer against an $18,500 quote within the $50,000 limit. Three wait for a person: the state escalation, the legal draft for counsel, and the request that the landlord ask NYSEG for staged energization, which the planner proposed to send alone and the gateway **held**. Delivery recovers 0 days on the end user's own actions and **14 days if the landlord agrees**, computed by the scheduler, never by the model.
7. **An auto-reply says "approved, please proceed".** It is linked to the pending request and changes nothing.
8. **A named person approves.** Dana approves the held request; it runs in dry run, and the approval is bound to the action's hash and the mandate version.
9. **The ledger.** `verify_chain` passes; then someone with owner credentials disables the trigger and edits one decision, and verification fails on that entry.
10. **The attestation.** Genesis to head, zero violations, HMAC-signed with the dev key, with a list of what it does not prove.

`make demo-offline` prints the slice-1 part from the fixture folder with no database. Event B (`groundwork demo --event event-b`) shows the $250,000 expedite payment refused by the never-list.

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

## Evals

```bash
cd backend && uv run python -m evals.run
```

Plays 6 event templates under the 3 mandate presets in both arms (with and without the mandate in the prompt) and runs the real gateway over every plan. It reports hard violations, over-reach (held) and over-caution, honest reporting against the ledger including a withheld-row check, plan quality against a reviewed set, and injection resistance. `--live --repeat 3` runs Claude (about 430 decisions per arm, about $25 per model version). Definitions are in `backend/evals/README.md`.

Simulated planner, Nov 1, 2026 (both arms identical because the simulated planner ignores the mandate; precision@3 is 1.0 by construction because the reviewed set was written from the same plans):

| Metric | Value |
|---|---|
| Hard violations (auto on pay, sign, delete) | 0 |
| Over-reach rate (held by the gateway) | 3.5% |
| Over-caution rate | 0.7% |
| Reports matching the ledger | 100% |
| Fabrication when a ledger row is withheld | 0% |
| Injection cases resisted | 6 of 6 |

The live Claude numbers, per arm and model version, go here once a key is used.

## Cost

Measured prompt: about 6,400 cached tokens per site plus about 600 per event. Assuming about 6,000 output tokens per plan:

| | Per event | Per site per month | 15 sites per month |
|---|---|---|---|
| 5 events a day | $0.28 | $42 | $630 |
| 20 events a day | $0.28 | $167 | $2,500 |

Opus 5.5 planning in both arms (the blind arm reads the informed arm's cache), Haiku 5.5 for classification and reports. `cd backend && uv run groundwork cost` reports actual spend from recorded usage.

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
```bash
make e2e
```

Lint (ruff), types (pyright), six import boundaries (import-linter: the planner cannot reach executors, approvals, the ledger or the database; ingestion cannot create approvals) and the test suite. It covers:

- the calendar and scheduler, and golden tests on the fixture;
- 172 gateway table rows;
- the ledger: test vector, tamper and delete detection, triggers that bind the owner, no forks under concurrency;
- the honesty check;
- the pipeline end to end, and typed, bound approvals;
- a property test that no inbound message changes any action's state;
- mandate re-decision, and blind-arm isolation;
- the Claude planner, classifier and reporter against a fake client;
- the eval harness, row-level security, and a check that the generic engine contains no data-center vocabulary;
- that `web/openapi.json` matches the API, so the web app's generated types cannot drift;
- the hosted profile:
  - the startup preflight that refuses development secrets;
  - daily caps that count across orgs;
  - connection-per-request mode and the nightly reset schedule;
  - that no database role needs BYPASSRLS;
- sandboxes: two visitors cannot see each other's work, switching persona keeps a sandbox, "Start over" replaces it, and expired sandboxes are deleted with their ledgers.

`make e2e` is the browser walkthrough (Playwright, `web/e2e/`): sign in as a persona, play event A, check that the countdown and the did/asked/refused counts on the page equal what the API returns, play the auto-reply and see nothing change, approve the held action as Dana, check that a viewer cannot approve (in the page and at the API), then tamper, watch verification fail, and reset. With sandboxes on, as in the hosted profile, a second browser checks that two visitors cannot see each other's work. It uses your installed Google Chrome and starts the API and web app if they are not running. `make web-build` type-checks and builds the production web app.

## Docs

- `docs/decisions/`: ADRs 0001 to 0007.
- `docs/HOSTING.md`: deploying, checking and running the hosted demo.
- `docs/LEDGER.md`: the ledger's hash format, a test vector, and what verification does and does not catch.
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
