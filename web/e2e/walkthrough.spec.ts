// The demo, end to end, against the real API: what a project lead sees, what the agent did, what
// the gateway held, who approved what, and whether the ledger still verifies. Numbers on the page
// are checked against the API rather than hard-coded, so the test follows the engine.
import { expect, test, type Page } from "@playwright/test";

const SITE = "lake-mariner";

type Chain = { milestone: { forecast_finish: string; days_remaining: number } };
type Action = { id: string; ref: string; decision: string | null; delta: string; state: string };
type Plan = { simulated: boolean; actions: Action[]; report_check: { ok?: boolean } | null };
type Verify = { ok: boolean; count: number };
type Health = { hosted?: boolean; sandboxes?: boolean };

async function api<T>(page: Page, path: string): Promise<T> {
  const res = await page.request.get(`/api/${path}`);
  expect(res.ok(), `GET ${path} returned ${res.status()}`).toBeTruthy();
  return (await res.json()) as T;
}

async function health(page: Page): Promise<Health> {
  return ((await (await page.request.get("/api/session")).json()) as { health: Health }).health;
}

// There is no one to choose: opening the app signs a visitor in as the demo's lead.
async function open(page: Page, path = "/"): Promise<void> {
  await page.goto(path);
  await expect(page.getByTestId("you")).toBeVisible();
}

async function tab(page: Page, name: string): Promise<void> {
  await page.getByRole("tab", { name: new RegExp(`^${name}`) }).click();
}

// The demo's extra messages aren't in the inbox until played; the tests play them through the API.
const EXTRAS = new Set(["event-a", "event-b", "event-b-expedite", "injection-expedite-po", "injection-date-change"]);

// Play a message from the inbox. Its steps stream into a drawer, which offers the decisions at the end.
async function play(page: Page, eventKey: string): Promise<void> {
  if (EXTRAS.has(eventKey)) {
    const res = await page.request.post(`/api/sites/${SITE}/events`, { data: { event: eventKey }, headers: { origin: new URL(page.url()).origin } });
    expect(res.ok(), `playing ${eventKey} returned ${res.status()}`).toBeTruthy();
    const { run_id } = (await res.json()) as { run_id: string };
    await expect.poll(async () => (await api<{ status: string }>(page, `runs/${run_id}`)).status, { timeout: 90_000 }).toBe("done");
    await page.goto(`/projects/${SITE}/actions`);
    return;
  }
  await tab(page, "Inbox");
  await page.getByTestId(`play-${eventKey}`).click();
  const drawer = page.getByTestId("message-drawer");
  await expect(drawer.getByTestId("see-actions")).toBeVisible({ timeout: 90_000 });
  await drawer.getByTestId("see-actions").click();
  await expect(page).toHaveURL(new RegExp(`/projects/${SITE}/actions$`));
}

async function menu(page: Page, item: RegExp): Promise<void> {
  await page.getByTestId("you").click();
  await page.getByRole("option", { name: item }).click();
}

const ui = (page: Page, id: string) => page.locator(`[data-testid="${id}"]`);

// Every test starts signed out on a clean copy of the demo. With sandboxes, signing in already gives
// a fresh private copy. Without them, reload the shared demo project as its lead.
test.beforeEach(async ({ page, context, baseURL }) => {
  await context.clearCookies();
  if ((await health(page)).sandboxes) return;
  expect((await page.request.post("/api/session")).ok(), "demo sign-in is on").toBeTruthy();
  const res = await page.request.post("/api/demo/reset", { headers: { origin: baseURL! } });
  expect(res.ok(), `reset returned ${res.status()}`).toBeTruthy();
  await context.clearCookies();
});

