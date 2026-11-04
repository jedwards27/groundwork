// The API lives on the same origin, under /api. The browser sends the session cookie itself; the
// page's scripts never see a token.
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? res.statusText);
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export async function get<T>(path: string): Promise<T> {
  return unwrap<T>(await fetch(`/api/${path}`, { cache: "no-store", credentials: "same-origin" }));
}

// State changes are JSON from this page, which is how the API tells them from a forged request.
export async function send<T>(method: "POST" | "PUT", path: string, body?: unknown, extra?: Record<string, string>): Promise<T> {
  return unwrap<T>(
    await fetch(`/api/${path}`, {
      method,
      credentials: "same-origin",
      headers: { "content-type": "application/json", ...extra },
      body: JSON.stringify(body ?? {}),
    }),
  );
}

export function stream(path: string): EventSource {
  return new EventSource(`/api/${path}`);
}
