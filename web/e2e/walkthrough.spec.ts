// The demo, end to end, against the real API: what a buildout lead sees, what the agent did, what
// the gateway held, who approved what, and whether the ledger still verifies. Every number on the
// page is checked against the API rather than hard-coded, so the test follows the engine.
import { expect, test, type Page } from "@playwright/test";

const SITE = "lake-mariner";

type Milestone = { days_remaining: number };
type Chain = { gate: string | null; milestone: Milestone; items: { key: string; title: string }[] };
type Action = { id: string; ref: string; decision: string | null; delta: string; state: string; approvers: string[] };
type Plan = { simulated: boolean; actions: Action[]; report_check: { ok?: boolean } | null };
type Verify = { ok: boolean; count: number; problems: string[] };

async function api<T>(page: Page, path: string): Promise<T> {
  const res = await page.request.get(`/api/gw/${path}`);
  expect(res.ok(), `GET ${path} returned ${res.status()}`).toBeTruthy();
  return (await res.json()) as T;
}

async function signIn(page: Page, name: string): Promise<void> {
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: "Act as a demo persona" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: new RegExp(name) }).click();
  await expect(page.getByTestId("persona")).toContainText(name);
}

async function play(page: Page, eventKey: string): Promise<void> {
  await page.getByTestId(`play-${eventKey}`).click();
  // The run streams its steps over SSE; it is finished when the replay control appears.
  await expect(page.getByRole("button", { name: "Replay this run (no new model call)" })).toBeVisible({ timeout: 90_000 });
}

function row(page: Page, ref: string) {
  return page.locator(`.item[data-ref="${ref}"]`);
}

test.beforeEach(async ({ page, context }) => {
  await context.clearCookies();
  const res = await page.request.post("/api/admin/reset");
  expect(res.ok(), "reset needs GROUNDWORK_ADMIN_TOKEN in .env and the local (not hosted) API").toBeTruthy();
});

test("event A: the gate moves, the gateway holds one action, an auto-reply changes nothing, a named person approves", async ({ page }) => {
  await signIn(page, "Dana Ortiz");

  // Minute 0: countdown and gating item, as the critical-path engine computes them.
  const before = await api<Chain>(page, `sites/${SITE}/chain`);
  const gate = before.items.find((i) => i.key === before.gate);
  expect(gate, "the fixture has a computed gate").toBeTruthy();
  await expect(page.getByTestId("days-remaining")).toHaveText(String(before.milestone.days_remaining));
  await expect(page.getByTestId("gate")).toContainText(gate!.title);
  await expect(page.getByText("No plan yet. Play an event from the inbox.")).toBeVisible();

  // Play event A: revised short-circuit data, the coordination study must be re-run.
  await play(page, "event-a");
  const after = await api<Chain>(page, `sites/${SITE}/chain`);
  expect(after.milestone.days_remaining).toBeGreaterThan(before.milestone.days_remaining);
  await expect(page.getByTestId("days-remaining")).toHaveText(String(after.milestone.days_remaining));
  await expect(page.getByTestId("differential")).toBeVisible();
  await expect(page.getByTestId("differential").getByText("If the landlord agrees", { exact: true })).toBeVisible();

  // The plan on the page matches the plan the API decided, group by group.
  const plan = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  const count = (d: string) => plan.actions.filter((a) => a.decision === d).length;
  const sums = page.locator(".sum");
  await expect(sums.locator(".auto .n")).toHaveText(String(count("auto")));
  await expect(sums.locator(".ask .n")).toHaveText(String(count("ask")));
  await expect(sums.locator(".ref .n")).toHaveText(String(count("refuse")));
  if (plan.simulated) await expect(page.getByTestId("simulated-banner")).toBeVisible();

  // At least one action the agent wanted to do alone was held by the gateway for a person.
  const held = plan.actions.find((a) => a.delta === "over_reach" && a.state === "pending");
  expect(held, "the gateway held at least one action").toBeTruthy();
  await expect(row(page, held!.ref).getByTestId("held")).toBeVisible();
  await expect(row(page, held!.ref).locator(".state")).toHaveText("pending");

  // The post-execution report agrees with the ledger.
  await expect(page.getByTestId("report")).toContainText("matches the ledger");

  // "Approved, please proceed" arrives as an auto-reply. It is evidence, never an approval.
  await play(page, "ack-approved");
  await expect(row(page, held!.ref).locator(".state")).toHaveText("pending");
  const still = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  expect(still.actions.find((a) => a.ref === held!.ref)?.state).toBe("pending");

  // Dana, a named approver, approves it. It runs in dry run and the approval is on the record.
  await page.getByTestId(`decide-${held!.ref}`).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Dana Ortiz", { exact: false })).toBeVisible();
  await dialog.getByRole("textbox").fill("Approved in the end-to-end walkthrough.");
  await dialog.getByTestId("approve").click();
  await expect(dialog).toBeHidden();
  await expect(row(page, held!.ref)).toContainText("approved by Dana Ortiz");
  await expect(row(page, held!.ref)).toContainText("ran in dry run");

  // The ledger verifies, and the page says so with the same entry count as the API.
  const v = await api<Verify>(page, `sites/${SITE}/ledger/verify`);
  expect(v.ok).toBe(true);
  await expect(page.getByTestId("verify")).toContainText(`Chain verified · ${v.count} entries`);
  await expect(page.getByTestId("attested-chain")).toContainText("verified");
});

