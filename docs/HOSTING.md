# Hosting the demo

The hosted demo is the Groundwork web app on a public HTTPS link, running the Lake Mariner fixture: synthetic and public data only, dry run forced on, and live planning capped per day. Every visitor is signed in as the demo's lead and gets a private sandbox, their own copy of the demo that nobody else sees, deleted after 12 hours. ADR 0007 explains the choices, and ADR 0009 the move to one machine.

```
browser ──HTTPS──▶ Groundwork (one Fly machine: the web app, and its API under /api)
                        ├──TLS──▶ Postgres (Neon, free plan)
                        └───────▶ api.anthropic.com (only with a key)
```

**Cost:** less than $7 a month for one small Fly machine (the old layout used two); Neon's free plan is $0. Fly needs a card on file.

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
4. **Deploy.** App names are global on Fly. The default is `groundwork-demo` (created Nov 2, 2026); to use another name, set `FLY_APP` first. The `groundwork-demo-api` app from the old two-machine layout is no longer used; destroy it when convenient (below).

   ```bash
   make deploy
   ```

   It creates the Fly app if it is missing, imports the secrets, and deploys. The image builds the web app in a Node stage and serves it from Python, so the machine runs no Node. The release step migrates and loads the fixture. It ends by printing the link: `https://groundwork-demo.fly.dev`.

## Check it

- **The page.** Open the link: you land on the home view, signed in as the demo's lead. The account menu (your name, top right) says when your copy will be deleted. The Ledger tab says "Intact" and has no "Try to break it" panel.
- **Sandboxes.** Open the link in a private window too and play event A in one window. The other window's forecast does not move.
- **Admin and tamper paths are refused.** Expect `403` from both:

  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' -X POST https://groundwork-demo.fly.dev/api/admin/reset
  ```
  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' -X POST https://groundwork-demo.fly.dev/api/admin/tamper
  ```

- **Logs are clean,** including the startup preflight:

  ```bash
  fly logs -a groundwork-demo
  ```

## Run it

- **Sandboxes.** A visitor's first visit signs them in and creates their sandbox. Starting the tour replaces it with a fresh copy. It is deleted 12 hours after it was created; a visitor who returns after their one-hour session gets a new one.
- **Nightly sweep.** At 08:00 UTC (3 or 4 a.m. Eastern) the API deletes expired sandboxes and reloads the shared fixture that sandboxes are copied from. A deploy also reloads it.
- **Caps, across all visitors.** Up to 200 new sandboxes, 300 runs and 30 runs that call Claude a day. After the Claude cap, the simulated planner takes over with its banner. They are set in `fly.toml`; redeploy after changing them.
- **Caps per visitor.** Each address can start 20 sandboxes and play 100 emails a day, so one script can't use up the day for everyone. The count is kept under a keyed hash of the address, never the address, and deleted after two days.
- **If the demo is locked out on the day.** Clear today's counts in the Neon SQL editor:

  ```sql
  DELETE FROM daily_usage WHERE day = current_date;
  ```
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

  The old API app, if it is still there:

  ```bash
  fly apps destroy groundwork-demo-api
  ```

## Rehearse on your machine first

```bash
make rehearse-hosted
```

It builds the web app, then starts a throwaway Postgres whose admin role is neither superuser nor BYPASSRLS, as on Neon. It runs the same bootstrap, preflight and release commands as a deploy, and serves the hosted profile, the web app and its API, on :8100. Run the browser walkthrough against it from another terminal; the tamper test is skipped because the hosted profile refuses it. Ctrl-C deletes the cluster and its secrets.

```bash
E2E_BASE_URL=http://localhost:8100 make e2e
```

## Safety rails, and what they do not cover

- **Preflight.** The API will not start in the hosted profile while any of these holds (`groundwork preflight --hosted` shows the same list):
  - the signing secret or admin token is missing or short;
  - either database URL uses a development password;
  - both URLs use the same role;
  - the daily caps are missing or out of range.
- **Hosted profile.** Dry run is forced on whatever the configuration says, tokens last one hour, and the API refuses both tamper endpoints. It also refuses to start with `GROUNDWORK_LOCAL` on, which would let one browser act in every org.
- **Isolation.** Each visitor's sandbox is a separate org, so row-level security keeps visitors apart, as it does customers.
- **Who holds what.** The one machine holds every secret. The browser holds only its session token, in a cookie its scripts cannot read, and a state change riding on that cookie must carry the app's own Origin.
- **Not covered:**
  - The per-visitor limits key on the address, so a script spread over many addresses could still use up the day's caps.
  - The API holds the owner credentials, because the nightly reset needs them.
  - One API machine means a deploy interrupts a running event; the run is marked interrupted.

## Assumptions to check on the first real deploy

These come from the providers' documentation and the local rehearsal, not from a real Fly or Neon account:

- Neon lets `neondb_owner` run `CREATE ROLE` and `CREATE DATABASE` from SQL. If `CREATE DATABASE` is refused, create a database named `groundwork` in the Neon console with `groundwork_owner` as owner, then run the bootstrap again with `--force`.
- Neon's compute suspends between visits when the API holds no idle connections. Neon documents suspension after five minutes without queries; the API opens a connection per request (`GROUNDWORK_DB_NULLPOOL`), so this should hold. Watch the compute hours in the Neon console during the first week.
- `fly deploy` builds from the folder it runs in. `scripts/deploy-fly.sh` runs it from the repo root, which the image needs for `web/` and `fixtures/`.
- One `shared-cpu-1x` machine with 512 MB serves the web app and the API; the old web machine had the same size. If the API runs short of memory under the demo's load, raise it in `fly.toml`.
