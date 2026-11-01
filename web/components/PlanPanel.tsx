"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { send } from "@/lib/client";
import { humanize, money } from "@/lib/format";
import type { ActionView, ChainView, Me, PlanView, SiteView } from "@/lib/types";

const KIND: Record<string, string> = {
  send: "Send", chase: "Chase", schedule: "Schedule", reserve: "Reserve", commit: "Commit spend", draft: "Draft",
  legal: "Legal draft", file: "File", escalate: "Report to you", record: "Record", pay: "Pay", sign: "Sign", delete: "Delete",
};

export function PlanPanel({ plan, site, me, chain }: { plan: PlanView | null; site: SiteView; me: Me; chain?: ChainView }) {
  const [acting, setActing] = useState<ActionView | null>(null);
  if (!plan)
    return (
      <section className="panel" aria-label="Plan and ledger">
        <h2>Plan</h2>
        <p className="empty">No plan yet. Play an event from the inbox.</p>
      </section>
    );
  const asked = plan.actions.filter((a) => a.decision === "ask");
  const did = plan.actions.filter((a) => a.decision === "auto");
  const refused = plan.actions.filter((a) => a.decision === "refuse");
  const name = (k: string) => site.parties.find((p) => p.key === k)?.name ?? site.people.find((p) => p.key === k)?.name ?? k;
  const names: Record<string, string> = Object.fromEntries(site.parties.map((p) => [p.key, p.name]));
  const items: Record<string, string> = Object.fromEntries((chain?.items ?? []).map((i) => [i.key, i.title]));
  const rc = plan.report_check;
  return (
    <section className="panel" aria-label="Plan and ledger">
      <h2>
        The plan, decided <span className="hint">{plan.simulated ? "simulated planner" : plan.model_id} · gateway outside the model</span>
      </h2>
      {plan.simulated && (
        <p className="banner sim" data-testid="simulated-banner">
          Simulated planner: these actions were written by hand to exercise the gateway. No model is running.
        </p>
      )}
      <div className="assess">{plan.assessment}</div>
      <div className="sum" style={{ marginTop: 10 }}>
        <div className="auto"><div className="n">{did.length}</div><div className="l">did on its own</div></div>
        <div className="ask"><div className="n">{asked.length}</div><div className="l">asked a person</div></div>
        <div className="ref"><div className="n">{refused.length}</div><div className="l">refused</div></div>
      </div>
      {[
        { title: "Asked you", list: asked, empty: "Nothing waiting on a person." },
        { title: "Did on its own", list: did, empty: "Nothing ran alone under this mandate." },
        { title: "Refused", list: refused, empty: "Nothing refused." },
      ].map((g) => (
        <div className="group" key={g.title}>
          <h3>{g.title} <span className="c">{g.list.length}</span></h3>
          {g.list.length === 0 && <div className="empty">{g.empty}</div>}
          {g.list.map((a) => <ActionRow key={a.id} a={a} name={name} names={names} items={items} onAct={() => setActing(a)} />)}
        </div>
      ))}
      {plan.report && (
        <div className={`report ${rc && rc.ok === false ? "bad" : ""}`} data-testid="report">
          <div className="k">
            What the agent reports{rc ? (rc.ok === false ? " · disagrees with the ledger" : " · matches the ledger") : ""}
          </div>
          <div>{plan.report.summary}</div>
        </div>
      )}
      <ApproveDialog action={acting} me={me} name={name} names={names} onClose={() => setActing(null)} />
    </section>
  );
}