test("the two-minute demo: Allow, Ask through the lessee, Deny, the report beside the ledger, and a record anyone can verify", async ({ page }) => {
  await open(page, `/projects/${SITE}`);
  await expect(page.getByTestId("gate")).toContainText("Utility approves the power settings");
  await play(page, "demo-monday");

  // Allow: a status request the mandate already allows, with the clause it relied on.
  await expect(page.getByTestId("decision-a1")).toHaveText("Allow");
  await page.getByTestId("action-a1").click();
  const drawer = page.getByTestId("action-drawer");
  await expect(drawer.getByTestId("clause-a1")).toContainText("routine_messages");
  await expect(drawer).toContainText("Ran:");
  await page.keyboard.press("Escape");

  // Ask: the landlord-bound request, routed Anthropic -> Fluidstack -> TeraWulf, waiting for you.
  await expect(page.getByTestId("decision-a2")).toHaveText("Ask");
  await page.getByTestId("action-a2").click();
  await expect(drawer).toContainText("Anthropic → Fluidstack (tenant) → TeraWulf (landlord)");
  await expect(drawer.getByTestId("approve")).toBeVisible();
  await page.keyboard.press("Escape");

  // Deny: the change order a vendor document told the agent to sign.
  await expect(page.getByTestId("decision-a3")).toHaveText("Deny");
  await page.getByTestId("action-a3").click();
  await expect(drawer.getByTestId("clause-a3")).toContainText("Never: pay, sign, delete");
  await page.keyboard.press("Escape");

  // The report beside the ledger, then one record checked by hash, and a forged copy rejected.
  await expect(page.getByTestId("report-verdict")).toHaveText("Report matches the ledger");
  const plan = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  expect(plan.simulated).toBe(true);
  expect(plan.report_check?.ok).toBe(true);
  await page.getByRole("button", { name: "Report vs. ledger" }).click();
  await page.getByTestId("report-vs-record").getByRole("link").last().click();
  await expect(page).toHaveURL(/\/projects\/lake-mariner\/settings\?record=\d+/);
  await page.getByTestId("verify-run").click();
  await expect(page.getByTestId("verify-verdict")).toHaveText("Match");
  await page.getByRole("button", { name: "Paste the stored record" }).click();
  const box = page.getByTestId("verify-copy");
  await box.fill((await box.inputValue()).replace('"decision": "refuse"', '"decision": "auto"'));
  await page.getByTestId("verify-run").click();
  await expect(page.getByTestId("verify-verdict")).toHaveText("Mismatch");
});

test("event A: the forecast moves, the gateway holds one action, an auto-reply changes nothing, you approve it from home", async ({ page }) => {
  await open(page, `/projects/${SITE}`);
  const before = await api<Chain>(page, `sites/${SITE}/chain`);

  await play(page, "event-a");
  const after = await api<Chain>(page, `sites/${SITE}/chain`);
  expect(after.milestone.days_remaining).toBeGreaterThan(before.milestone.days_remaining);
  await expect(page.getByTestId("lateness")).toContainText("days late");

  // At least one action the agent wanted to do alone was held by the gateway for a person.
  const plan = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  const held = plan.actions.find((a) => a.delta === "over_reach" && a.state === "pending");
  expect(held, "the gateway held at least one action").toBeTruthy();
  await expect(page.getByTestId(`held-${held!.ref}`)).toBeVisible();
  await expect(page.getByTestId("report-verdict")).toHaveText("Report matches the ledger");

  // "Approved, please proceed" arrives as an auto-reply. It is evidence, never an approval, and it
  // plans nothing, so its run ends without next steps to see.
  await tab(page, "Inbox");
  await page.getByTestId("play-ack-approved").click();
  await expect(page.getByTestId("message-drawer").getByTestId("run-done")).toHaveText("Done. No next steps needed.");
  await expect(page.getByTestId("message-drawer").getByTestId("see-actions")).toHaveCount(0);
  await page.keyboard.press("Escape");
  const still = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  expect(still.actions.find((a) => a.ref === held!.ref)?.state).toBe("pending");

  // Home lists it under "Needs you"; approving there runs it, on the record.
  await page.getByTestId("home-link").click();
  await page.getByTestId(`ask-${held!.ref}`).click();
  const ask = page.getByTestId("ask-drawer");
  await expect(ask).toContainText("Mandate clause");
  await ask.getByTestId("approve").click();
  await expect(page.getByTestId(`ask-${held!.ref}`)).toBeHidden();
  const done = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  expect(done.actions.find((a) => a.ref === held!.ref)?.state).toBe("executed");

  // The ledger verifies, and the page says so with the same record count as the API.
  const v = await api<Verify>(page, `sites/${SITE}/ledger/verify`);
  expect(v.ok).toBe(true);
  await page.goto(`/projects/${SITE}/ledger`);
  await expect(page.getByTestId("chain-ok")).toHaveText(`Intact (${v.count} records)`);
});

