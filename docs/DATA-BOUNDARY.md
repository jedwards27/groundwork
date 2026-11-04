# Data boundary: what leaves your machine

Groundwork's local mode keeps project data on your machine except for one destination: Anthropic's API, used by the planner (slice 2) and extraction (slice 4). This page lists exactly what is sent, what never leaves, and every other network contact the stack makes, so the claim can be checked behind a proxy.

## Project data at run time

**Sent to `api.anthropic.com`, only when `ANTHROPIC_API_KEY` is set, or when a visitor adds their own key from the account menu (hosted demo or `make dev`; never in the plugin). A visitor's key stays in that browser tab's memory, goes with each Play, is used for that one run and is never stored:**

- The site's items, links, dates, statuses and forecast (the planner's context).
- The text of the event being played.
- The mandate (the grant of authority) in the informed arm; the never-list and the owner's goals in the blind arm.
- The tail of the site's ledger: action titles, decisions and outcomes.
- In slice 4, the text and pages of documents you load for extraction.

**Never sent anywhere:** approvals and who made them, signing secrets and tokens, people's email addresses (addresses inside forwarded messages are replaced with "[address withheld]" before a model sees them, and a test checks the prompt), database credentials, the full ledger, and anything from another org.

**Also sent, when live:** the text of outbound messages and drafts the planner proposes, to the Haiku classifier; the plan and the ledger entry types for its actions, to the Haiku reporter.

Without an API key nothing is sent; the hand-written simulated planner runs instead, under a banner that says so.

**Retention.** Under Anthropic's commercial terms, API inputs and outputs are not used for training and are retained for a limited period; zero-data-retention is available by agreement for production. *Verify the current terms before submission:* https://www.anthropic.com/legal/commercial-terms. Zero-data-retention is a production option, out of scope for v1.

## Install-time network (no project data)

- Python packages from PyPI (`uv sync`), the web app's packages from the npm registry (`npm ci`), and Python itself if uv downloads it.
- Docker image pulls from Docker Hub (`postgres:16`, `python:3.13-slim`, `node:22-alpine`) and the uv image from GitHub's container registry, if you use the Docker profile.
- Homebrew or nodejs.org, if `make doctor` suggests installing Postgres or Node.
- Nothing for the browser tests by default: they use your installed Google Chrome. Playwright's own Chromium is downloaded only if you choose it (`npx playwright install chromium`).

## Run-time network other than Anthropic

- **None.** The browser loads everything from the app's own address, which also serves the API: scripts and styles are bundled and the fonts are the system's, so there is no font or analytics request to a third party. The content security policy limits the page's requests to its own origin (`connect-src 'self'`), and a test checks it. The web app has no framework telemetry. Executors run in dry run, so no email, calendar or filing leaves the system.

## The Claude plugin (local)

When Groundwork runs as a Claude plugin, project data reaches Anthropic only through the person's own Claude session, under their account's terms:
- what Claude reads with their connectors;
- what Groundwork's tools return to Claude.

The Groundwork server runs on the machine and keeps everything under `~/.groundwork`: the embedded database, drafts, the person's name and email, and the token in Claude's links to the web app. It makes no network calls at run time; it clears `ANTHROPIC_API_KEY`, so the server itself never calls a model. The web app and its API listen on 127.0.0.1 only, and answer only to the names 127.0.0.1 and localhost. The outbound guard holds connector sends addressed to a party on a tracked project and records them; it sends nothing.

On first launch, uv downloads Python 3.12 and the locked packages from PyPI, including `pgserver`, which bundles the Postgres binaries. No project data is involved.

## Hosted demo (separate profile)

The hosted demo holds only the synthetic and public Lake Mariner fixture. It is for the demo only: real projects run on the person's own computer, through the plugin or `make dev` (ADR 0010). Where things live (docs/HOSTING.md, ADR 0007):

- **Fly.io, Ashburn (`iad`):** one public machine serving the web app and its API (ADR 0009). Fly keeps the request logs.
- **Neon, AWS US East 1:** the database. Connections use TLS.
- **Secrets:** stored as Fly secrets. The API machine holds the database URLs, the signing secret, the admin token and, if set, the Anthropic API key. The web machine holds only the admin token. They are generated into a gitignored `.env.hosted` and never printed.
- **Anthropic's API:** receives what is listed above, only when a key is set, and capped per day. After the cap the simulated planner runs with its banner.

Dry run is forced on regardless of configuration. The API refuses to start on development secrets or passwords. Each visitor works in a private sandbox copy of the fixture, deleted with its ledger 12 hours after it was created. Expired sandboxes are swept and the shared fixture is reloaded every night at 08:00 UTC.