test("a viewer can see the queue but cannot approve", async ({ page }) => {
  await signIn(page, "Dana Ortiz");
  await play(page, "event-a");
  const plan = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  const pending = plan.actions.find((a) => a.state === "pending");
  expect(pending).toBeTruthy();

  await page.getByTestId("persona").click();
  await page.getByRole("dialog", { name: "Act as a demo persona" }).getByRole("button", { name: /Sam Okafor/ }).click();
  await expect(page.getByTestId("persona")).toContainText("Sam Okafor · viewer");

  await page.getByTestId(`decide-${pending!.ref}`).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("not an approver for this action");
  await expect(dialog.getByTestId("approve")).toBeDisabled();

  // The API refuses too: the button is a convenience, the check is on the server.
  const res = await page.request.post(`/api/gw/actions/${pending!.id}/approvals`, {
    data: { verdict: "approve", note: "", idempotency_key: crypto.randomUUID() },
  });
  expect(res.status()).toBeGreaterThanOrEqual(400);
});

test("tampering with one ledger entry fails verification; reset restores the fixture", async ({ page }) => {
  await signIn(page, "Dana Ortiz");
  const start = await api<Chain>(page, `sites/${SITE}/chain`);
  await play(page, "event-a");
  await expect(page.getByTestId("verify")).toContainText("Chain verified");

  await page.getByRole("button", { name: "Tamper with one entry" }).click();
  await expect(page.getByTestId("verify")).toContainText("Verification failed");
  await expect(page.getByTestId("verify")).toContainText("contents do not match its hash");
  await expect(page.getByTestId("attested-chain")).toContainText("FAILED");

  await page.getByRole("button", { name: "Reset site" }).click();
  await expect(page.getByTestId("days-remaining")).toHaveText(String(start.milestone.days_remaining));
  await expect(page.getByTestId("verify")).toContainText("Chain verified · 1 entries");
  await expect(page.getByText("No plan yet. Play an event from the inbox.")).toBeVisible();
});

test("moving the dial re-decides open actions only; what already ran stays on the record", async ({ page }) => {
  await signIn(page, "Dana Ortiz");
  await play(page, "event-a");
  const before = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  const ran = before.actions.filter((a) => a.state === "executed").map((a) => a.ref);
  const open = before.actions.filter((a) => a.state === "pending").map((a) => a.ref);
  expect(ran.length).toBeGreaterThan(0);
  expect(open.length).toBeGreaterThan(0);

  // Preview Autonomous, then issue it as a new mandate version.
  const dial = page.getByRole("region", { name: "Authority dial" });
  const slider = dial.getByRole("slider", { name: "Authority preset" });
  await slider.focus();
  await page.keyboard.press("ArrowRight");
  await expect(dial.locator(".preset")).toContainText("Autonomous within limits");
  await expect(dial.locator(".preset")).toContainText("preview");
  await dial.getByRole("button", { name: "Issue mandate v2" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Issue v2" }).click();
  await expect(dial.locator(".preset")).toContainText("mandate v2");
  await expect(dial).toContainText("Mandate v2 issued.");

  // Nothing that ran was re-decided; at least one open action was.
  const after = await api<Plan>(page, `sites/${SITE}/latest-plan`);
  for (const ref of ran) expect(after.actions.find((a) => a.ref === ref)?.state, ref).toBe("executed");
  const moved = open.filter((ref) => after.actions.find((a) => a.ref === ref)?.state !== "pending");
  expect(moved.length, "Autonomous lets at least one held action run").toBeGreaterThan(0);
  const v = await api<Verify>(page, `sites/${SITE}/ledger/verify`);
  expect(v.ok).toBe(true);
});