test("a state change riding on the cookie needs this app's Origin", async ({ page, baseURL }) => {
  await open(page);
  const play = { data: { event: "event-a" } };
  expect((await page.request.post(`/api/sites/${SITE}/events`, play)).status()).toBe(403);
  const ok = await page.request.post(`/api/sites/${SITE}/events`, { ...play, headers: { origin: baseURL! } });
  expect(ok.status()).toBe(202);
});

test("two visitors at once each get a private copy", async ({ page, browser }) => {
  test.skip(!(await health(page)).sandboxes, "sandboxes are off (they are on in the hosted profile)");
  const other = await browser.newContext();
  const bob = await other.newPage();
  try {
    await open(page, `/projects/${SITE}`);
    await open(bob, `/projects/${SITE}`);
    await page.getByTestId("you").click();
    await expect(page.getByTestId("account-menu")).toContainText("(resets in");
    await page.keyboard.press("Escape");
    const start = await api<Chain>(bob, `sites/${SITE}/chain`);
    await play(page, "event-a");

    // Bob's copy has not moved: same forecast, no plan, a one-record ledger.
    const still = await api<Chain>(bob, `sites/${SITE}/chain`);
    expect(still.milestone.forecast_finish).toBe(start.milestone.forecast_finish);
    await bob.goto(`/projects/${SITE}/ledger`);
    await expect(bob.getByTestId("chain-ok")).toHaveText("Intact (1 record)");

    // Bob starting the tutorial starts his copy over; the first visitor's work is untouched.
    const mine = await api<Plan>(page, `sites/${SITE}/latest-plan`);
    await bob.goto("/");
    await bob.getByTestId("tutorial-card-start").click();
    await bob.getByTestId("tutorial-begin").click();
    await expect(bob.getByTestId("tutorial-count")).toHaveText(/1 of 16/);
    const after = await api<Plan>(page, `sites/${SITE}/latest-plan`);
    expect(after.actions.map((a) => a.id)).toEqual(mine.actions.map((a) => a.id));
    expect((await api<Chain>(page, `sites/${SITE}/chain`)).milestone.forecast_finish).not.toBe(start.milestone.forecast_finish);
  } finally {
    await other.close();
  }
});

test("tampering with one ledger record fails verification; reset restores the demo", async ({ page }) => {
  test.skip(!!(await health(page)).hosted, "the hosted profile refuses tampering");
  await open(page, `/projects/${SITE}`);
  await play(page, "event-a");
  await tab(page, "Ledger");
  await expect(page.getByTestId("chain-ok")).toBeVisible();

  await page.getByRole("button", { name: "Try to break it" }).click();
  await page.getByTestId("tamper").click();
  await expect(page.getByTestId("chain-broken")).toBeVisible();
  await expect(page.getByTestId("verify-problem")).toContainText("contents do not match its hash");

  await page.getByTestId("restore").click();
  await expect(page.getByTestId("chain-ok")).toHaveText("Intact (1 record)");
});

