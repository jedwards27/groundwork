# Data boundary: what leaves your machine

Groundwork's local mode keeps project data on your machine except for one destination: Anthropic's API, used by the planner (slice 2) and extraction (slice 4). This page lists exactly what is sent, what never leaves, and every other network contact the stack makes, so the claim can be checked behind a proxy.

## Project data at run time

**Sent to `api.anthropic.com`, only when `ANTHROPIC_API_KEY` is set:**

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

- **None.** The browser loads everything from the web app's own address: scripts, styles and fonts are bundled, so there is no font or analytics request to a third party. The web app's server talks only to the API. Next.js anonymous telemetry is turned off with `NEXT_TELEMETRY_DISABLED=1` in `.env.example`, `next.config.ts`, both run profiles and the web container, and a test checks it. Executors run in dry run, so no email, calendar or filing leaves the system.

## Hosted demo (separate profile)

The hosted demo holds only the synthetic and public Lake Mariner fixture. Where things live (docs/HOSTING.md, ADR 0007):

- **Fly.io, Ashburn (`iad`):** two machines. Mission Control is the only public one. The API has no public address and is reached over Fly's private network. Fly keeps the request logs.
- **Neon, AWS US East 1:** the database. Connections use TLS.
- **Secrets:** stored as Fly secrets. The API machine holds the database URLs, the signing secret, the admin token and, if set, the Anthropic API key. The web machine holds only the admin token. They are generated into a gitignored `.env.hosted` and never printed.
- **Anthropic's API:** receives what is listed above, only when a key is set, and capped per day. After the cap the simulated planner runs with its banner.

Dry run is forced on regardless of configuration. The API refuses to start on development secrets or passwords. Each visitor works in a private sandbox copy of the fixture, deleted with its ledger 12 hours after it was created. Expired sandboxes are swept and the shared fixture is reloaded every night at 08:00 UTC.
