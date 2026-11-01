"use client";
import * as Dialog from "@radix-ui/react-dialog";
import * as Slider from "@radix-ui/react-slider";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { send } from "@/lib/client";
import type { CompareRow, MandateView, Me } from "@/lib/types";

const LABEL: Record<string, string> = { supervised: "Supervised", standard: "Standard", autonomous: "Autonomous within limits" };

export function Dial({ site, mandate, compare, me }: { site: string; mandate: MandateView; compare: CompareRow[]; me: Me }) {
  const qc = useQueryClient();
  const presets = mandate.presets;
  const [sel, setSel] = useState(presets.indexOf(mandate.preset));
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => setSel(presets.indexOf(mandate.preset)), [mandate.preset, presets]);
  const chosen = presets[sel];
  const changed = chosen !== mandate.preset;
  const issue = async () => {
    try {
      const r = await send<{ version: number; redecided: { ref: string; from: string; to: string }[]; executed: string[] }>(
        "PUT", `sites/${site}/mandate`, { preset: chosen });
      const moved = r.redecided.filter((x) => x.from !== x.to);
      setMsg(`Mandate v${r.version} issued. ${moved.length ? `Re-decided: ${moved.map((x) => `${x.ref} ${x.from}→${x.to}`).join(", ")}.` : "No open action changed."}${r.executed.length ? ` Ran: ${r.executed.join(", ")}.` : ""}`);
      setConfirm(false);
      await qc.invalidateQueries();
    } catch (e) {
      setMsg((e as Error).message);
      setConfirm(false);
    }
  };
  return (
    <section className="panel dial" aria-label="Authority dial">
      <h2>
        Authority dial <span className="hint">what the agent may do alone</span>
      </h2>
      <div className="preset">
        {LABEL[chosen]} <span className="ver">{changed ? "preview" : `mandate v${mandate.version}`}</span>
      </div>
      <Slider.Root className="slider" min={0} max={presets.length - 1} step={1} value={[sel]}
        onValueChange={(v) => setSel(v[0])}>
        <Slider.Track className="track">
          <Slider.Range className="range" />
        </Slider.Track>
        <Slider.Thumb className="thumb" aria-label="Authority preset" aria-valuetext={LABEL[chosen]} />
      </Slider.Root>
      <div className="ticks">
        {presets.map((p) => (
          <span key={p}>{LABEL[p].split(" ")[0]}</span>
        ))}
      </div>
      {!changed ? (
        <ul className="rules">
          {mandate.plain_lines.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      ) : (
        <p className="small muted" style={{ marginTop: 10 }}>
          Previewing the latest plan under {LABEL[chosen]}. Nothing changes until a new mandate version is issued.
        </p>
      )}
      {compare.length > 0 && (
        <table className="compare" aria-label="The same plan under each preset">
          <thead>
            <tr><th>Preset</th><th>Alone</th><th>Asks</th><th>Refused</th><th>Held</th><th>Days if agreed</th></tr>
          </thead>
          <tbody>
            {compare.map((r) => (
              <tr key={r.preset} className={`${r.current ? "cur" : ""} ${r.preset === chosen && changed ? "sel" : ""}`}>
                <td>{LABEL[r.preset].split(" ")[0]}{r.current ? " (now)" : ""}</td>
                <td className="n">{r.auto}</td><td className="n">{r.ask}</td><td className="n">{r.refuse}</td>
                <td className="n">{r.held}</td><td className="n">{r.recovered_if_they_agree}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="actions">
        <button className="btn primary" disabled={!changed || !me.approver} onClick={() => setConfirm(true)}>
          Issue mandate v{mandate.version + 1}
        </button>
        {!me.approver && <span className="small muted">Only an approver can change the mandate.</span>}
      </div>
      {msg && <p className="small" style={{ marginTop: 8 }}>{msg}</p>}
      <p className="note">Same plan, different authority: the gateway re-decides open actions; it never re-plans, and what already ran stays on the record.</p>
      <Dialog.Root open={confirm} onOpenChange={setConfirm}>
        <Dialog.Portal>
          <Dialog.Overlay className="overlay" />
          <Dialog.Content className="dialog" aria-describedby={undefined}>
            <Dialog.Title>Issue mandate v{mandate.version + 1}: {LABEL[chosen]}</Dialog.Title>
            <p className="small">
              {me.name} is changing the grant of authority from {LABEL[mandate.preset]} to {LABEL[chosen]}. Open actions are
              re-decided under the new version and any that may now run alone run in dry run. The change is a ledger entry.
            </p>
            <div className="actions">
              <button className="btn primary" onClick={issue}>Issue v{mandate.version + 1}</button>
              <Dialog.Close className="btn ghost">Cancel</Dialog.Close>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