test("a new mandate version decides open actions again; what already ran stays on the record", async ({ page }) => {
  await open(page, `/projects/${SITE}`);
  await play(page, "event-a");
  const before = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  const ran = before.actions.filter((a) => a.state === "executed").map((a) => a.ref);
  const open_ = before.actions.filter((a) => a.state === "pending").map((a) => a.ref);
  expect(ran.length).toBeGreaterThan(0);
  expect(open_.length).toBeGreaterThan(0);

  // Preview the Auto template, then issue it as a new mandate version.
  await tab(page, "Settings");
  await page.getByTestId("template").click();
  await page.getByRole("option", { name: "Auto" }).click();
  await expect(page.getByTestId("mandate-version")).toHaveText("preview");
  await expect(page.getByTestId("preview")).toContainText("Previewing Auto");
  await page.getByTestId("issue").click();
  await page.getByTestId("issue-confirm").click();
  await expect(page.getByTestId("mandate-version")).toHaveText("v2");

  // Nothing that ran was decided again; at least one open action was.
  const after = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  for (const ref of ran) expect(after.actions.find((a) => a.ref === ref)?.state, ref).toBe("executed");
  const moved = open_.filter((ref) => after.actions.find((a) => a.ref === ref)?.state !== "pending");
  expect(moved.length, "Auto lets at least one held action run").toBeGreaterThan(0);
  expect((await api<Verify>(page, `sites/${SITE}/ledger/verify`)).ok).toBe(true);
});

async function tutorial(page: Page): Promise<void> {
  await open(page);
  await ui(page, "tutorial-card-start").click();
  await ui(page, "tutorial-begin").click();
}

const TOTAL = 16;
const step = (page: Page, n: number) => expect(ui(page, "tutorial-count")).toHaveText(new RegExp(`${n} of ${TOTAL}`));

// Every click below is a real click: it fails if the tutorial's panel covers what it points at.
async function clickThrough(page: Page): Promise<void> {
  await step(page, 1);
  await expect(ui(page, "tutorial-pointer")).toHaveText("Click Lake Mariner");
  await expect(ui(page, "tutorial-cta")).toContainText("Click Lake Mariner");
  await expect(ui(page, "tutorial").getByRole("button")).toHaveCount(1); // just the close button
  await ui(page, "project-lake-mariner").click();
  await step(page, 2);
  await expect(page.locator('[data-tour="on"]')).toHaveAttribute("data-testid", "summary");
  await ui(page, "gate").click();
  await step(page, 3);
  await expect(ui(page, "path").locator("li")).not.toHaveCount(0);
  await ui(page, "tutorial-next").click();
  await step(page, 4);
  await expect(ui(page, "why-drawer")).toBeHidden(); // the step closed the drawer it no longer needs
  await expect(page.locator('[data-tour="on"]')).toHaveAttribute("data-testid", "graph");
  await ui(page, "tutorial-next").click();
  await step(page, 5);
  await ui(page, "tab-inbox").click();
  await step(page, 6);
  await ui(page, "play-demo-monday").click();
  await step(page, 7);
  // A demo message plays its written plan one step at a time, labeled as a simulated agent.
  await expect(ui(page, "simulated-run")).toBeVisible();
  await expect(ui(page, "run-done")).toBeVisible({ timeout: 90_000 });
  await expect(ui(page, "tutorial-cta")).toHaveText("Done. Click See the 3 next steps.");
  await ui(page, "see-actions").click();
  await step(page, 8);
  await expect(ui(page, "decision-a3")).toHaveText("Deny");

  // Back goes over what you've seen, past the run's drawer, with Next instead of the click.
  await ui(page, "tutorial-back").click();
  await step(page, 6);
  await expect(page).toHaveURL(new RegExp(`/projects/${SITE}/inbox$`));
  await expect(ui(page, "tutorial-cta")).toBeHidden();
  await ui(page, "tutorial-next").click();
  await step(page, 7);
  await ui(page, "tutorial-next").click();
  await step(page, 8);
  await expect(page).toHaveURL(new RegExp(`/projects/${SITE}/actions$`));

  await ui(page, "tutorial-next").click();
  await step(page, 9);
  await ui(page, "action-a2").click();
  await step(page, 10);
  // What would go out leads the drawer, above Approve.
  const drawer = ui(page, "action-drawer");
  await expect(drawer.getByTestId("outgoing")).toContainText("Please ask TeraWulf to confirm the power-on date");
  await drawer.getByTestId("approve").click();
  await step(page, 11);
  await expect(drawer).toBeHidden();
  await ui(page, "tab-settings").click();
  await step(page, 12);
  await ui(page, "tab-ledger").click();
  await step(page, 13);
  await expect(ui(page, "chain-ok")).toHaveText(/Intact/);
  await ui(page, "home-link").click();
  await step(page, 14);
  // A second email played in the background while you looked at the ledger: home has something new.
  await expect(page.locator('[data-testid^="ask-b"]')).toHaveCount(3, { timeout: 90_000 });
  await expect(ui(page, "runs").getByTestId("run")).toHaveCount(2);
  await ui(page, "tutorial-next").click();
  // No model ran in the tour; it points at where your own API key goes.
  await expect(ui(page, "tutorial-title")).toHaveText("Want to see Claude plan?");
  await ui(page, "tutorial-next").click();
  await expect(ui(page, "tutorial-title")).toHaveText("That's the whole tour!");
  await expect(ui(page, "tutorial-finish")).toBeVisible();
  // In the browser (not the plugin's own app), the tour points to the plugin download.
  await expect(ui(page, "tutorial-finish").getByRole("link", { name: "download the plugin" })).toHaveAttribute(
    "href",
    "https://github.com/jedwards27/groundwork/releases/latest/download/groundwork-plugin.zip",
  );
  if ((await health(page)).hosted) {
    // The demo doesn't create projects: the way on is installing it.
    await expect(ui(page, "tutorial-install")).toHaveAttribute("href", /#try-it-in-the-claude-app-the-plugin$/);
    await ui(page, "tutorial-done").click();
    await expect(ui(page, "tutorial")).toBeHidden();
    return;
  }
  await ui(page, "tutorial-new-project").click();
  await expect(page).toHaveURL(/\/projects\/new$/);
  await expect(ui(page, "tutorial")).toBeHidden();
}

test("the tutorial: you click through the app yourself, and it ends at your first project", async ({ page }) => {
  test.setTimeout(180_000); // sixteen steps and a background run, slower over the network
  await tutorial(page);
  await clickThrough(page);
  // Finished once, home stops offering it; the account menu still has it.
  await page.getByTestId("home-link").click();
  await expect(ui(page, "projects")).toBeVisible();
  await expect(ui(page, "tutorial-card")).toBeHidden();
});

test("the tutorial fits a narrow window: its panel never covers what it points at", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 575, height: 560 });
  await tutorial(page);
  await clickThrough(page);
});

