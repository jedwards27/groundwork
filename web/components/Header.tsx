"use client";
import { fmtLong } from "@/lib/format";
import type { Health, Me, PlanView, SiteView } from "@/lib/types";

export function Header({ site, me, health, plan, onPersona, onReset, resetting }: {
  site: SiteView | undefined;
  me: Me;
  health: Health | null;
  plan: PlanView | null;
  onPersona: () => void;
  onReset: () => void;
  resetting: boolean;
}) {
  const live = health?.live_planner;
  return (
    <header className="top">
      <div className="brand">
        <h1>Groundwork</h1>
        {site && <span className="muted">{site.name} · {site.location} · {site.asset}</span>}
      </div>
      <div className="badges">
        {site && <span className="badge">As of <span className="num">{fmtLong(site.as_of)}</span></span>}
        <span className={`badge ${live ? "live" : "sim"}`}>
          <span className="dot" />
          {live ? `Live planner · ${health?.planner_model}` : "Simulated planner (no API key)"}
        </span>
        {plan && plan.simulated && live && <span className="badge sim"><span className="dot" />last plan simulated</span>}
        {health?.dry_run && <span className="badge">dry run: nothing is sent</span>}
        <button className="badge" onClick={onPersona} data-testid="persona">
          {me.name} · {me.approver ? "approver" : "viewer"} <span className="dim">(demo persona)</span>
        </button>
        <button className="badge crit" onClick={onReset} disabled={resetting}>
          {resetting ? "Resetting…" : "Reset site"}
        </button>
      </div>
    </header>
  );
}
