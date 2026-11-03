import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { Button, KIND, SIZE } from "baseui/button";
import { ButtonGroup, MODE } from "baseui/button-group";
import { ChevronRight } from "baseui/icon";
import { ParagraphSmall } from "baseui/typography";
import { useState } from "react";
import { Link } from "react-router";
import { DECISION_LABEL, humanize, money } from "@/lib/format";
import type { ActionView, ChainView, Me, PlanView, SiteView } from "@/lib/types";
import { ApproveButtons } from "./Approve";
import { Chip, DecisionTag, Drawer, Empty, Field, Grow, Line, Muted, Quote, Row } from "./ui";

const KIND_LABEL: Record<string, string> = {
  send: "Send", chase: "Chase", schedule: "Schedule", reserve: "Reserve", commit: "Commit spend", draft: "Draft",
  legal: "Legal draft", file: "File", escalate: "Report to you", record: "Record", pay: "Pay", sign: "Sign", delete: "Delete",
};

const FILTERS = [
  { label: "All", test: () => true },
  { label: "Allow", test: (a: ActionView) => a.decision === "auto" },
  { label: "Ask", test: (a: ActionView) => a.decision === "ask" },
  { label: "Deny", test: (a: ActionView) => a.decision === "refuse" },
];

function outcome(a: ActionView): string {
  if (a.state === "executed") return "Ran · dry run";
  if (a.state === "pending") return "Waiting for you";
  if (a.state === "declined") return "Declined";
  if (a.decision === "refuse") return "Not run";
  return a.state;
}

export function ActionsTab({ plan, site, chain, me, onOpenInbox }: {
  plan: PlanView | null;
  site: SiteView;
  chain: ChainView;
  me: Me | null;
  onOpenInbox: () => void;
}) {
  const [css, theme] = useStyletron();
  const [filter, setFilter] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  if (!plan)
    return (
      <div>
        <Empty>No plan yet. Play a message from the inbox.</Empty>
        <Button kind={KIND.secondary} size={SIZE.compact} onClick={onOpenInbox}>
          Open the inbox
        </Button>
      </div>
    );
  const name = (k: string) => site.parties.find((p) => p.key === k)?.name ?? site.people.find((p) => p.key === k)?.name ?? k;
  const shown = plan.actions.filter(FILTERS[filter].test);
  const rc = plan.report_check;
  const action = plan.actions.find((a) => a.id === open) ?? null;
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale400 })}>
      <div className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", flexWrap: "wrap" })}>
        <ButtonGroup mode={MODE.radio} size={SIZE.compact} selected={filter} onClick={(_, i) => setFilter(i)}>
          {FILTERS.map((f) => (
            <Button key={f.label} kind={KIND.secondary}>
              {f.label} · {plan.actions.filter(f.test).length}
            </Button>
          ))}
        </ButtonGroup>
        <span className={css({ marginLeft: "auto", display: "flex", gap: theme.sizing.scale200 })}>
          {plan.simulated ? (
            <Chip tip="Written by hand so the demo runs the same way every time; no model is running. The gateway's decisions, the ledger and the report check are live code." testId="simulated">
              Scripted plan
            </Chip>
          ) : (
            <Chip kind="blue" tip={`Planned by ${plan.model_id}.`}>
              {plan.model_id}
            </Chip>
          )}
          {plan.report && (
            <Chip
              kind={rc?.ok === false ? "red" : "green"}
              tip="The agent's own account of what it did, asked and was denied, checked line by line against the ledger."
              testId="report-verdict"
            >
              {rc?.ok === false ? "Report disagrees with the ledger" : "Report matches the ledger"}
            </Chip>
          )}
        </span>
      </div>
      {plan.assessment && <Clamped text={plan.assessment} />}

      <div>
        {shown.length === 0 && <Empty>Nothing here.</Empty>}
        {shown.map((a) => (
          <Row key={a.id} onClick={() => setOpen(a.id)} testId={`action-${a.ref}`}>
            <DecisionTag decision={a.decision} testId={`decision-${a.ref}`} />
            <Grow>
              <Line>{a.title}</Line>
              <Muted>
                {KIND_LABEL[a.kind ?? ""] ?? a.executor}
                {a.recipient_name ? ` · to ${a.recipient_name}` : ""}
                {a.amount_cents ? ` · ${money(a.amount_cents)}` : ""}
                <span className={css({ "@media (min-width: 640px)": { display: "none" } })}> · {outcome(a)}</span>
              </Muted>
            </Grow>
            {a.delta === "over_reach" && (
              <Chip kind="red" tip={`The agent proposed “${DECISION_LABEL[a.proposed_autonomy]}”; the mandate says “${DECISION_LABEL[a.decision ?? ""]}”. The gateway held it.`} testId={`held-${a.ref}`}>
                Held
              </Chip>
            )}
            <span className={css({ display: "none", whiteSpace: "nowrap", "@media (min-width: 640px)": { display: "block" } })}>
              <Muted>{outcome(a)}</Muted>
            </span>
            <ChevronRight size={20} color={theme.colors.contentTertiary} />
          </Row>
        ))}
      </div>

      {plan.report && (
        <Accordion>
          <Panel title="The agent's report beside the ledger">
            <ParagraphSmall marginTop={0}>{plan.report.summary}</ParagraphSmall>
            <ReportVsRecord plan={plan} project={site.key} />
          </Panel>
        </Accordion>
      )}

      <ActionDrawer action={action} site={site} chain={chain} me={me} name={name} onClose={() => setOpen(null)} />
    </div>
  );
}

