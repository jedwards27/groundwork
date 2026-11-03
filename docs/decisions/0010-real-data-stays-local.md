# 0010: Real data stays on your computer; the hosted copy is the demo

**Status:** accepted (Nov 3, 2026).

## Context

The hosted demo signs every visitor in as the demo's one person, in a private copy that is deleted after 12 hours (ADR 0007). That suits anyone trying the demo. It doesn't suit a real project: there are no accounts, so nothing ties a project to a person beyond one browser's cookie, and a real project's mail, schedule and people would sit on a server the person doesn't control.

Two ways to hold real data were on the table:
1. **Add sign-in to the hosted app.** Google sign-in was built on a branch (`v1/google-sign-in`). Real data then lives on the hosted server, behind accounts.
2. **Keep real data on the person's computer.** The plugin and `make dev` already run the whole system locally: the API, the web app, Postgres and the ledger.

## Decision

Option 2 for the prototype.

- **Real projects run locally:** the Claude plugin (embedded Postgres under `~/.groundwork`, the web app on 127.0.0.1) or `make dev` (local Postgres). The README's "Keep your data on your laptop" section is the how-to.
- **The hosted copy is the demo.** It holds only the synthetic and public Lake Mariner fixture and whatever a visitor types into their private copy, deleted with it. Its New project form says so and points real projects to the local install.
- **No identity provider in the prototype.** The Google sign-in branch is parked, not merged.

## Consequences

- No accounts, passwords or OAuth clients to run or secure, and no customer data on Fly or Neon.
- What leaves a person's machine is what `docs/DATA-BOUNDARY.md` lists: with the plugin, only what their own Claude session reads and what Groundwork's tools return to it; with `make dev`, model calls only when they set `ANTHROPIC_API_KEY`.
- One person per install. Sharing a project's approvals across a team needs a hosted, multi-user version: sign-in through an identity provider, one org per customer, and the same row-level security the sandboxes already use. That is the step after the prototype.
