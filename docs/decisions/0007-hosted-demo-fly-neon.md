# 0007. Hosted demo: two Fly.io machines and a free Neon Postgres; no database role needs BYPASSRLS

**Status:** accepted. Settles the hosting `[DECIDE]` in ARCHITECTURE §3.

**Context.** The hosted demo holds only the synthetic and public Lake Mariner fixture. It has to be reachable by a link, cost a few dollars a month, keep the API key and signing secret off anything public, stay in dry run, and reset itself. Two facts shaped the choice:

- **BYPASSRLS.** Locally, the owner role (migrations, seeding, reset) had the BYPASSRLS attribute, and every org-scoped table forced row-level security even for its owner. On managed Postgres you are not a superuser. Postgres lets only a superuser, or a role that already has BYPASSRLS, grant it, and attributes are not inherited through role membership. Neon's admin role belongs to `neon_superuser`, which has the attribute, but whether that admin can create a role with it could not be confirmed from the documentation.
- **Scale to zero.** Neon's free plan includes 100 compute-hours a month per project and suspends compute after 5 minutes without queries. Whether an idle pooled connection counts as activity is not documented. A pool that kept the compute awake would use up the month in about 17 days at the smallest size (100 hours at a quarter compute unit is 400 hours).

**Options.**
- (a) Fly.io API and web machines plus Neon free.
- (b) Render: a public web service, a private service and a cron job, plus Neon free. About $7 per service per month, and it deploys from a GitHub repo.
- (c) One virtual machine running `docker compose` with Caddy for TLS. It is cheap and identical to local, but the machine, its patches and its certificates become ours to run.
- (d) Fly Managed Postgres instead of Neon. Too expensive for a demo.

**Decision.** (a).
- **Machines.** The API runs on one Fly machine with no public service, so it is unreachable from the internet. It listens on IPv6 for Fly's private network. The web app is the only public machine, with HTTPS forced, and it reaches the API at `<api-app>.internal`. Both are 512 MB shared-CPU machines in Ashburn (`iad`), next to Neon's `aws-us-east-1`.
- **Database roles.** The owner role no longer has BYPASSRLS. It gets past row-level security only by owning the tables: migration 0003 turns off FORCE on every table. The app role is still not an owner and has no BYPASSRLS, so it remains bound by row-level security. This works on any Postgres where you can create roles.
- **Setup.** `groundwork hosted-bootstrap` uses the database admin's URL once. It creates the two roles with random passwords and the database, and writes every hosted secret to a gitignored `.env.hosted` without printing it. The deploy script imports those secrets into Fly. The web machine receives only the admin token.
- **Hosted mode.**
  - The API opens a connection per request (`GROUNDWORK_DB_NULLPOOL`), so Neon can scale to zero.
  - The API refuses to start if a secret is weak, missing or a dev default.
  - It caps all runs per day as well as live planning.
  - It reseeds the fixture nightly from inside the API process.
  - Dry run is forced on, tokens live one hour, and the tamper endpoint is refused.

**Consequences.**
- **Cost.** About $7 a month: two machines, plus Neon at $0. Deploys need only the `fly` CLI, because Fly builds the images remotely, and neither GitHub nor local Docker is required.
- **Owner role semantics.** Dropping BYPASSRLS changes nothing in practice. The owner always bypassed row-level security, and FORCE only binds an owner that lacks BYPASSRLS. The app role's isolation is untouched, and `tests/test_db_rls.py` asserts both roles' attributes.
- **Credentials in the API.** The API process holds the owner credentials, which the nightly reset and the admin reset need. A production deployment would keep them in a release or cron process only.
- **No high availability.** One API machine, on purpose. Runs are in-process background tasks, and a second machine's startup sweep could mark the first machine's runs as interrupted.
- **Shared personas.** Visitors share the demo personas and one org, so two people clicking at once see each other's runs. The nightly reseed bounds the mess. A sandbox org per visitor is the real fix and the next step if the link is shared widely.
- **Verification.** The hosted profile was exercised locally against a throwaway Postgres cluster. Its admin role had only CREATEROLE and CREATEDB, no superuser and no BYPASSRLS, to stand in for Neon's admin. Bootstrap, migrations, seeding, the hosted API and the browser walkthrough all ran against it. Fly and Neon themselves are untested until the first real deploy (`docs/HOSTING.md`).