function ActionRow({ a, name, names, items, onAct }: {
  a: ActionView; name: (k: string) => string; names: Record<string, string>; items: Record<string, string>; onAct: () => void;
}) {
  const e = a.effect;
  const reason = humanize(a.reason, names);
  const verb: Record<string, string> = { duration_reduction: "shorten", lag_reduction: "shorten the wait before", parallelize: "overlap" };
  return (
    <div className="item" data-ref={a.ref}>
      <div className="row">
        <span className="kind">{KIND[a.kind ?? ""] ?? a.executor}</span>
        <span className="title">{a.title}</span>
        <span className={`state ${a.state}`}>{a.state}</span>
      </div>
      {(a.recipient || a.path.length > 1) && (
        <div className="path">
          to <span className="hop">{a.recipient_name ?? a.recipient}</span>
          {a.path.length > 1 && (
            <>
              asking{" "}
              {a.path.map((h, n) => (
                <span key={h}>{n > 0 && "→ "}<span className="hop">{name(h)}</span></span>
              ))}
            </>
          )}
          {a.amount_cents ? <span className="meta"> · {money(a.amount_cents)}</span> : null}
        </div>
      )}
      <div className="why">{a.rationale}</div>
      {a.delta === "over_reach" ? (
        <div className="gate held" data-testid="held">
          Gateway held this: the agent proposed “{a.proposed_autonomy}”, the mandate says “{a.decision}”. {reason}
        </div>
      ) : a.delta === "over_caution" ? (
        <div className="gate caution">The agent asked, though the mandate allowed it to act: {reason}</div>
      ) : (
        <div className="gate">{reason}</div>
      )}
      {e && e.kind !== "none" && (
        <div className="meta">
          if it works: {verb[e.kind] ?? e.kind} “{items[e.item ?? ""] ?? e.item}”{e.pred && e.kind === "parallelize" ? ` with “${items[e.pred] ?? e.pred}”` : ""} by {e.days} business days ·{" "}
          {!a.effect_allowed
            ? `not credited: ${humanize(a.effect_reason, names)}`
            : e.realized_by === "counterparty_response"
              ? `counts only if they agree, no sooner than ${a.response_lag_bd} business days from now`
              : "our own action"}
        </div>
      )}
      {a.approvals.map((ap) => (
        <div key={ap.at} className="meta">
          {ap.verdict === "approve" ? "approved" : "declined"} by {ap.person_name} · {new Date(ap.at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} · key {ap.kid}
        </div>
      ))}
      {a.external_ref && <div className="meta">ran in dry run: {a.execution_detail} ({a.external_ref})</div>}
      {a.state === "pending" && (
        <div className="actions" style={{ marginTop: 4 }}>
          <button className="btn small primary" onClick={onAct} data-testid={`decide-${a.ref}`}>Approve or decline</button>
          <span className="small dim">approvers: {a.approvers.join(", ")}</span>
        </div>
      )}
    </div>
  );
}

function ApproveDialog({ action, me, name, names, onClose }: {
  action: ActionView | null; me: Me; name: (k: string) => string; names: Record<string, string>; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  if (!action) return null;
  const allowed = me.approver && action.approvers.includes(me.person);
  const decide = async (verdict: "approve" | "decline") => {
    setBusy(true);
    setErr("");
    try {
      await send("POST", `actions/${action.id}/approvals`, { verdict, note, idempotency_key: crypto.randomUUID() });
      await qc.invalidateQueries();
      setNote("");
      onClose();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const p = action.params as Record<string, string | undefined>;
  return (
    <Dialog.Root open={!!action} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="dialog" aria-describedby={undefined}>
          <Dialog.Title>{action.title}</Dialog.Title>
          <dl>
            <dt>To</dt><dd>{action.recipient_name ?? action.recipient ?? "internal"}</dd>
            {action.path.length > 1 && (<><dt>Asks</dt><dd>{action.path.map(name).join(" → ")}</dd></>)}
            {p.subject && (<><dt>Subject</dt><dd>{p.subject}</dd></>)}
            {(p.body || p.scope || p.document_title) && (<><dt>Text</dt><dd>{p.body ?? `${p.document_title ?? ""} ${p.scope ?? ""}`}</dd></>)}
            <dt>Gateway</dt><dd>{humanize(action.reason, names)}</dd>
            <dt>Mandate</dt><dd>v{action.mandate_version} · approvers {action.approvers.join(", ")}</dd>
            <dt>You</dt><dd>{me.name}{allowed ? "" : " (not an approver for this action)"}</dd>
            <dt>Binds to</dt><dd className="mono">{action.action_hash.slice(0, 23)}…</dd>
          </dl>
          <label className="small muted" htmlFor="note">Note (recorded in the ledger)</label>
          <textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} />
          {err && <p className="bad small">{err}</p>}
          <div className="actions">
            <button className="btn primary" disabled={!allowed || busy} onClick={() => decide("approve")} data-testid="approve">Approve</button>
            <button className="btn danger" disabled={!allowed || busy} onClick={() => decide("decline")}>Decline</button>
            <Dialog.Close className="btn ghost">Cancel</Dialog.Close>
          </div>
          <p className="note">An approval is a typed action by a named person, bound to this action&apos;s content and the mandate version. Replies, forwards and auto-replies are evidence and never approve anything.</p>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
