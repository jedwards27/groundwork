// Server-only helpers for the route handlers. The browser never sees a token or the admin key.
import fs from "node:fs";
import path from "node:path";
import { cookies } from "next/headers";

// One .env for the whole repo. The web app runs from web/ (or from the repo root in some setups),
// so look for the repo's .env next to backend/. Variables already set in the environment win.
function loadRepoEnv(): void {
  for (const dir of [path.resolve(process.cwd(), ".."), process.cwd(), path.resolve(process.cwd(), "groundwork")]) {
    const file = path.join(dir, ".env");
    if (!fs.existsSync(file) || !fs.existsSync(path.join(dir, "backend"))) continue;
    for (const line of fs.readFileSync(file, "utf8").split("\n")) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
    return;
  }
}
loadRepoEnv();

export const API = process.env.GROUNDWORK_API_URL ?? "http://localhost:8000";
export const TOKEN_COOKIE = "gw_token";

// Only these API paths are reachable through the proxy. /auth and /admin stay server-side.
const ALLOWED = [/^health$/, /^me$/, /^sites(\/.*)?$/, /^runs\/[0-9a-f-]+(\/(stream|plans|replay))?$/, /^actions\/[0-9a-f-]+\/approvals$/];

export function allowed(path: string): boolean {
  return ALLOWED.some((re) => re.test(path));
}

export async function token(): Promise<string | undefined> {
  return (await cookies()).get(TOKEN_COOKIE)?.value;
}

// Keep the API's token in an httpOnly cookie the page's scripts cannot read. Secure whenever the
// browser reached us over HTTPS (directly or through a proxy); plain HTTP on localhost would
// otherwise drop the cookie in some browsers.
export async function setToken(req: Request, token: string, ttlHours: number): Promise<void> {
  (await cookies()).set(TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: new URL(req.url).protocol === "https:" || req.headers.get("x-forwarded-proto") === "https",
    path: "/",
    maxAge: ttlHours * 3600,
  });
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const t = await token();
  if (t) headers.set("authorization", `Bearer ${t}`);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  return fetch(`${API}/${path}`, { ...init, headers, cache: "no-store" });
}
