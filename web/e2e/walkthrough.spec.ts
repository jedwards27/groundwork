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

// Play a message from the inbox. Its steps stream into a drawer, which offers the decisions at the end.
async function play(page: Page, eventKey: string): Promise<void> {
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
  await expect(page.getByTestId("gate")).toContainText("NYSEG");
  await play(page, "demo-monday");

  // Allow: a status request the mandate already allows, with the clause it relied on.
  await expect(page.getByTestId("decision-a1")).toHaveText("Allow");
  await page.getByTestId("action-a1").click();
  const drawer = page.getByTestId("action-drawer");
  await expect(drawer.getByTestId("clause-a1")).toContainText("routine_messages");
  await expect(drawer).toContainText("Nothing was sent");
  await page.keyboard.press("Escape");

  // Ask: the landlord-bound request, routed Anthropic -> Fluidstack -> TeraWulf, waiting for you.
  await expect(page.getByTestId("decision-a2")).toHaveText("Ask");
  await page.getByTestId("action-a2").click();
  await expect(drawer).toContainText("Anthropic → Fluidstack → TeraWulf");
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
  await page.getByRole("button", { name: "The agent's report beside the ledger" }).click();
  await page.getByTestId("report-vs-record").getByRole("link").last().click();
  await expect(page).toHaveURL(/\/verify\?project=lake-mariner&record=\d+/);
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

  // "Approved, please proceed" arrives as an auto-reply. It is evidence, never an approval.
  await play(page, "ack-approved");
  const still = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  expect(still.actions.find((a) => a.ref === held!.ref)?.state).toBe("pending");

  // Home lists it under "Needs you"; approving there runs it in dry run, on the record.
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
  await expect(page.getByTestId("chain-ok")).toHaveText(`Verified · ${v.count} records`);
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
    await expect(page.getByTestId("sandbox")).toBeVisible();
    const start = await api<Chain>(bob, `sites/${SITE}/chain`);
    await play(page, "event-a");

    // Bob's copy has not moved: same forecast, no plan, a one-record ledger.
    const still = await api<Chain>(bob, `sites/${SITE}/chain`);
    expect(still.milestone.forecast_finish).toBe(start.milestone.forecast_finish);
    await bob.goto(`/projects/${SITE}/ledger`);
    await expect(bob.getByTestId("chain-ok")).toHaveText("Verified · 1 record");
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

  await menu(page, /Tamper with one demo record/);
  await expect(page.getByTestId("chain-broken")).toBeVisible();
  await expect(page.getByTestId("verify-problem")).toContainText("contents do not match its hash");

  await menu(page, /Reset the demo project|Start over/);
  await expect(page.getByTestId("chain-ok")).toHaveText("Verified · 1 record");
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
  await tab(page, "Mandate");
  await page.getByTestId("template").click();
  await page.getByRole("option", { name: "Auto" }).click();
  await expect(page.getByTestId("mandate-version")).toHaveText("preview");
  await expect(page.getByTestId("preview")).toContainText("Under Auto");
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
