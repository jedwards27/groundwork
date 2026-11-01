// Demo controls. Reset: with sandboxes on (hosted), start over in a fresh private sandbox, which any
// persona may do since it touches only their own copy; otherwise reload the shared fixture with the
// admin token, which only this server holds, and only for a signed-in approver. Tamper (local only;
// the API refuses it when hosted): edit one ledger entry in the caller's org the way an operator with
// owner credentials could; approvers only.
import { API, apiFetch, setToken } from "@/lib/server"; // also loads the repo .env

export const dynamic = "force-dynamic";

export async function POST(req: Request, ctx: { params: Promise<{ action: string }> }): Promise<Response> {
  const { action } = await ctx.params;
  if (action !== "reset" && action !== "tamper") return Response.json({ detail: "unknown action" }, { status: 404 });
  const me = await apiFetch("me");
  if (!me.ok) return Response.json({ detail: "choose a demo persona first" }, { status: 401 });
  const who = (await me.json()) as { person: string; approver?: boolean };
  const health = (await (await fetch(`${API}/health`, { cache: "no-store" })).json()) as { sandboxes?: boolean };

  if (action === "reset" && health.sandboxes) {
    const res = await apiFetch("auth/demo-login", { method: "POST", body: JSON.stringify({ person: who.person, fresh: true }) });
    if (!res.ok) return Response.json(await res.json().catch(() => ({})), { status: res.status });
    const data = (await res.json()) as { token: string; ttl_hours: number };
    await setToken(req, data.token, data.ttl_hours);
    return Response.json({ sandbox: "new" });
  }

  if (!who.approver) return Response.json({ detail: "only an approver can reset the site or edit the ledger" }, { status: 403 });
  const tokenValue = process.env.GROUNDWORK_ADMIN_TOKEN;
  if (!tokenValue) return Response.json({ detail: "GROUNDWORK_ADMIN_TOKEN is not set" }, { status: 403 });
  const res = await apiFetch(`admin/${action}`, { method: "POST", headers: { "x-admin-token": tokenValue } });
  return Response.json(await res.json().catch(() => ({})), { status: res.status });
}
