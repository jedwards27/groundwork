import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ChevronRight } from "baseui/icon";
import { Skeleton } from "baseui/skeleton";
import { toaster } from "baseui/toast";
import { KIND as TAG, Tag } from "baseui/tag";
import { HeadingXSmall, LabelMedium, ParagraphSmall } from "baseui/typography";
import { useState } from "react";
import { useNavigate } from "react-router";
import { get, send } from "@/lib/client";
import { ago, DEMO_PROJECT, fmt, lateness } from "@/lib/format";
import type { AskItem, DraftItem, HomeView, Session } from "@/lib/types";
import { ApproveButtons } from "./Approve";
import { STEPS, useTutorial } from "./Tutorial";
import { Chip, Drawer, Empty, Field, Grow, Line, Muted, Page, Quote, Row, Section } from "./ui";

// "Did 1 · asked you about 1 · refused 1", leaving out what's zero.
function did(c: { allow: number; ask: number; deny: number }): string {
  const parts = [
    c.allow ? `did ${c.allow} on its own` : "",
    c.ask ? `asked you about ${c.ask}` : "",
    c.deny ? `refused ${c.deny}` : "",
  ].filter(Boolean);
  const text = parts.join(", ") || "nothing to do";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

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
  const tutorial = useTutorial();
  const h = home.data;
  if (!h)
    return (
      <Page>
        <Skeleton rows={6} height="240px" width="100%" animation />
      </Page>
    );
  const waiting = h.asks.length + h.drafts.length;
  const runs = allRuns ? h.runs : h.runs.slice(0, 3);
  const demo = h.projects.some((p) => p.project === DEMO_PROJECT);
  return (
    <Page>
      {demo && !tutorial.open && !tutorial.done && (
        <div
          data-testid="tutorial-card"
          className={css({
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: theme.sizing.scale500,
            padding: theme.sizing.scale700,
            borderRadius: theme.borders.radius400,
            background: theme.colors.backgroundAccentLight,
          })}
        >
          <div className={css({ flex: "1 1 260px", display: "grid", gap: theme.sizing.scale200 })}>
            <HeadingXSmall margin={0}>{tutorial.paused === null ? "New here? Take the two-minute tutorial" : "Pick up the tutorial"}</HeadingXSmall>
            <ParagraphSmall margin={0} color={theme.colors.contentSecondary}>
              {tutorial.paused === null
                ? "See how Groundwork keeps a project's date on track, using the Lake Mariner demo."
                : `You stopped at step ${tutorial.paused + 1} of ${STEPS.length}.`}
            </ParagraphSmall>
          </div>
          <Button onClick={tutorial.start} data-testid="tutorial-card-start">
            {tutorial.paused === null ? "Start the tutorial" : "Resume"}
          </Button>
        </div>
      )}
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

      <Section
        title="Projects"
        testId="projects"
        right={
          <Button kind={KIND.secondary} size={SIZE.mini} onClick={() => navigate("/projects/new")} data-testid="new-project">
            New project
          </Button>
        }
      >
        {h.projects.length === 0 && <Empty>No projects yet. Ask Claude to start one from your email or a few sentences.</Empty>}
        {h.projects.map((p) => {
          const late = lateness(p.days_late);
          return (
            <Row key={p.project} onClick={() => navigate(`/projects/${p.project}`)} testId={`project-${p.project}`}>
              <Grow>
                <span className={css({ display: "flex", alignItems: "center", gap: theme.sizing.scale300 })}>
                  <LabelMedium>{p.name}</LabelMedium>
                  {p.project === DEMO_PROJECT && (
                    <span data-testid="tutorial-badge">
                      <Tag
                        closeable={false}
                        kind={TAG.blue}
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          tutorial.start();
                        }}
                        overrides={{ Root: { style: { margin: 0 } } }}
                      >
                        Tutorial
                      </Tag>
                    </span>
                  )}
                </span>
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
        title="What Groundwork did"
        hint="When a message comes in, Groundwork plans what to do next. It does what your mandate allows, asks you about the rest, and refuses what's never allowed."
        right={
          h.runs.length > 3 && (
            <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => setAllRuns(!allRuns)}>
              {allRuns ? "Show fewer" : "Show all"}
            </Button>
          )
        }
        testId="runs"
      >
        {h.runs.length === 0 && <Empty>Nothing yet. When a message comes in, what Groundwork did about it shows here.</Empty>}
        {runs.map((r) => (
          <Row key={r.run} onClick={() => navigate(`/projects/${r.project}/actions`)} testId="run">
            <Grow>
              <Line>{r.message}</Line>
              <Muted>{did(r.counts)} · {r.project_name} · {ago(r.at)}</Muted>
            </Grow>
            {r.report_ok === false && (
              <Chip kind="red" tip="Groundwork's own account of what it did doesn't match the ledger.">
                Doesn't add up
              </Chip>
            )}
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
