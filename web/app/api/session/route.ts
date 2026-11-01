// Demo personas. GET: who am I (or 401). POST {person, fresh?}: log in as a seeded persona. The API
// only allows this when GROUNDWORK_DEMO_LOGIN is on. The current token goes along, so with sandboxes
// on a visitor switching persona stays in their own sandbox; `fresh` starts over in a new one.
import { API, apiFetch, setToken } from "@/lib/server";

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
  const { person, fresh } = (await req.json()) as { person: string; fresh?: boolean };
  const res = await apiFetch("auth/demo-login", { method: "POST", body: JSON.stringify({ person, fresh: !!fresh }) });
  if (!res.ok) return Response.json(await res.json().catch(() => ({})), { status: res.status });
  const data = (await res.json()) as { token: string; ttl_hours: number; name: string; person: string };
  await setToken(req, data.token, data.ttl_hours);
  return Response.json({ person: data.person, name: data.name });
}
