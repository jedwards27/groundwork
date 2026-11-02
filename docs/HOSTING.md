# Hosting the demo

The hosted demo is Mission Control on a public HTTPS link, running the Lake Mariner fixture: synthetic and public data only, dry run forced on, and live planning capped per day. Every visitor gets a private sandbox, their own copy of the demo that nobody else sees, deleted after 12 hours. ADR 0007 explains the choices.

```
browser ──HTTPS──▶ Mission Control (Fly machine, public)
                        │  Fly private network (IPv6)
                        ▼
                   API (Fly machine, no public address) ──TLS──▶ Postgres (Neon, free plan)
                        └──────────────────────────────────────▶ api.anthropic.com (only with a key)
```

**Cost:** about $7 a month for two small Fly machines; Neon's free plan is $0. Fly needs a card on file.

## What you need

- A [Fly.io](https://fly.io) account and `flyctl` ([install](https://fly.io/docs/flyctl/install/)), then `fly auth login`. Fly builds the images on its own builders, so you do not need Docker.
- A [Neon](https://neon.com) account with one project. Pick the AWS US East 1 region, which is next to Fly's Ashburn region.
- Optionally, an Anthropic API key for the live planner. Without one, the demo runs the simulated planner under a banner that says so.

## Deploy

1. **Copy the admin connection string from Neon.** In the project's dashboard, open "Connect" and copy the connection string for the `neondb_owner` role, choosing the direct connection rather than the pooled one. It is used once, in the next step, and is never stored.
2. **Create the database roles and secrets.** At the prompt, paste the string (input is hidden):

   ```bash
   make hosted-bootstrap
   ```

   It creates `groundwork_owner` and `groundwork_app` with random passwords; neither gets BYPASSRLS. It creates the `groundwork` database owned by `groundwork_owner`, checks that both logins work, and writes the database URLs, a new signing secret and an admin token to `.env.hosted` at the repo root. That file is gitignored, readable only by you, and its values are never printed.
3. **Optional: turn on the live planner** by adding a line `ANTHROPIC_API_KEY=sk-ant-...` to `.env.hosted`.
4. **Deploy.** App names are global on Fly. The defaults are `groundwork-demo-api` and `groundwork-demo` (created Nov 2, 2026); to use other names, set `FLY_API_APP` and `FLY_WEB_APP` first.

   ```bash
   make deploy
   ```

   It creates the two Fly apps if they are missing and imports the secrets: the API gets all of them, the web app only the admin token. Then it deploys the API, whose release step migrates and loads the fixture, and then Mission Control. It ends by printing the link: `https://<web app>.fly.dev`.

## Check it

- **The page.** Open the link and choose Dana Ortiz. A blue banner says this is your own copy of the demo and when it will be deleted. There is no "Tamper with one entry" button, and the ledger says "Chain verified".
- **Sandboxes.** Open the link in a private window too and play event A in one window. The other window's countdown does not move.
- **The API is private.** Expect no addresses to be listed:

  ```bash
  fly ips list -a groundwork-demo-api
  ```

- **Admin paths are not reachable from the browser.** Expect `404`:

  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' -X POST https://groundwork-demo.fly.dev/api/gw/admin/reset
  ```

- **Logs are clean,** including the startup preflight:

  ```bash
  fly logs -a groundwork-demo-api
  ```

## Run it

- **Sandboxes.** A visitor's first demo login creates their sandbox. Switching persona keeps it, and "Start over" replaces it with a fresh copy. It is deleted 12 hours after it was created; a visitor who returns after their one-hour session gets a new one.
- **Nightly sweep.** At 08:00 UTC (3 or 4 a.m. Eastern) the API deletes expired sandboxes and reloads the shared fixture that sandboxes are copied from. A deploy also reloads it.
- **Caps, across all visitors.** Up to 200 new sandboxes, 300 runs and 30 runs that call Claude a day. After the Claude cap, the simulated planner takes over with its banner. They are set in `fly.toml`; redeploy after changing them.
- **Rotate every secret.** This rotates both database passwords, the signing secret (every token stops working) and the admin token.

  ```bash
  cd backend && uv run groundwork hosted-bootstrap --force
  ```
  ```bash
  make deploy
  ```

- **Take it down.** Then delete the Neon project in its console.

  ```bash
  fly apps destroy groundwork-demo
  ```
  ```bash
  fly apps destroy groundwork-demo-api
  ```

## Rehearse on your machine first

```bash
make rehearse-hosted
```

It builds the web app, then starts a throwaway Postgres whose admin role is neither superuser nor BYPASSRLS, as on Neon. It runs the same bootstrap, preflight and release commands as a deploy, and serves the hosted API on :8100 and Mission Control on :3200. Run the browser walkthrough against it from another terminal; the tamper test is skipped because the hosted profile refuses it. Ctrl-C deletes the cluster and its secrets.

```bash
E2E_BASE_URL=http://localhost:3200 make e2e
```

## Safety rails, and what they do not cover

- **Preflight.** The API will not start in the hosted profile while any of these holds (`groundwork preflight --hosted` shows the same list):
  - the signing secret or admin token is missing or short;
  - either database URL uses a development password;
  - both URLs use the same role;
  - the daily caps are missing or out of range.
- **Hosted profile.** Dry run is forced on whatever the configuration says, tokens last one hour, and the API refuses the tamper endpoint.
- **Isolation.** Each visitor's sandbox is a separate org, so row-level security keeps visitors apart, as it does customers.
- **Who holds what.** The web machine holds only the admin token.
- **Not covered:**
  - There is no rate limit per visitor beyond the daily caps, so one visitor could use up the day's sandboxes.
  - The API holds the owner credentials, because the nightly reset needs them.
  - One API machine means a deploy interrupts a running event; the run is marked interrupted.

## Assumptions to check on the first real deploy

These come from the providers' documentation and the local rehearsal, not from a real Fly or Neon account:

- Neon lets `neondb_owner` run `CREATE ROLE` and `CREATE DATABASE` from SQL. If `CREATE DATABASE` is refused, create a database named `groundwork` in the Neon console with `groundwork_owner` as owner, then run the bootstrap again with `--force`.
- Neon's compute suspends between visits when the API holds no idle connections. Neon documents suspension after five minutes without queries; the API opens a connection per request (`GROUNDWORK_DB_NULLPOOL`), so this should hold. Watch the compute hours in the Neon console during the first week.
- `fly deploy` builds from the folder it runs in. `scripts/deploy-fly.sh` runs it from the repo root for the API and from `web/` for Mission Control.