test("closing the tutorial pauses it; opening it again picks up where you left off", async ({ page }) => {
  await tutorial(page);
  await ui(page, "project-lake-mariner").click();
  await step(page, 2);
  await ui(page, "tutorial-close").click();
  await expect(ui(page, "tutorial")).toBeHidden();
  await expect(ui(page, "tutorial-pointer")).toBeHidden();
  await page.getByTestId("home-link").click();
  await expect(ui(page, "tutorial-card-start")).toHaveText("Resume");
  await page.getByTestId("you").click();
  await expect(page.getByRole("option", { name: new RegExp(`Resume the tutorial \\(2 of ${TOTAL}\\)`) })).toBeVisible();
  await expect(page.getByRole("option", { name: "Start the tutorial over" })).toBeVisible();
  await page.keyboard.press("Escape");
  await ui(page, "tutorial-card-start").click();
  await step(page, 2);
  await expect(page).toHaveURL(/\/projects\/lake-mariner$/);
  await ui(page, "gate").click();
  await step(page, 3);

  // Starting over from the menu closes the panel while it asks.
  await ui(page, "tutorial-next").click();
  await step(page, 4);
  await page.getByTestId("you").click();
  await page.getByRole("option", { name: "Start the tutorial over" }).click();
  await expect(ui(page, "tutorial")).toBeHidden();
  await ui(page, "tutorial-begin").click();
  await step(page, 1);
});

