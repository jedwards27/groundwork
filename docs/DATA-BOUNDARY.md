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

- Python packages from PyPI (`uv sync`), the npm registry (web app, slice 3), and Python itself if uv downloads it.
- Docker image pulls from Docker Hub (`postgres:16`, `python:3.12-slim`) and the uv image from GitHub's container registry, if you use the Docker profile.
- Homebrew, if `make doctor` suggests installing Postgres or Node.

## Run-time network other than Anthropic

- **None.** Next.js anonymous telemetry is turned off with `NEXT_TELEMETRY_DISABLED=1` in `.env.example` and both run profiles, and a test checks it. Fonts are self-hosted (slice 3). Executors run in dry run, so no email, calendar or filing leaves the system.

## Hosted demo (separate profile)

The hosted demo holds only the synthetic and public Lake Mariner fixture. Its API runs on one small paid host with a free Neon Postgres. The API key lives server-side only. Dry run is forced on regardless of configuration. Live planning calls are capped per day, after which the simulated planner runs with its banner. The demo database is reset nightly.
