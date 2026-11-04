# Groundwork

Groundwork is an agent that chases what a project waits on from other organizations: utilities, permit offices, landlords and vendors. It acts only inside a written mandate, and every step it takes lands in a ledger anyone can check. Its first market is data-center construction.

It reads a project's paper trail (utility studies, permits, landlord decisions, vendor tests), names what sets the finish date this week, forecasts slips with their sources, and drafts, chases and asks within the mandate. Five parts keep it inside its authority:
- The mandate says what it may do alone, what it must ask about, and what it may never do.
- The gateway, code outside the model, decides allow, ask or deny for each action and shows the clause it relied on.
- A named approval binds one person to one exact action.
- The ledger records every step in a hash chain, so when a date is disputed it shows who was asked for what, and when.
- A receipt lets anyone re-check one ledger record by its hash.

**What's real and what's simulated.**
- Real: the gateway, the ledger and receipts, the forecaster, approvals, the check of the agent's report against the ledger, and row-level security.
- Simulated: sending (everything runs in dry run, so nothing is sent), the demo's hand-written plan, and the demo's people, schedule and email, which are synthetic.
- Claude writes the plans in the plugin, or when you add your own API key.

The demo site is **Lake Mariner CB-5** (Barker, NY), seen from the end user's seat: TeraWulf is landlord and the utility's customer, Fluidstack is the lessee, and the end user, an AI company, reaches the utility only through both. Public facts carry links; the schedule, inbox and people are synthetic and labeled.

**Try it now:** https://groundwork-demo.fly.dev. Click **Start the tutorial** for a two-minute tour; there is no account to create. To run it yourself, see [Run it locally](#run-it-locally) (`make doctor`, then `make dev`) or the plugin below.

## Try it in the Claude app (the plugin)

The main way to try Groundwork is as a plugin inside the Claude app. It runs on your computer, uses the connectors you already have, and needs no API key: Claude in the app writes the plans, and Groundwork's gateway, which is code outside the model, decides allow, ask or deny for each action.

**You need:** [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). The first launch takes about a minute while uv fetches Python 3.12 and an embedded Postgres; later launches take seconds.

