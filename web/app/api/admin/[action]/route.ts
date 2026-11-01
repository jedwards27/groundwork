// Demo controls that need the admin token, which only this server holds: reset the site to its
// fixture, or (local only) edit one ledger entry the way an operator with owner credentials could.
import { API } from "@/lib/server"; // also loads the repo .env

export const dynamic = "force-dynamic";

export async function POST(_req: Request, ctx: { params: Promise<{ action: string }> }): Promise<Response> {
  const { action } = await ctx.params;
  if (action !== "reset" && action !== "tamper") return Response.json({ detail: "unknown action" }, { status: 404 });
  const tokenValue = process.env.GROUNDWORK_ADMIN_TOKEN;
  if (!tokenValue) return Response.json({ detail: "GROUNDWORK_ADMIN_TOKEN is not set" }, { status: 403 });
  const res = await fetch(`${API}/admin/${action}`, {
    method: "POST",
    headers: { "x-admin-token": tokenValue },
    cache: "no-store",
  });
  return Response.json(await res.json().catch(() => ({})), { status: res.status });
}
