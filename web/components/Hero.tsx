"use client";
import { daysBetween, fmt, fmtLong } from "@/lib/format";
import { stages } from "@/lib/stages";
import type { ChainView, PlanView, SiteView } from "@/lib/types";
import { Prov } from "./Tip";

export function Hero({ chain, site, plan, onEvidence }: {
  chain: ChainView;
  site: SiteView;
  plan: PlanView | null;
  onEvidence: (key: string) => void;
}) {
  const ms = chain.milestone;
  const late = ms.delta_days ?? 0;
  const gate = chain.items.find((i) => i.key === chain.gate);
  const party = (k: string) => site.parties.find((p) => p.key === k)?.name ?? k;
  const slipped = gate && gate.finish_shift_days > 0;
  return (
    <section className="hero" aria-label="Delivery countdown">
      <div className="count">
        <div className="lead">
          {site.asset} · {site.capacity_mw} MW · {ms.headline}
        </div>
        <div className="big">
          <span className="num" data-testid="days-remaining">{ms.days_remaining}</span>
          <span className="unit">days</span>
          <span className={`delta ${late <= 0 ? "ok" : ""}`}>
            {late > 0 ? `${late} days late` : `${-late} days to spare`}
          </span>
        </div>
        <div className="target muted">
          Forecast <b>{fmtLong(ms.forecast_finish)}</b>
          {ms.forecast_low !== ms.forecast_high && (
            <span className="num"> (range {fmt(ms.forecast_low)} to {fmt(ms.forecast_high)})</span>
          )}{" "}
          · target <b>{fmtLong(ms.target_date)}</b> <Prov provenance={ms.provenance} source={ms.source} />
        </div>
        {gate && (
          <div className={`gating ${slipped ? "crit" : ""}`} data-testid="gate">
            <div className="k">{slipped ? "Gating item, slipped" : "This week's gating item"}</div>
            <div className="v">{gate.title}</div>
            <div className="row small muted">
              <span>{party(gate.owner)} ·</span>
              <span className="num">
                planned {fmt(gate.planned_finish)}
                {slipped ? ` → forecast ${fmt(gate.early_finish)}` : ""} ·
              </span>
              <span className="num">
                {(chain.min_float ?? 0) >= 0
                  ? `${chain.min_float} business days of float`
                  : `${-(chain.min_float ?? 0)} business days behind the target`}
              </span>
              <Prov provenance={gate.provenance} source={gate.source} />
              {gate.source.startsWith("status-report") && (
                <button className="btn small ghost" onClick={() => onEvidence("status-report-2026-10-30")}>
                  Open the status report
                </button>
              )}
            </div>
          </div>
        )}
        {chain.calendar_losses.length > 0 && (
          <div className="losses">
            <b>Hidden in the calendar</b>
            <ul>
              {chain.calendar_losses.map((l, n) => (
                <li key={n}>{l.sentence}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <Differential chain={chain} plan={plan} />
      <ol className="stages" aria-label="Delivery stages">
        {stages(chain.items).map((s) => (
          <li key={s.key} className={`stage ${s.status}`}>
            <div className="name">{s.label}</div>
            <div className="st">{s.note}</div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Differential({ chain, plan }: { chain: ChainView; plan: PlanView | null }) {
  const target = chain.milestone.target_date;
  const d = plan?.differential;
  const rows: { label: string; date: string | null; color: string; hatch?: boolean; tip?: string }[] = [
    { label: "Lease target", date: target, color: "var(--line-2)" },
    { label: d ? "Unmitigated" : "Forecast now", date: d ? d.unmitigated : chain.milestone.forecast_finish ?? null, color: "var(--crit)" },
  ];
  if (d) {
    rows.push(
      { label: "With what ran", date: d.now, color: "var(--agent)" },
      { label: "If you approve the queue", date: d.if_approved, color: "var(--good)" },
      { label: "If the landlord agrees", date: d.if_they_agree, color: "var(--good)", hatch: true },
    );
  }
  const deltas = rows.map((r) => daysBetween(target, r.date));
  const max = Math.max(1, ...deltas);
  return (
    <div className="diff" data-testid="differential">
      <h2>
        What the plan changes <span className="hint">days past the lease target, computed by the scheduler</span>
      </h2>
      <div className="rows">
        {rows.map((r, i) => (
          <div key={r.label} style={{ display: "contents" }}>
            <div className="lab">{r.label}</div>
            <div className="bar">
              <i className={r.hatch ? "hatch" : ""} style={{ width: `${Math.max(0, Math.round((100 * deltas[i]) / max))}%`, background: r.color }} />
            </div>
            <div className="val">
              <b>{deltas[i] > 0 ? `+${deltas[i]} d` : deltas[i] < 0 ? `${-deltas[i]} d early` : "on time"}</b> · {fmt(r.date)}
            </div>
          </div>
        ))}
      </div>
      <div className="net">
        {d ? (
          <>
            Our own actions recover <b>{d.recovered_now} days</b>; approving the queue <b>{d.recovered_if_approved}</b>;{" "}
            <b>{d.recovered_if_they_agree} days</b> come back only if the landlord agrees. Counterparty-dependent days are
            never credited on send.
          </>
        ) : (
          <>Play an event: the agent proposes a plan, the gateway decides what runs alone, and the scheduler computes the days.</>
        )}
      </div>
    </div>
  );
}
