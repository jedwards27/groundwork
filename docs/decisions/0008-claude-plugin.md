# 0008: Groundwork as a Claude plugin, with confirmations on Groundwork's own page

**Status:** accepted (Nov 2, 2026)

**Update (Nov 4, 2026):** ADR 0011 adds drafts for changing a project after it starts (its steps, details and parties) and for archiving or deleting one, confirmed in the same app.

**Update (Nov 3, 2026):** ADR 0009 replaces the local page with the same web app the hosted demo uses, served on 127.0.0.1 by the plugin's server. Claude's links still carry the random token; following one signs the browser in. Approvals and confirmations still happen only there, and the demo has one person, its lead, instead of personas.

## Context

The prototype should run where people already work: inside the Claude app, using the connectors and sign-in they already have, with no API key. A Claude plugin bundles skills, an MCP server and hooks, and the same folder installs in Claude Code and, as a zip, in Cowork. Hooks see every tool call, including other connectors' tools, and can allow, deny or ask. Hooks and tools don't see which model is running or who is signed in.

The binding rules still apply:
- the gateway stays outside the model;
- approvals are typed actions by a named person;
- the ledger is append-only;
- everything runs in dry run;
- one command runs everything locally.

## Options

1. **Runtime.** Require a local Postgres; port the backend to SQLite for single-user use; or embed Postgres (`pgserver`, a Postgres 16 build in a Python wheel).
2. **Who approves.** Use the app's own "allow" prompt, or a page Groundwork serves.
3. **Other connectors' outbound tools.** Leave them alone; block them all; or act only on calls addressed to a party on a tracked project.

## Decision

- **Runtime: embedded Postgres.** `groundwork mcp` starts it under `~/.groundwork`, creates the two roles, migrates, seeds Lake Mariner and serves a local page on 127.0.0.1. The full backend suite passes on it under Python 3.12, so row-level security, the ledger trigger and the advisory lock behave as in development and hosting. The plugin's launcher (`plugin/server/start.sh`) needs only uv; uv fetches Python 3.12 and the locked dependencies into the plugin's data folder.
- **Planner: Claude in the app.** Tools hand Claude the same planning context and rules the API planner gets, and accept plans in the same wire format. `pipeline.play_external_plan` runs the unchanged gateway, dry-run executors and ledger, and `submit_external_report` checks Claude's report against the ledger. The model id is self-reported and labeled as such.
- **Approvals and confirmations happen on Groundwork's local page.** This covers asks, mandate drafts, new projects and date changes from messages. The page calls the same `approvals.approve` as the web API, so an approval binds the person, the action's hash and the mandate version. The page's address carries a random token. The app's own prompt isn't used, because it isn't bound to the action or recorded. No tool can approve, confirm or issue anything, and a test lists the tools.
- **The outbound guard acts only on project parties.** A `PreToolUse` hook on connector tools that send, reply, forward, post or invite checks the recipients. If one is a person on a tracked project, the call is recorded as `outbound_held` in that project's ledger and denied, since everything is dry run. Every other call gets no decision, so an evaluator's own Gmail or Slack use is untouched.
- **Each project is its own org,** with its own ledger chain. Mail is routed by email thread first, then by sender and recipients, and the person decides when routing is unclear.
- **Mandates can be written in plain words.** Claude drafts terms; `policy/terms.build_from_terms` builds the version, and only the person's confirmation issues it. An expired mandate makes the gateway ask for everything it used to allow.

## Consequences

- **Data boundary.** Project data reaches Anthropic only through the person's own Claude session. The local server makes no network calls at run time (it clears `ANTHROPIC_API_KEY`).
- **First launch is slow.** It takes about a minute while uv builds the environment; a session-start hook warms it, and later launches take seconds.
- **Platform.** macOS first. `pgserver`'s last release was June 2024, so if it stops working, the fallback is the single-user SQLite port described in the plan.
- **One named person per install.** On the demo project, approvals are made as its demo personas, and the page labels them as such. Team sign-in comes later.
- **Governing connector sends** with full gateway decisions waits for real sending (story S17).
- **The demo follows the plugin, not the person (Nov 3, 2026).** The demo used to be seeded only on first launch, so an update left the older build's mandate and its run beside newer scripted plans and skill text, and the demo message reported "already played". Now the demo's site row stores a fingerprint of its fixture folder, and a launch reloads the demo when the fingerprint differs. The check, the reseed and the new fingerprint share one transaction under an advisory lock, so two sessions launching at once load it once. The cost: whatever the person did in the demo is discarded by an update that changes it, and the demo's ledger restarts as a new chain, as every reseed does. Their own projects are separate orgs and are never touched. Keeping the old demo state was the alternative, and it is what broke the demo.