function ActionDrawer({ action: a, site, chain, me, name, onClose }: {
  action: ActionView | null;
  site: SiteView;
  chain: ChainView;
  me: Me | null;
  name: (k: string) => string;
  onClose: () => void;
}) {
  const names: Record<string, string> = Object.fromEntries(site.parties.map((p) => [p.key, p.name]));
  const items: Record<string, string> = Object.fromEntries(chain.items.map((i) => [i.key, i.title]));
  const verb: Record<string, string> = { duration_reduction: "shorten", lag_reduction: "shorten the wait before", parallelize: "overlap" };
  if (!a) return <Drawer open={false} onClose={onClose} title="">{null}</Drawer>;
  const p = a.params as Record<string, string | undefined>;
  const text = p.body ?? p.agenda ?? p.summary ?? p.decision ?? p.scope ?? "";
  const reason = humanize(a.reason, names);
  const e = a.effect;
  return (
    <Drawer open onClose={onClose} title={a.title} testId="action-drawer">
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <DecisionTag decision={a.decision} />
        <Muted>{outcome(a)}</Muted>
      </div>
      {a.path.length > 0 && <Field label="Route">{[name(site.principal), ...a.path.map(name)].join(" → ")}</Field>}
      {a.clause && (
        <Field label={`Mandate clause${a.mandate_version ? ` (v${a.mandate_version})` : ""}`}>
          <span data-testid={`clause-${a.ref}`}>{a.clause}</span>
        </Field>
      )}
      {!a.clause.includes(a.reason) && <Field label="The gateway">{reason}</Field>}
      {(a.recipient_name || p.subject || text) && (
        <Field label="As it would go out">
          {a.recipient_name && <Muted>To {a.recipient_name}</Muted>}
          {p.subject && <ParagraphSmall margin={0}>{p.subject}</ParagraphSmall>}
          {text && <Quote>{text}</Quote>}
        </Field>
      )}
      <Field label="Why the agent proposed it">{a.rationale}</Field>
      {e && e.kind !== "none" && (
        <Field label="If it works">
          {verb[e.kind] ?? e.kind} “{items[e.item ?? ""] ?? e.item}”{e.pred && e.kind === "parallelize" ? ` with “${items[e.pred] ?? e.pred}”` : ""} by {e.days}{" "}
          business days.{" "}
          {!a.effect_allowed
            ? `Not counted: ${humanize(a.effect_reason, names)}`
            : e.realized_by === "counterparty_response"
              ? `Counts only if they agree, no sooner than ${a.response_lag_bd} business days from now.`
              : "Our own action."}
        </Field>
      )}
      {a.approvals.map((ap) => (
        <Muted key={ap.at}>
          {ap.verdict === "approve" ? "Approved" : "Declined"} by {ap.person_name},{" "}
          {new Date(ap.at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} (key {ap.kid})
        </Muted>
      ))}
      {a.external_ref && <Muted>Ran in dry run: {a.execution_detail} ({a.external_ref}). Nothing was sent.</Muted>}
      {a.state === "pending" && (
        <ApproveButtons
          actionId={a.id}
          version={a.mandate_version}
          canApprove={!!me && me.approver && a.approvers.includes(me.person)}
          approvers={a.approvers.map(name)}
          onDone={onClose}
        />
      )}
      {a.decision === "refuse" && <Muted>No one can approve this: the mandate denies it.</Muted>}
    </Drawer>
  );
}

// The agent's assessment, two lines until asked for more.
function Clamped({ text }: { text: string }) {
  const [css, theme] = useStyletron();
  const [more, setMore] = useState(false);
  return (
    <div data-testid="assessment">
      <div
        className={css({
          ...theme.typography.ParagraphXSmall,
          color: theme.colors.contentSecondary,
          ...(more ? {} : { display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }),
        })}
      >
        {text}
      </div>
      <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => setMore(!more)}>
        {more ? "Less" : "More"}
      </Button>
    </div>
  );
}

const BUCKET: Record<string, string> = { did: "did", asked: "asked a person", refused: "denied", failed: "failed" };

function ReportVsRecord({ plan, project }: { plan: PlanView; project: string }) {
  const [css, theme] = useStyletron();
  const r = plan.report!;
  const said = (ref: string) =>
    (["did", "asked", "refused", "failed"] as const).find((k) => (r[k] ?? []).some((x) => x === ref || x.startsWith(`${ref}:`) || x.startsWith(`${ref} `)));
  const held = (a: ActionView) =>
    a.ledger.some((l) => l.type === "execution_failed") ? "failed" : a.decision === "auto" ? "did" : a.decision === "refuse" ? "refused" : "asked";
  return (
    <div data-testid="report-vs-record">
      {plan.actions.map((a) => {
        const s = said(a.ref);
        const h = held(a);
        const decided = [...a.ledger].reverse().find((l) => l.type === "decided");
        return (
          <Row key={a.id}>
            <Grow>
              <Line>{a.title}</Line>
              <Muted>
                Report: {s ? BUCKET[s] : "not mentioned"} · Ledger: {BUCKET[h]}
              </Muted>
            </Grow>
            <span className={css({ color: s === h ? theme.colors.contentPositive : theme.colors.contentNegative })}>{s === h ? "✓" : "✗"}</span>
            {decided && (
              <Link to={`/verify?project=${project}&record=${decided.seq}`} className={css({ ...theme.typography.ParagraphXSmall, color: theme.colors.contentSecondary })}>
                #{decided.seq}
              </Link>
            )}
          </Row>
        );
      })}
    </div>
  );
}
