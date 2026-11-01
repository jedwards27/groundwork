// Browser-side API access, always through the same-origin proxy at /api/gw.
import createClient from "openapi-fetch";
import type { paths } from "./api-types";

export const api = createClient<paths>({ baseUrl: "/api/gw" });

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
  return unwrap<T>(await fetch(`/api/gw/${path}`, { cache: "no-store" }));
}

export async function send<T>(method: "POST" | "PUT", path: string, body?: unknown): Promise<T> {
  return unwrap<T>(
    await fetch(`/api/gw/${path}`, {
      method,
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

export async function local<T>(path: string, method: "GET" | "POST" = "GET", body?: unknown): Promise<T> {
  return unwrap<T>(
    await fetch(path, {
      method,
      cache: "no-store",
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    }),
  );
}
