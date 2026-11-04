import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { Button, KIND, SIZE } from "baseui/button";
import { ButtonGroup, MODE } from "baseui/button-group";
import { ChevronRight } from "baseui/icon";
import { ParagraphSmall } from "baseui/typography";
import { useState } from "react";
import { Link } from "react-router";
import { DECISION_LABEL, humanize, money, reasonSentence } from "@/lib/format";
import type { ActionView, ChainView, Me, PlanView, SiteView } from "@/lib/types";
import { ApproveButtons } from "./Approve";
import { app } from "@/copy/app";
import { project } from "@/copy/project";
import { Chip, DecisionTag, Drawer, Empty, Field, Grow, Line, Muted, Outgoing, Row } from "./ui";

const say = project.actions;
const sayAction = project.action;

const KIND_LABEL = say.kinds;

const FILTERS = [
  { label: say.filters.all, test: () => true },
  { label: say.filters.allow, test: (a: ActionView) => a.decision === "auto" },
  { label: say.filters.ask, test: (a: ActionView) => a.decision === "ask" },
  { label: say.filters.deny, test: (a: ActionView) => a.decision === "refuse" },
];

function outcome(a: ActionView): string {
  if (a.state === "executed") return say.outcome.executed;
  if (a.state === "pending") return say.outcome.pending;
  if (a.state === "declined") return say.outcome.declined;
  if (a.decision === "refuse") return say.outcome.refused;
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
        <Empty>{say.noPlan}</Empty>
        <Button kind={KIND.secondary} size={SIZE.compact} onClick={onOpenInbox}>
          {say.openInbox}
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
              {say.filterCount(f.label, plan.actions.filter(f.test).length)}
            </Button>
          ))}
        </ButtonGroup>
        <span className={css({ marginLeft: "auto", display: "flex", gap: theme.sizing.scale200 })}>
          {plan.simulated ? (
            <Chip tip={say.scriptedTip} testId="simulated">
              {say.scripted}
            </Chip>
          ) : (
            <Chip kind="blue" tip={say.plannedBy(plan.model_id ?? "")}>
              {plan.model_id}
            </Chip>
          )}
          {plan.report && (
            <Chip
              kind={rc?.ok === false ? "red" : "green"}
              tip={say.reportTip}
              testId="report-verdict"
            >
              {rc?.ok === false ? say.reportBad : say.reportOk}
            </Chip>
          )}
        </span>
      </div>
      {plan.assessment && <Clamped text={plan.assessment} />}

      <div data-testid="actions-list">
        {shown.length === 0 && <Empty>{say.nothingHere}</Empty>}
        {shown.map((a) => (
          <Row key={a.id} onClick={() => setOpen(a.id)} testId={`action-${a.ref}`}>
            <DecisionTag decision={a.decision} testId={`decision-${a.ref}`} />
            <Grow>
              <Line>{a.title}</Line>
              <Muted>
                {KIND_LABEL[a.kind ?? ""] ?? a.executor}
                {a.recipient_name ? say.to(a.recipient_name) : ""}
                {a.amount_cents ? `, ${money(a.amount_cents)}` : ""}
                <span className={css({ "@media (min-width: 640px)": { display: "none" } })}>, {outcome(a)}</span>
              </Muted>
            </Grow>
            {a.delta === "over_reach" && (
              <Chip kind="red" tip={say.heldTip(DECISION_LABEL[a.proposed_autonomy], DECISION_LABEL[a.decision ?? ""])} testId={`held-${a.ref}`}>
                {say.held}
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
          <Panel title={say.reportTitle}>
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
  if (!a) return <Drawer open={false} onClose={onClose} title="">{null}</Drawer>;
  const p = a.params as Record<string, string | undefined>;
  const text = p.body ?? p.agenda ?? p.summary ?? p.decision ?? p.scope ?? "";
  const subject = p.subject ?? (p.document_title ? sayAction.sign(p.document_title) : "");
  const e = a.effect;
  return (
    <Drawer open onClose={onClose} title={a.title} testId="action-drawer">
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <DecisionTag decision={a.decision} />
        <Muted>{outcome(a)}</Muted>
      </div>
      {(a.recipient_name || subject || text) && (
        <Outgoing
          label={p.subject || text ? sayAction.asItGoesOut : sayAction.whatItWouldDo}
          to={a.recipient_name ? sayAction.to(a.recipient_name) : null}
          subject={subject}
          text={text}
          testId="outgoing"
        />
      )}
      {a.decision === "refuse" && (
        // Deny isn't a dead end: Groundwork can't do it, so it hands it to you with what it found.
        <Field label={sayAction.yours.title}>
          <span data-testid="yours-to-do">
            {sayAction.yours.body} {a.rationale}
          </span>
        </Field>
      )}
      {a.state === "pending" && (
        <ApproveButtons
          actionId={a.id}
          version={a.mandate_version}
          canApprove={!!me && me.approver && a.approvers.includes(me.person)}
          approvers={a.approvers.map(name)}
          onDone={onClose}
        />
      )}
      {a.decision && <Field label={sayAction.why[a.decision]}>{plainWhy(a, names)}</Field>}
      {a.approvals.map((ap) => (
        <Muted key={ap.at}>
          {sayAction.decided(
            ap.verdict === "approve" ? "approve" : "decline",
            ap.person_name,
            new Date(ap.at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }),
            ap.kid,
          )}
        </Muted>
      ))}
      {a.external_ref && <Muted>{sayAction.ran(a.execution_detail ?? "", a.external_ref)}</Muted>}
      <Accordion renderAll overrides={{ Content: { style: { paddingLeft: 0, paddingRight: 0 } }, Header: { style: { paddingLeft: 0, paddingRight: 0 } } }}>
        <Panel title={sayAction.details}>
          <div style={{ display: "grid", gap: 16 }}>
            {a.path.length > 0 && <Field label={sayAction.route}>{[name(site.principal), ...a.path.map(name)].join(" → ")}</Field>}
            {a.clause && (
              <Field label={sayAction.clause(a.mandate_version)}>
                <span data-testid={`clause-${a.ref}`}>{a.clause}</span>
              </Field>
            )}
            <Field label={sayAction.agentWhy}>{a.rationale}</Field>
            {e && e.kind !== "none" && (
              <Field label={sayAction.ifItWorks}>
                {sayAction.effect(
                  sayAction.effectVerbs[e.kind] ?? e.kind,
                  items[e.item ?? ""] ?? e.item ?? "",
                  e.pred && e.kind === "parallelize" ? (items[e.pred] ?? e.pred) : null,
                  e.days,
                )}{" "}
                {!a.effect_allowed
                  ? sayAction.notCounted(humanize(a.effect_reason, names))
                  : e.realized_by === "counterparty_response"
                    ? sayAction.onlyIfTheyAgree(a.response_lag_bd)
                    : sayAction.ourOwn}
              </Field>
            )}
          </div>
        </Panel>
      </Accordion>
    </Drawer>
  );
}

// Why the gateway decided as it did, in a sentence: its reason for an allow or an ask (with names
// for keys), and the never-list for a deny.
function plainWhy(a: ActionView, names: Record<string, string>): string {
  return a.decision === "refuse" ? a.clause : reasonSentence(humanize(a.reason, names));
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
        {more ? app.common.less : app.common.more}
      </Button>
    </div>
  );
}

const BUCKET = say.buckets;

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
                {say.reportLine(s ? BUCKET[s] : say.notMentioned, BUCKET[h])}
              </Muted>
            </Grow>
            <span className={css({ color: s === h ? theme.colors.contentPositive : theme.colors.contentNegative })}>{s === h ? "✓" : "✗"}</span>
            {decided && (
              <Link to={`/projects/${project}/settings?record=${decided.seq}`} className={css({ ...theme.typography.ParagraphXSmall, color: theme.colors.contentSecondary })}>
                #{decided.seq}
              </Link>
            )}
          </Row>
        );
      })}
    </div>
  );
}
