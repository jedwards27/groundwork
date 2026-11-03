import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ChevronRight } from "baseui/icon";
import { Skeleton } from "baseui/skeleton";
import { toaster } from "baseui/toast";
import { LabelMedium } from "baseui/typography";
import { useState } from "react";
import { useNavigate } from "react-router";
import { get, send } from "@/lib/client";
import { ago, fmt, lateness } from "@/lib/format";
import type { AskItem, DraftItem, HomeView, Session } from "@/lib/types";
import { ApproveButtons } from "./Approve";
import { Chip, Drawer, Empty, Field, Grow, Line, Muted, Page, Quote, Row, Section } from "./ui";

const DRAFT_LABEL: Record<DraftItem["kind"], string> = {
  project: "New project",
  mandate: "Mandate",
  facts: "Dates",
  links: "Links",
  people: "People",
};

export function Home({ session }: { session: Session }) {
  const [css, theme] = useStyletron();
  const navigate = useNavigate();
  const home = useQuery({ queryKey: ["home"], queryFn: () => get<HomeView>("home") });
  const [ask, setAsk] = useState<AskItem | null>(null);
  const [draft, setDraft] = useState<DraftItem | null>(null);
  const [allRuns, setAllRuns] = useState(false);
  const h = home.data;
  if (!h)
    return (
      <Page>
        <Skeleton rows={6} height="240px" width="100%" animation />
      </Page>
    );
  const waiting = h.asks.length + h.drafts.length;
  const runs = allRuns ? h.runs : h.runs.slice(0, 5);
  return (
    <Page>
      <Section
        title={waiting ? `Needs you · ${waiting}` : "Needs you"}
        hint="Asks wait for your approval; drafts are what Claude prepared and only you can make real."
        testId="needs-you"
      >
        {waiting === 0 && <Empty>Nothing needs you right now.</Empty>}
        {h.asks.map((a) => (
          <Row key={a.id} onClick={() => setAsk(a)} testId={`ask-${a.ref}`}>
            <Chip kind="yellow">Ask</Chip>
            <Grow>
              <Line>{a.title}</Line>
              <Muted>
                {a.project_name} · {ago(a.at)}
              </Muted>
            </Grow>
            <ChevronRight size={20} color={theme.colors.contentTertiary} />
          </Row>
        ))}
        {h.drafts.map((d) => (
          <Row key={d.id} onClick={() => setDraft(d)} testId={`draft-${d.id}`}>
            <Chip kind="blue">{DRAFT_LABEL[d.kind]}</Chip>
            <Grow>
              <Line>{d.title}</Line>
              <Muted>
                {d.project} · {ago(d.at)}
              </Muted>
            </Grow>
            <ChevronRight size={20} color={theme.colors.contentTertiary} />
          </Row>
        ))}
      </Section>

      <Section title="Projects" testId="projects">
        {h.projects.length === 0 && <Empty>No projects yet. Ask Claude to start one from your email or a few sentences.</Empty>}
        {h.projects.map((p) => {
          const late = lateness(p.days_late);
          return (
            <Row key={p.project} onClick={() => navigate(`/projects/${p.project}`)} testId={`project-${p.project}`}>
              <Grow>
                <LabelMedium>{p.name}</LabelMedium>
                <Muted>
                  {p.finish}
                  {p.sets_the_date ? ` · waiting on ${p.sets_the_date}` : ""}
                </Muted>
              </Grow>
              <div className={css({ flex: "0 0 auto", display: "grid", justifyItems: "end", gap: theme.sizing.scale100 })}>
                <LabelMedium>{fmt(p.forecast, true)}</LabelMedium>
                <Chip kind={late.late ? "red" : "green"}>{late.text}</Chip>
              </div>
              <ChevronRight size={20} color={theme.colors.contentTertiary} />
            </Row>
          );
        })}
      </Section>

      <Section
        title="Recent runs"
        hint="Each run is one message played: the plan, the gateway's decisions and the agent's report, checked against the ledger."
        right={
          h.runs.length > 5 && (
            <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => setAllRuns(!allRuns)}>
              {allRuns ? "Show fewer" : "Show all"}
            </Button>
          )
        }
        testId="runs"
      >
        {h.runs.length === 0 && <Empty>No runs yet. Open a project and play a message from its inbox.</Empty>}
        {runs.map((r) => (
          <Row key={r.run} onClick={() => navigate(`/projects/${r.project}/actions`)} testId="run">
            <Grow>
              <Line>{r.message}</Line>
              <Muted>
                {r.project_name} · {ago(r.at)}
                <span className={css({ "@media (min-width: 640px)": { display: "none" } })}>
                  {" "}
                  · allow {r.counts.allow}, ask {r.counts.ask}, deny {r.counts.deny}
                </span>
              </Muted>
            </Grow>
            <div className={css({ display: "none", gap: theme.sizing.scale200, flex: "0 0 auto", "@media (min-width: 640px)": { display: "flex" } })}>
              {r.counts.allow > 0 && <Chip kind="green">Allow {r.counts.allow}</Chip>}
              {r.counts.ask > 0 && <Chip kind="yellow">Ask {r.counts.ask}</Chip>}
              {r.counts.deny > 0 && <Chip kind="red">Deny {r.counts.deny}</Chip>}
              {r.report_ok === false && (
                <Chip kind="red" tip="The agent's report disagrees with the ledger.">
                  Report ✗
                </Chip>
              )}
            </div>
            <ChevronRight size={20} color={theme.colors.contentTertiary} />
          </Row>
        ))}
      </Section>

      <AskDrawer ask={ask} onClose={() => setAsk(null)} />
      <DraftDrawer draft={draft} local={session.local} onClose={() => setDraft(null)} />
    </Page>
  );
}

