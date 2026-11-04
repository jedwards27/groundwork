# 0009: One web app, served by the API, on Uber's Base Web

**Status:** accepted (Nov 3, 2026). Replaces the web half of ADR 0001 and the two-machine layout in ADR 0007.

## Context

Groundwork had two web UIs. Mission Control was a Next.js app whose server held the API token and forwarded an allowlist of API paths. The plugin had its own page, HTML that FastAPI rendered on 127.0.0.1, because the plugin's only prerequisite is uv and it can't ship Node. The two looked and behaved differently.

Jude wanted:
- one app, with the plugin page's home (what needs you, projects, recent runs) and Mission Control's project view;
- no persona picker;
- a sparse default view, with details behind tabs, drawers, accordions, tooltips and filters;
- Base Web, Uber's open-source design system (MIT). Starlink and eero have not published theirs.

## Options

1. **Keep Next.js, export it as static files.** Static export can't serve project URLs without knowing them at build time, and the Next.js server routes (token proxy, demo sign-in, admin) existed only because the API lived on another origin.
2. **Keep two apps and share a look.** Two code paths for approvals, drafts and the ledger, which is what this change is meant to end.
3. **A page app the API serves.** Vite builds static files; FastAPI serves them and the API (under `/api`) from one origin, hosted and on a person's computer.

## Decision

Option 3.

- **One origin, one process.** `api/server.py` mounts the API at `/api`, serves `web/dist` for every other path, adds the security headers (a content security policy that allows inline styles, because Base Web's styling engine writes them at runtime), and, on a person's computer, the plugin's hand-off and guard routes. The hosted demo becomes one Fly machine.
- **The cookie is the session.** The API reads its signed token from an HttpOnly cookie as well as a bearer header. A state change that rides on the cookie must be JSON and carry this app's Origin. On a person's computer, the server answers only to 127.0.0.1 and localhost.
- **A viewer can hold several orgs.** A hosted visitor has one (their sandbox). A person's computer has one per project, because each local project is its own org with its own ledger. A request picks the org from its project, run or action, and still runs in exactly one org's session under row-level security.
- **The demo has one person.** Lake Mariner's lead is its only approver, legal asks included, and a visitor is signed in as them. Routing legal asks to counsel stays tested on a project that names counsel.
- **Base Web, React 19.** Base Web 18 declares React 18 or later; its popover, tooltip, select and layer code doesn't use the APIs React 19 removed, and a spike rendered every component used here. Base Web ships an old copy of React's types, so `package.json` overrides it with one copy.

## Consequences

- The plugin bundle carries the built web app (static files, about 1 MB) and still needs only uv.
- Uber says it is "limiting our engagement" with Base Web while still mirroring internal development; a fork or a swap to plain components is possible later, since the app uses about fifteen of them.
- Node is needed only to build the web app, not to run Groundwork.
- `docs/HOSTING.md` describes one machine, and ADR 0007 has an update note for the change. The hosted demo has run this way since Nov 3, 2026.