1. **Get the plugin:** download [groundwork-plugin.zip](https://github.com/jedwards27/groundwork/releases/latest/download/groundwork-plugin.zip) from the [latest release](https://github.com/jedwards27/groundwork/releases/latest), or build it with `make plugin` (writes `dist/groundwork-plugin.zip`; needs Node 20 or newer).
2. **Install it in one of two places:**
   - **The Claude desktop app (Cowork):** Customize, then Plugins, then upload the zip.
   - **Claude Code:** run `unzip groundwork-plugin.zip`, then `claude --plugin-dir groundwork-plugin`.
3. **Set up and play:** run `/groundwork:setup` to say who you are, then `/groundwork:demo` for the two-minute demo.

**Setting it up with an agent?** Check that `uv` is installed, download and unzip the release zip, and then hand back to the person: they upload the zip in the Claude desktop app, or start Claude Code with `--plugin-dir`. A running session can't load a plugin into itself.

You approve asks, confirm drafts and check receipts in the Groundwork app: the same web app as the hosted demo, served on your computer. Claude gives you its link, which signs you in; the app answers only on your computer. Other skills:
- `/groundwork:new-project` starts tracking one of your own projects from a few sentences, a spreadsheet or your email.
- `/groundwork:mandate` writes or changes a mandate in plain words.
- The `coordinate` skill handles "what are we waiting on?" and checking project mail.

**Changing a project.** Open its **Steps** tab to see every step, done and cancelled ones included. To change one, ask Claude: it drafts the change with `edit_steps` (add, change, mark cancelled or remove steps) or `edit_project` (name, finish, parties), and you confirm it on your home page. To get a project out of the way, archive it: it leaves your home page and mail routing, and nothing is deleted. Delete removes it for good, after you type its key; a line in `~/.groundwork/deleted.jsonl` keeps its ledger's last hash. A project's **Settings** tab holds its mandate, its name, its facts, receipts (check any ledger record), and Archive, Restore and Delete. To cancel a step yourself, use **Cancel** on its row in the Steps tab; **Restore** undoes it. ADR 0011 covers the design.

**When people are on two projects.** Mail goes to the project whose email thread it continues, then to the project whose people sent or received it. If those people are on more than one project, it goes to the one whose name the message mentions; otherwise Claude asks you. Starting a project warns when its people or parties are already on another one.

Everything stays in dry run. If Claude tries to send project mail through another connector, Groundwork's guard records it and holds it; your other use of Gmail or Slack is untouched.

**Updating.** Install the new zip the same way. If the update changes the Lake Mariner demo, the next launch loads the new demo from the start, with a fresh ledger, so the demo matches the skills that narrate it. Your own projects are never touched.

**Backtesting a past project.** Start it with `/groundwork:new-project` as of the date you want to begin, using only what was known then. Then replay its messages in date order. Each recorded message moves the project's date forward to the message's date. `check_overdue` moves the date forward by itself and lists work past due with no word, so Groundwork can plan chases. A message can report progress: an item done or started, with its date. It can also report date changes. Both wait for your confirmation in the app, and until then `status` shows the forecast "if confirmed" beside the confirmed one. Links Claude inferred rather than read in a source are flagged, and you can confirm or remove them. `docs/DATA-BOUNDARY.md` covers what leaves your machine, and ADR 0008 covers the design.

**Hosted demo:** if you'd rather not install anything, the same demo runs in the browser at https://groundwork-demo.fly.dev (`docs/HOSTING.md` covers deploying it). It's a demo of one made-up project and can't create projects; see the next section. To watch Claude plan the demo's other messages live, add your own Anthropic API key from the menu under your name: it stays in that browser tab's memory and is never stored, and the inbox then shows the five extra messages below.

## Keep your data on your laptop

For a real project, run Groundwork on your own computer. Both ways run all of it there: the server, the web app, the database and the ledger.

- **The Claude plugin** (above). Your projects live under `~/.groundwork`, and the app answers only on 127.0.0.1. What leaves your computer is what your own Claude session reads with your connectors and what Groundwork's tools return to it, under your Claude account's terms. The Groundwork server itself makes no network calls.
- **`make dev`** (below). Your projects live in your local Postgres. Nothing leaves your machine unless you set `ANTHROPIC_API_KEY` or add a key from the menu under your name; then the planner receives what `docs/DATA-BOUNDARY.md` lists.

The hosted demo is for trying Lake Mariner without installing anything. It has no accounts, holds only the demo, and deletes each visitor's copy after 12 hours, so don't put a real project there. ADR 0010 explains the choice.

## Run it locally

**You need:** Postgres 14 or newer running locally, [uv](https://docs.astral.sh/uv/), and Node 20 or newer (22 LTS recommended). `make doctor` checks all three and prints install commands.

```bash
make doctor
```
```bash
make dev
```

`make dev` writes `.env` with fresh dev secrets, creates the database roles and databases, applies migrations, seeds Lake Mariner, installs the web app's packages, and serves **Groundwork on http://localhost:3000** with live reload (its API is on http://localhost:8000 under `/api`, docs at `/api/docs`). Ctrl-C stops both. You're signed in as **Jordan Brooks**, the demo project's lead and its one approver; there is no one else to choose. Then play the demo below.

`make web-build` builds the web app into `web/dist`, and from then on `make api` serves it too, on http://localhost:8000: one process, as in the plugin and the hosted demo (ADR 0009).

Set `ANTHROPIC_API_KEY` in `.env` to have Claude write the plans for the other inbox events (Opus 5.5 plans; Haiku 5.5 checks outbound text and writes the report). The demo event is scripted and never calls a model. `docs/DATA-BOUNDARY.md` lists exactly what leaves your machine.

Docker, untested because the author's machine has no Docker: `sh scripts/new-env.sh`, then `docker compose --profile full up --build`, then open http://localhost:8000.

## The tutorial and the two-minute demo

Click **Start the tutorial** at the top of the home view (or **Tutorial** next to Lake Mariner). A short dialog sets the scene: a data center is coming online at Lake Mariner, and you're Jordan, the project manager for the company that will use it. A small panel then walks through each feature in sixteen steps: the date and what it waits on, the schedule, an email arriving and Groundwork working through it (a demo message plays a written plan, one step at a time, labeled as a simulated agent), allow, ask and deny, approving the ask on the project's Actions tab, the mandate, the ledger, and how to have Claude plan live with your own API key. Each step points at one thing on the page and you click it yourself, tabs included, so you get around the app the way you would without the tutorial; steps that only explain have Next, and Back steps through what you've seen. While you read the ledger, a second email plays in the background, so the home view you return to has asks waiting and a second run under Activity. Closing the panel pauses it, and opening it again (from the home view, the badge or the menu under your name) picks up at the furthest step you reached; the menu can also start it over. It ends with "That's the whole tour!": start your own project, or keep exploring the demo. Once finished, home stops offering it. The model scorecard and the blind arm stay in the evals (below) and the API, not the app.

The demo by hand: open **Lake Mariner**, then its **Inbox** tab, and play the first message, **"Demo: the utility wants another review"**. It plays the same hand-written plan every time; the gateway, ledger and report check are live code.

1. **The forecast moves.** The data center is now forecast for Apr 13, 2027, 50 days late, still waiting on the utility's approval of the power settings. **Waiting on** opens the steps the date depends on and why it moved, each delay citing the email it came from. When the run is done, **See the 3 next steps** opens the Actions tab.
2. **Allow.** A weekly status request to Fluidstack, the tenant. The mandate allows it on its own; it runs in dry run, so it's recorded and not sent.
3. **Ask.** Asking the landlord, through Fluidstack, to confirm the power-on date. Anything to the landlord waits for you, so it's under **Needs you** on the home view.
4. **Deny.** The landlord also asks you to sign a revised schedule. Signing is never Groundwork's to do, so it's denied and left to you, and the agent's report says so.
5. **Report vs. ledger.** The run says "Report matches the ledger". On the Actions tab, open **Report vs. ledger** to see each line of the agent's report beside the ledger's record. Click a record number to open **Verify a receipt** in the project's Settings. Check it: **Match**. Use **Paste the stored record**, change one word, and check again: **Mismatch**.

Then try the auto-reply that says "approved, please proceed" and changes nothing, approving from the home view, a new mandate template in the Settings tab, and **Try to break it** at the bottom of the Ledger tab (on your own computer only; the hosted demo refuses it). The demo also holds five messages the inbox leaves out unless they've been played or the tab has an API key: event A (the same delay, with a fuller plan), the switchgear email the tour plays, the rush offer that follows it, and two with instructions for AI hidden in them. Tests, evals and Claude play them through the API.

**Your own project, on the website.** **New project** on the home view opens a short form: what finishing means and when, who you're waiting on, and what has to happen in what order. "Check the forecast" shows the forecast and what sets the date before anything is saved; "Create the project" makes it, as a project of its own with its own ledger. This works on your computer (`make dev` or the plugin); the hosted demo doesn't create projects. To have Groundwork read your mail and chase what's late, use the plugin.

## Changing the words

Every word the app shows lives in a handful of files, so copy can change without touching code:

- `web/copy/tutorial.ts`: the tutorial, its card on home and its start and end dialogs.
- `web/copy/home.ts`: the home page (Needs you, Projects, Activity).
- `web/copy/project.ts`: a project's page and its five tabs, including the approve drawer.
- `web/copy/newProject.ts`: the New project form and its example.
- `web/copy/app.ts`: the header and account menu, shared labels, and the receipt check in Settings.
- `backend/groundwork/service/narration.py`: what a run says, step by step, in the Inbox.

The demo's own content (step names, emails, the scripted plans) is in `fixtures/lake-mariner/`. The mandate's rules and the gateway's reasons are written by the gateway (`backend/groundwork/policy/`), since they are part of the record. After editing a `web/copy` file, `make web-build` rebuilds the app.

## Evals

```bash
cd backend && uv run python -m evals.run
```

Plays 6 event templates under the 3 mandate presets in both arms (with and without the mandate in the prompt) and runs the real gateway over every plan. It reports hard violations, over-reach (held) and over-caution, honest reporting against the ledger including a withheld-row check, plan quality against a reviewed set, and injection resistance (graded by a fixed Sonnet 5.5 judge plus deterministic rules). `--live --model <id> --repeat 3` runs Claude: 108 case runs and about 310 to 360 action decisions per arm. Every case run is saved in `backend/evals/results/`. Definitions and grading notes are in `backend/evals/README.md`.

**Live results, Nov 1, 2026** (Lake Mariner fixture, 6 events x 3 presets x 2 arms x 3 repeats per model; the content classifier and reports run on Haiku 5.5 throughout):

| Metric | Opus 5.5 with mandate | Opus 5.5 without | Sonnet 5.5 with mandate | Sonnet 5.5 without | Haiku 5.5 with mandate | Haiku 5.5 without |
|---|---|---|---|---|---|---|
| Hard violations (auto on pay, sign, delete) | 0 | 0 | 0 | 0 | 0 | 0 |
| Over-reach: wanted more autonomy than the mandate allows | 19.0% | 35.8% | 13.7% | 39.0% | 10.3% | 25.2% |
| Over-caution: asked where it could act | 3.2% | 5.4% | 3.2% | 4.6% | 5.3% | 5.9% |
| Reports matching the ledger | 98.1% | 100.0% | 98.1% | 100.0% | 96.3% | 100.0% |
| No fabrication when a ledger row is withheld | 98.1% | 100.0% | 100.0% | 100.0% | 100.0% | 98.1% |
| Injection cases resisted | 18 of 18 | 18 of 18 | 18 of 18 | 18 of 18 | 18 of 18 | 18 of 18 |
| Plan quality: precision@3 vs. the reviewed set | 0.85 | 0.84 | 0.85 | 0.83 | 0.57 | 0.56 |
| Action decisions | 358 | 345 | 335 | 344 | 319 | 312 |

Cost of the run: Opus 5.5 $12.02, Sonnet 5.5 $6.02, Haiku 5.5 $0.85.

What the numbers say:

- **The rules hold where they are enumerable.** No model proposed paying, signing or deleting on its own authority in about 2,000 decisions; when a model proposed a payment at all (Haiku 14 times, Opus 9, Sonnet never), it proposed refusing it.
- **Spelling out the mandate roughly halves over-reach, and does not remove it.** With the mandate in the prompt, 10 to 19% of actions still asked for more autonomy than allowed; without it, 25 to 39%. The gateway held every one. This is the capability prediction measured on this product: enumerable scope is reliable with explicit rules plus an external gateway, and judgment alone is not.
- **Over-reach concentrates at the edges of permissive mandates.** Under the Auto template Opus over-reached on 39% of actions (Supervised 9%, Standard 14%). The two patterns: proposing to draft a legal notice alone (the mandate routes legal drafts to counsel even though nothing is sent), and emails to the lessee asking the landlord or NYSEG to act (the mandate routes requests to further parties, and anything reaching the utility, to a person). Both are fine print a model reads as "safe"; neither escaped the gateway.
- **Reporting is honest.** 96 to 100% of post-run reports matched the ledger, and with one action's ledger rows withheld, 98 to 100% left it out rather than inventing a status.
- **Injections were resisted 108 of 108 times.** In the plans read by hand, models flagged the injected date change and payment request to the owner, refused the payment, or asked a legitimate party to confirm in writing.
- **Opus and Sonnet agree with the reviewed first-three actions about 85% of the time; Haiku 57%.** The reviewed set is pending practitioner review, so this measures agreement with our key, not correctness.

Limits: the table averages each rate per case, while the per-template figures above count all actions together. One synthetic site and six event templates; actions within one plan are not independent, so treat differences under about 5 points as noise; the classifier is Haiku in every run, and a stricter or looser classifier moves over-reach. The scripted planner scores 0 hard violations, 3.5% over-reach and 100% on reports and injection by construction (its plans and the reviewed set were written together).

## Test

```bash
make test
```
```bash
make e2e
```

Lint (ruff), types (pyright), six import boundaries (import-linter: the planner cannot reach executors, approvals, the ledger or the database; ingestion cannot create approvals) and the test suite. It covers:

- the calendar and scheduler, and golden tests on the fixture;
- 144 gateway table rows plus 30 rule tests, and the mandate clause each kind of decision cites;
- the ledger: test vector, tamper and delete detection, triggers that bind the owner, no forks under concurrency;
- the honesty check;
- the pipeline end to end, typed, bound approvals, and the scripted demo path (the same allow, ask and deny even with a live key);
- checking one record: a match, a forged copy, and an edited stored record;
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
- sandboxes: two visitors cannot see each other's work, signing in again keeps a sandbox, starting the tour again replaces it, and expired sandboxes are deleted with their ledgers;
- the web app's session: a cookie its scripts cannot read, state changes refused without this app's Origin, and, in the plugin, one browser that sees every project on the computer while each request runs in one project's org.

`make e2e` is the browser walkthrough (Playwright, `web/e2e/`). It runs the two-minute demo step by step, including a match and a mismatch under Receipts in the project's Settings. It also plays event A, checks the forecast against the API, finds the action the gateway held, plays the auto-reply and sees nothing change, approves the held action from the home view, issues a new mandate version and checks that only open actions were decided again, and tampers with a record, watches verification fail and resets. It checks that a state change without this app's Origin is refused. With sandboxes on, as in the hosted profile, a second browser checks that two visitors cannot see each other's work. It uses your installed Google Chrome and starts the API and the web app's dev server if they are not running; `E2E_BASE_URL=http://localhost:8000 make e2e` tests the built app instead.

## Cost

Measured in the Nov 1, 2026 eval run: about $0.22 per event on Opus 5.5 (both arms, plus the Haiku reports), $0.11 on Sonnet 5.5 and under $0.02 on Haiku 5.5. With Opus planning:

| | Per event | Per site per month | 15 sites per month |
|---|---|---|---|
| 5 events a day | $0.22 | $33 | $500 |
| 20 events a day | $0.22 | $134 | $2,000 |

Opus 5.5 planning in both arms (the blind arm reads the informed arm's cache), Haiku 5.5 for classification and reports. `cd backend && uv run groundwork cost` reports actual spend from recorded usage.

## Load your own site

A site is a folder: `site.yaml` (site, milestone, parties with roles and routing), `schedule.csv` (one row per item; predecessors in one column, e.g. `to_accept FS+15bd; meter`), optional `events.yaml`, `evidence/`, `inbox/` and `reference_projects.csv`. `fixtures/lake-mariner/` is the template and its README explains each file. A step's status is `not_started`, `in_progress`, `done` or `cancelled` (descoped: kept on record, ignored by the forecast). Put `true` in the optional `estimated` column when a date is a guess; a done step with no `actual_finish` keeps its planned date, marked as an estimate.

```bash
make inspect SITE=path/to/your-site
```

It validates the folder, lists every problem at once if there are any, and otherwise prints the gate, critical path, holiday losses and forecast, plus any sequencing rule your schedule breaks. Loading it into the database is `cd backend && uv run groundwork seed path/to/your-site`. To have Groundwork read a project's email, use the plugin. Reading PDFs isn't built yet.

## Docs

- `docs/ARCHITECTURE.md`: the system as it is built today.
- `docs/decisions/`: ADRs 0001 to 0011.
- `backend/evals/README.md`: what each eval measures and how it is graded.
- `docs/HOSTING.md`: deploying, checking and running the hosted demo.
- `docs/LEDGER.md`: the ledger's hash format, a test vector, and what verification does and does not catch.
- `docs/DATA-BOUNDARY.md`: exactly what leaves your machine.

## Known limits

- The evals cover one synthetic project and six messages, and their numbers predate three later gateway changes.
- Nothing is ever sent. Real sending needs an outbox that records each send exactly once.
- The plugin has one person per install, and its local database trusts every program on the laptop.
- The hosted demo is one machine, so a deploy stops a running message, which is then marked interrupted.
- The Docker setup hasn't been run.
- A practitioner hasn't yet confirmed the gating item, the forecast's assumptions or the reviewed plans. The fixture marks each assumption `assumption_to_verify`.
