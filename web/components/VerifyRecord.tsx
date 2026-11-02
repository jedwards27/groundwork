"use client";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { get, local, send } from "@/lib/client";
import type { LedgerEntry, Session, VerifyEntry } from "@/lib/types";

// Anyone holding a copy of a record (from a receipt, an export, a screenshot typed back in) can check
// it against the ledger: the record's hash is recomputed, the chain up to it is walked, and the copy
// must hash to exactly what the ledger holds.
export function VerifyRecord({ site }: { site: string }) {
  const session = useQuery({ queryKey: ["session"], queryFn: () => local<Session>("/api/session") });
  const me = session.data?.me ?? null;
  const ledger = useQuery({
    queryKey: ["ledger", site, "all"],
    queryFn: () => get<{ entries: LedgerEntry[] }>(`sites/${site}/ledger?arm=`),
    enabled: !!me,
  });
  const entries = [...(ledger.data?.entries ?? [])].reverse();
  const [seq, setSeq] = useState<number | null>(null);
  const [copy, setCopy] = useState("");
  const [result, setResult] = useState<VerifyEntry | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("seq");
    if (q && /^\d+$/.test(q)) setSeq(Number(q));
  }, []);
  useEffect(() => {
    if (seq === null && entries.length) setSeq(entries[0].seq);
  }, [entries, seq]);

  const label = (e: LedgerEntry) => {
    const p = e.payload as { ref?: string; title?: string };
    return `#${e.seq} · ${e.type}${p.ref ? ` · ${p.ref}` : ""}${p.title ? ` · ${p.title}` : ""}`;
  };
  const selected = entries.find((e) => e.seq === seq);
  const verify = async () => {
    setErr("");
    setResult(null);
    let entry: Record<string, unknown> | undefined;
    let target = seq;
    if (copy.trim()) {
      try {
        entry = JSON.parse(copy) as Record<string, unknown>;
      } catch {
        setErr("The pasted copy is not valid JSON.");
        return;
      }
      if (typeof entry.seq === "number") target = entry.seq;
    }
    if (target === null) {
      setErr("Choose a record first.");
      return;
    }
    setBusy(true);
    try {
      setResult(await send<VerifyEntry>("POST", `sites/${site}/ledger/verify-entry`, { seq: target, entry }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (session.isSuccess && !me)
    return (
      <main className="verify-page">
        <p>
          Choose a demo persona on <a href="/">Mission Control</a> first, then come back.
        </p>
      </main>
    );
  return (
    <main className="verify-page" aria-label="Verify a record">
      <header className="top">
        <div className="brand">
          <h1>Verify a record</h1>
          <span className="muted">
            <a href="/">Mission Control</a> · every proposal, decision, approval and outcome is a hash-chained record
          </span>
        </div>
      </header>
      <section className="panel">
        <label className="small muted" htmlFor="record">Record</label>
        <select id="record" value={seq ?? ""} onChange={(e) => setSeq(Number(e.target.value))} data-testid="verify-select">
          {entries.map((e) => (
            <option key={e.seq} value={e.seq}>{label(e)}</option>
          ))}
        </select>
        <label className="small muted" htmlFor="copy" style={{ display: "block", marginTop: 12 }}>
          Or paste a copy of a record (JSON), for example from a receipt someone sent you
        </label>
        <textarea id="copy" rows={8} className="mono" value={copy} onChange={(e) => setCopy(e.target.value)} data-testid="verify-copy" />
        {err && <p className="bad small">{err}</p>}
        <div className="actions">
          <button className="btn primary" onClick={verify} disabled={busy} data-testid="verify-run">Verify</button>
          <button className="btn ghost" onClick={() => selected && setCopy(JSON.stringify(selected, null, 2))} disabled={!selected}>
            Copy the selected record into the box
          </button>
          {copy && <button className="btn ghost" onClick={() => setCopy("")}>Clear</button>}
        </div>
      </section>
      {result && (
        <section className={`panel verify-result ${result.match ? "match" : "mismatch"}`} data-testid="verify-result">
          <h2 data-testid="verify-verdict">{result.match ? "Match" : "Mismatch"}</h2>
          {result.found ? (
            <dl>
              <dt>Record</dt><dd>#{result.seq} · {result.type} · {result.recorded_at}</dd>
              <dt>Mandate</dt><dd>{result.mandate_version ? `issued under mandate v${result.mandate_version}` : "not tied to a mandate decision"}</dd>
              <dt>Stored hash</dt><dd className="mono">{result.stored_hash}</dd>
              <dt>Recomputed</dt><dd className="mono">{result.recomputed_hash}</dd>
              {result.copy_hash && (<><dt>Your copy</dt><dd className="mono">{result.copy_hash}</dd></>)}
            </dl>
          ) : null}
          {result.problems.length > 0 && (
            <ul className="bad small">
              {result.problems.map((p) => <li key={p}>{p}</li>)}
            </ul>
          )}
          <p className="note">
            {result.match
              ? "The record hashes to what the ledger holds, and every record before it links to the one after."
              : "Something differs from what was recorded. The ledger is append-only, so a mismatch means the copy or the stored record was changed."}
          </p>
        </section>
      )}
    </main>
  );
}