test("with your own API key in the tab, the inbox shows the hard cases for Claude to plan", async ({ page }) => {
  await open(page, `/projects/${SITE}/inbox`);
  for (const k of EXTRAS) await expect(ui(page, `play-${k}`)).toHaveCount(0);
  await menu(page, /Use your own API key/);
  // A made-up key: nothing is played, so it never leaves this page.
  await ui(page, "live-key").fill("sk-ant-test-not-a-real-key-000000000000");
  await ui(page, "live-use").click();
  await expect(ui(page, "live-tag")).toBeVisible();
  for (const k of EXTRAS) await expect(ui(page, `play-${k}`)).toBeVisible();
  await menu(page, /Forget the API key/);
  await expect(ui(page, "live-tag")).toBeHidden();
  for (const k of EXTRAS) await expect(ui(page, `play-${k}`)).toHaveCount(0);
});

test("a new project from the website: check its forecast, then create it", async ({ page }) => {
  await open(page, "/projects/new");
  if ((await health(page)).hosted) {
    // The hosted demo has one made-up project; real ones run on your computer.
    await expect(ui(page, "demo-only")).toBeVisible();
    return;
  }
  await ui(page, "use-example").click();
  await ui(page, "check-forecast").click();
  await expect(ui(page, "project-preview")).toContainText("Waiting on: Cabinets delivered");
  await expect(ui(page, "project-preview")).toContainText("days late");
  await ui(page, "create-project").click();
  await expect(page).toHaveURL(/\/projects\/kitchen-remodel$/);
  await expect(ui(page, "gate")).toContainText("Cabinets delivered");
  await page.getByTestId("home-link").click();
  await expect(ui(page, "project-kitchen-remodel")).toBeVisible();
});

test("every step: the Steps tab lists them all, and the chart can show the whole project", async ({ page }) => {
  await open(page, `/projects/${SITE}`);
  const chain = await api<{ items: { key: string; status: string }[] }>(page, `sites/${SITE}/chain`);
  await ui(page, "range-all").click();
  await expect(ui(page, "schedule-chart")).toHaveAttribute("data-rows", String(chain.items.length));
  await tab(page, "Steps");
  await expect(page).toHaveURL(new RegExp(`/projects/${SITE}/steps$`));
  await expect(ui(page, "steps")).toContainText(`${chain.items.length} steps`);
  // A page at a time: every step is on one of the pages.
  const seen = new Set<string>();
  const collect = async () => {
    for (const id of await page.locator('[data-testid^="step-"]').evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")))) seen.add(String(id).slice(5));
  };
  await collect();
  while (await ui(page, "pager").getByRole("button", { name: /next/i }).isEnabled().catch(() => false)) {
    await ui(page, "pager").getByRole("button", { name: /next/i }).click();
    await collect();
  }
  expect([...seen].sort()).toEqual(chain.items.map((i) => i.key).sort());
  const done = chain.items.filter((i) => i.status === "done").length;
  await page.getByRole("radio", { name: new RegExp(`^Done \\(${done}\\)$`) }).click();
  await expect(ui(page, "steps")).toContainText(`${done} of ${chain.items.length} steps`);
});

test("a new project's steps can be pasted from a spreadsheet", async ({ page }) => {
  await open(page, "/projects/new");
  test.skip(!!(await health(page)).hosted, "the hosted demo doesn't create projects");
  await page.getByRole("button", { name: "Paste steps from a spreadsheet" }).click();
  await ui(page, "paste-steps").fill("Step\tOwner\tStatus\tDue\tWaits on\nPermit issued\tCity permits\tunder way\t2027-01-15\t\nCabinets installed\tBayside Builders\tnot started\t2/1/2027\tPermit issued\nno date\tBayside Builders\t\t\t");
  await ui(page, "paste-add").click();
  await expect(ui(page, "paste-note")).toHaveText("Added 2 steps; skipped 1 row missing a step name or a readable date.");
  await expect(page.locator('input[placeholder="Organization"]').nth(1)).toHaveValue("Bayside Builders");
});