function AskDrawer({ ask, onClose }: { ask: AskItem | null; onClose: () => void }) {
  return (
    <Drawer open={!!ask} onClose={onClose} title={ask?.title} testId="ask-drawer">
      {ask && (
        <>
          <Muted>
            {ask.project_name} · {ask.route.join(" → ")}
          </Muted>
          <Field label="To">{ask.recipient ?? ask.route[ask.route.length - 1]}</Field>
          {ask.subject && <Field label="Subject">{ask.subject}</Field>}
          {ask.text && (
            <Field label="Text, as it would go out">
              <Quote>{ask.text}</Quote>
            </Field>
          )}
          <Field label={`Mandate clause${ask.mandate_version ? ` (v${ask.mandate_version})` : ""}`}>{ask.clause}</Field>
          <ApproveButtons actionId={ask.id} version={ask.mandate_version} canApprove={ask.can_approve} approvers={ask.approvers} onDone={onClose} />
        </>
      )}
    </Drawer>
  );
}

function DraftDrawer({ draft, local, onClose }: { draft: DraftItem | null; local: boolean; onClose: () => void }) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const decide = async (verdict: "confirm" | "reject") => {
    if (!draft) return;
    setBusy(true);
    try {
      const r = await send<{ message: string }>("POST", `drafts/${draft.id}`, { verdict });
      await qc.invalidateQueries();
      toaster.info(r.message, {});
      onClose();
    } catch (e) {
      toaster.negative((e as Error).message, {});
    } finally {
      setBusy(false);
    }
  };
  const color = { add: theme.colors.contentPositive, remove: theme.colors.contentNegative, assumed: theme.colors.contentWarning };
  return (
    <Drawer
      open={!!draft}
      onClose={onClose}
      title={draft?.title}
      testId="draft-drawer"
      footer={
        draft &&
        local && (
          <>
            <Button onClick={() => decide("confirm")} isLoading={busy} data-testid="confirm">
              Confirm
            </Button>
            <Button kind={KIND.secondary} onClick={() => decide("reject")} disabled={busy} data-testid="reject">
              Reject
            </Button>
          </>
        )
      }
    >
      {draft && (
        <>
          <Muted>
            {DRAFT_LABEL[draft.kind]} · {draft.project} · prepared by Claude {ago(draft.at)}
          </Muted>
          <ul className={css({ margin: 0, paddingLeft: theme.sizing.scale600, display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale200 })}>
            {draft.lines.map((l, i) => (
              <li
                key={i}
                className={css({
                  ...theme.typography.ParagraphSmall,
                  color: l.change ? color[l.change] : theme.colors.contentPrimary,
                  textDecoration: l.change === "remove" ? "line-through" : "none",
                })}
              >
                {l.text}
              </li>
            ))}
          </ul>
          {draft.note && <Muted>{draft.note}</Muted>}
          <Muted>Nothing changes until you confirm. Your confirmation is a record on the project's ledger.</Muted>
        </>
      )}
    </Drawer>
  );
}
