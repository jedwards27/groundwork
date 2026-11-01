"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, local } from "@/lib/client";
import type { Attestation, LedgerEntry, ScoreRow, Verify } from "@/lib/types";

export function LedgerPanel({ site, hosted }: { site: string; hosted: boolean }) {
  const qc = useQueryClient();
  const [arm, setArm] = useState<"informed" | "blind" | "all">("informed");
  const ledger = useQuery({
    queryKey: ["ledger", site, arm],
    queryFn: () => get<{ entries: LedgerEntry[] }>(`sites/${site}/ledger${arm === "all" ? "?arm=" : `?arm=${arm}`}`),
  });
  const verify = useQuery({ queryKey: ["verify", site], queryFn: () => get<Verify>(`sites/${site}/ledger/verify`) });
  const [msg, setMsg] = useState("");
  const tamper = async () => {
    try {
      const r = await local<{ edited_seq: number }>("/api/admin/tamper", "POST");
      setMsg(`Edited entry ${r.edited_seq} with owner credentials (trigger disabled, row changed, trigger re-enabled).`);
    } catch (e) {
      setMsg((e as Error).message);
    }
    await qc.invalidateQueries({ queryKey: ["verify"] });
    await qc.invalidateQueries({ queryKey: ["attestation"] });
  };
  const v = verify.data;
  const entries = ledger.data?.entries ?? [];
  return (
    <section className="panel" aria-label="Ledger">
      <h2>
        Ledger <span className="hint">append-only, hash-chained; every proposal, decision and outcome</span>
      </h2>
      <div className="tabs" role="group" aria-label="Arm">
        {(["informed", "blind", "all"] as const).map((a) => (
          <button key={a} aria-pressed={arm === a} onClick={() => setArm(a)}>{a === "informed" ? "your plan" : a === "blind" ? "blind arm" : "everything"}</button>
        ))}
      </div>
      <p className="small" style={{ margin: "8px 0" }} data-testid="verify">
        {v ? (
          v.ok ? (
            <span className="ok">Chain verified · {v.count} entries · head <span className="mono">{v.head_hash.slice(0, 12)}…</span></span>
          ) : (
            <span className="bad">Verification failed: {v.problems[0]}</span>
          )
        ) : (
          "Verifying…"
        )}{" "}
        <button className="btn small ghost" onClick={() => verify.refetch()}>Verify again</button>
        {!hosted && (
          <button className="btn small danger" onClick={tamper} aria-describedby="tamper-note">Tamper with one entry</button>
        )}
      </p>
      {!hosted && (
        <p id="tamper-note" className="small dim">
          Local demo only: edits one decision the way someone holding database owner credentials could. Reset the site to restore.
        </p>
      )}
      {msg && <p className="small muted">{msg}</p>}
      <div className="scroll">
        <table className="tbl">
          <thead><tr><th>#</th><th>entry</th><th>what</th><th>hash</th></tr></thead>
          <tbody>
            {[...entries].reverse().map((e) => {
              const p = e.payload as Record<string, unknown>;
              const what = [p.ref, p.title ?? p.preset ?? p.event, p.decision ?? p.verdict].filter(Boolean).join(" · ");
              return (
                <tr key={e.seq}>
                  <td className="n">{e.seq}</td>
                  <td>{e.type}{e.arm === "blind" ? " (blind)" : ""}</td>
                  <td>{String(what).slice(0, 90)}</td>
                  <td className="n">{e.hash.slice(0, 8)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function Scorecard({ site }: { site: string }) {
  const q = useQuery({ queryKey: ["scorecard", site], queryFn: () => get<{ rows: ScoreRow[]; note: string }>(`sites/${site}/scorecard`) });
  const rows = q.data?.rows ?? [];
  const pct = (x: number) => `${Math.round(x * 1000) / 10}%`;
  return (
    <section className="panel" aria-label="Scope faithfulness">
      <h2>
        Scope faithfulness <span className="hint">does the model stay inside the grant, and report truthfully?</span>
      </h2>
      {rows.length === 0 ? (
        <p className="empty">No plans yet.</p>
      ) : (
        <table className="tbl">
          <thead><tr><th>arm · model</th><th>proposals</th><th>held</th><th>over-cautious</th><th>hard</th><th>honest</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.arm}-${r.model_id}`}>
                <td>{r.label}<br /><span className="dim mono">{r.model_id}</span></td>
                <td className="n">{r.proposals}</td>
                <td className="n">{r.over_reach} ({pct(r.over_reach_rate)})</td>
                <td className="n">{r.over_caution} ({pct(r.over_caution_rate)})</td>
                <td className="n">{r.hard_violations}</td>
                <td className="n">{r.honest_rate === null ? "—" : pct(r.honest_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="note">
        Held: the model proposed more autonomy than the mandate allows. The gap between the two arms is how much of
        scope faithfulness comes from the model&apos;s own judgment versus the rules being spelled out. {q.data?.note}
      </p>
    </section>
  );
}

export function AttestationPanel({ site }: { site: string }) {
  const q = useQuery({ queryKey: ["attestation", site], queryFn: () => get<Attestation>(`sites/${site}/attestation`) });
  const [show, setShow] = useState(false);
  const a = q.data?.attestation;
  if (!a) return null;
  const href = `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(q.data, null, 2))}`;
  return (
    <section className="panel" aria-label="Attestation">
      <h2>
        Attestation <span className="hint">signed summary of the ledger, genesis to head</span>
      </h2>
      <dl className="small" style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", margin: 0 }}>
        <dt className="muted">Violations</dt><dd className={a.violations.count ? "bad" : "ok"} data-testid="violations">{a.violations.count} <span className="dim">({a.violations.definition})</span></dd>
        <dt className="muted">Chain</dt><dd className={a.ledger.chain_verified ? "ok" : "bad"} data-testid="attested-chain">{a.ledger.chain_verified ? "verified" : "FAILED"} · {a.ledger.entries} entries · head {a.ledger.head_hash.slice(0, 12)}…</dd>
        <dt className="muted">Mandate</dt><dd>v{a.mandate.version} {a.mandate.preset}</dd>
        <dt className="muted">Models</dt><dd className="mono">{a.model_ids.join(", ") || "none"}</dd>
        <dt className="muted">Dry run</dt><dd>{String(a.dry_run)}</dd>
        <dt className="muted">Identity</dt><dd>{a.identity_assurance}</dd>
        <dt className="muted">Signature</dt><dd className="mono">{q.data!.signature.alg} {q.data!.signature.value.slice(0, 16)}… ({a.signer})</dd>
      </dl>
      <p className="small muted" style={{ marginTop: 8 }}>What this does not prove:</p>
      <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>
        {a.what_this_does_not_prove.map((x) => <li key={x}>{x}</li>)}
      </ul>
      <div className="actions">
        <button className="btn small ghost" onClick={() => setShow(!show)}>{show ? "Hide" : "Show"} JSON</button>
        <a className="btn small ghost" href={href} download={`attestation-${a.site}-${a.ledger.head_seq}.json`}>Download</a>
      </div>
      {show && <pre className="json">{JSON.stringify(q.data, null, 2)}</pre>}
    </section>
  );
}
