// Same-origin proxy to the Groundwork API. Adds the persona's bearer token from an httpOnly cookie,
// passes Last-Event-ID through, and streams server-sent events without buffering.
import { NextRequest } from "next/server";
import { allowed, apiFetch } from "@/lib/server";

export const dynamic = "force-dynamic";

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const path = (await ctx.params).path.join("/");
  if (!allowed(path)) return Response.json({ detail: "not proxied" }, { status: 404 });
  const headers = new Headers();
  const lei = req.headers.get("last-event-id");
  if (lei) headers.set("last-event-id", lei);
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.text();
  if (body) headers.set("content-type", "application/json");
  let res: Response;
  try {
    res = await apiFetch(`${path}${req.nextUrl.search}`, { method: req.method, headers, body });
  } catch {
    return Response.json({ detail: "The Groundwork API is not reachable. Is `make api` running?" }, { status: 502 });
  }
  const out = new Headers({ "cache-control": "no-store" });
  const ct = res.headers.get("content-type");
  if (ct) out.set("content-type", ct);
  if (ct?.startsWith("text/event-stream")) out.set("x-accel-buffering", "no");
  return new Response(res.body, { status: res.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
