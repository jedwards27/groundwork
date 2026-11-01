// Demo personas. GET: who am I (or 401). POST {person}: log in as a seeded persona. The API only
// allows this when GROUNDWORK_DEMO_LOGIN is on; the token is kept in an httpOnly cookie.
import { cookies } from "next/headers";
import { API, TOKEN_COOKIE, apiFetch } from "@/lib/server";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  try {
    const [me, personas, health] = await Promise.all([
      apiFetch("me"),
      fetch(`${API}/auth/personas`, { cache: "no-store" }),
      fetch(`${API}/health`, { cache: "no-store" }),
    ]);
    return Response.json({
      me: me.ok ? await me.json() : null,
      personas: personas.ok ? await personas.json() : [],
      health: health.ok ? await health.json() : null,
    });
  } catch {
    return Response.json({ me: null, personas: [], health: null, error: "API not reachable" }, { status: 502 });
  }
}

export async function POST(req: Request): Promise<Response> {
  const { person } = (await req.json()) as { person: string };
  const res = await fetch(`${API}/auth/demo-login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ person }),
    cache: "no-store",
  });
  if (!res.ok) return Response.json(await res.json().catch(() => ({})), { status: res.status });
  const data = (await res.json()) as { token: string; ttl_hours: number; name: string; person: string };
  (await cookies()).set(TOKEN_COOKIE, data.token, {
    httpOnly: true,
    sameSite: "lax",
    // Secure whenever the browser reached us over HTTPS (directly or through a proxy); plain HTTP
    // on localhost would otherwise drop the cookie in some browsers.
    secure: new URL(req.url).protocol === "https:" || req.headers.get("x-forwarded-proto") === "https",
    path: "/",
    maxAge: data.ttl_hours * 3600,
  });
  return Response.json({ person: data.person, name: data.name });
}
