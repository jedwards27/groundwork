"use client";
import { useState } from "react";
import { time } from "@/lib/format";
import type { EventView, SiteView, Step } from "@/lib/types";

const KIND_LABEL: Record<string, string> = {
  schedule_change: "schedule change",
  evidence: "evidence",
  acknowledgment: "auto-reply",
  injection: "injection test",
};

export interface RunState {
  id: string;
  event: string;
  status: "running" | "done" | "failed";
  steps: Step[];
  replay?: string;
}

export function Inbox({ events, site, run, onPlay, onReplay }: {
  events: EventView[];
  site: SiteView;
  run: RunState | null;
  onPlay: (key: string) => void;
  onReplay: () => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const party = (k: string | null) => (k === "public" ? "public source" : site.parties.find((p) => p.key === k)?.name ?? k ?? "");
  const busy = run?.status === "running";
  const order = ["event-a", "event-b", "ack-approved", "event-b-expedite", "eo-62", "psc-26-e-0045", "injection-expedite-po", "injection-date-change"];
  const sorted = [...events].sort((a, b) => (order.indexOf(a.key) + 99) % 99 - (order.indexOf(b.key) + 99) % 99);
  return (
    <section className="panel" aria-label="Inbox">
      <h2>
        Inbox <span className="hint">what the end user receives, mostly forwarded by the lessee</span>
      </h2>
      <div>
        {sorted.map((e) => {
          const played = e.status === "applied";
          return (
            <div key={e.key} className={`msg ${played ? "played" : ""}`}>
              <div className="from">
                {party(e.from_party)}
                {e.forwarded_from ? <span className="muted"> (forwarding {party(e.forwarded_from)})</span> : null}
              </div>
              <div className="when">{new Date(e.received_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</div>
              <div className="title">{e.title}</div>
              <div className="ctl">
                <span className={`kindtag ${e.kind}`}>{KIND_LABEL[e.kind] ?? e.kind}</span>
                {e.body && (
                  <button className="btn small ghost" onClick={() => setOpen(open === e.key ? null : e.key)} aria-expanded={open === e.key}>
                    {open === e.key ? "Hide" : "Read"}
                  </button>
                )}
                {played ? (
                  <span className="small muted">received</span>
                ) : (
                  <button className="btn small primary" disabled={busy} onClick={() => onPlay(e.key)} data-testid={`play-${e.key}`}>
                    Play
                  </button>
                )}
              </div>
              {open === e.key && <pre className="body">{e.body}</pre>}
            </div>
          );
        })}
      </div>
      {run && (
        <div style={{ marginTop: 12 }} aria-live="polite">
          <h3>
            {run.replay ? `Replay of a run recorded at ${run.replay}` : run.status === "running" ? "Working" : run.status === "failed" ? "Run interrupted" : "Run"}{" "}
            {run.status === "running" && !run.replay && <span className="spin" aria-hidden />}
          </h3>
          <ol className="steps" data-testid="steps">
            {run.steps.map((s) => (
              <li key={s.i} className={`k-${s.kind}`}>
                <span className="i">{s.i}</span>
                <span>{s.text}</span>
              </li>
            ))}
          </ol>
          {run.status === "failed" && !run.replay && (
            <p className="banner crit small" data-testid="run-interrupted">
              This run stopped before it finished. Everything it did up to that point is on the ledger. Replay it, or play the event again.
            </p>
          )}
          {run.status !== "running" && !run.replay && (
            <div className="actions">
              <button className="btn small ghost" onClick={onReplay}>
                Replay this run (no new model call)
              </button>
              <span className="small dim">finished {run.steps.length ? time(run.steps[run.steps.length - 1].at) : ""}</span>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
