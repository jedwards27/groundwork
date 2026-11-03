// Dates in the API are ISO strings (YYYY-MM-DD). Parse them as local calendar dates, never as UTC
// instants, so "2027-01-12" never renders as January 11.
export function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null;
  const [y, m, d] = s.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function fmt(s: string | null | undefined, withYear = false): string {
  const d = parseDate(s);
  if (!d) return "—";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...(withYear ? { year: "numeric" } : {}) });
}

export function fmtLong(s: string | null | undefined): string {
  const d = parseDate(s);
  return d ? d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }) : "—";
}

export function daysBetween(a: string | null | undefined, b: string | null | undefined): number {
  const da = parseDate(a);
  const db = parseDate(b);
  if (!da || !db) return 0;
  return Math.round((db.getTime() - da.getTime()) / 86_400_000);
}

export function money(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "";
  return "$" + Math.round(cents / 100).toLocaleString("en-US");
}

export function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export const PROVENANCE_LABEL: Record<string, string> = {
  public: "public",
  synthetic: "synthetic",
  assumption_to_verify: "assumption to verify",
};

// The API keeps its own values (auto / ask / refuse, autonomous); the page shows the product's words.
export const DECISION_LABEL: Record<string, string> = { auto: "allow", ask: "ask", refuse: "deny" };

export const TEMPLATE_LABEL: Record<string, string> = { supervised: "Supervised", standard: "Standard", autonomous: "Auto" };

// Gateway reasons are written over keys (the gateway is generic); show names instead.
export function humanize(text: string, names: Record<string, string>): string {
  const keys = Object.keys(names).sort((a, b) => b.length - a.length);
  if (!keys.length) return text;
  const re = new RegExp(`\\b(${keys.map((k) => k.replace(/[-]/g, "\\-")).join("|")})\\b`, "g");
  return text.replace(re, (k) => names[k] ?? k);
}

// "3 min ago", "2 h ago", "Nov 2" for timestamps.
export function ago(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 24 * 60) return `${Math.round(mins / 60)} h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function lateness(days: number | null | undefined): { text: string; late: boolean } {
  const d = days ?? 0;
  if (d > 0) return { text: `${d} days late`, late: true };
  if (d < 0) return { text: `${-d} days early`, late: false };
  return { text: "on time", late: false };
}

// The demo project. Its messages have hand-written plans, so the app can play them without Claude;
// a project of your own is planned by Claude through the plugin.
export const DEMO_PROJECT = "lake-mariner";
