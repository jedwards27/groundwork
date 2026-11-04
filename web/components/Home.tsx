import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ChevronRight } from "baseui/icon";
import { Skeleton } from "baseui/skeleton";
import { toaster } from "baseui/toast";
import { KIND as TAG, Tag } from "baseui/tag";
import { HeadingXSmall, LabelMedium, ParagraphSmall } from "baseui/typography";
import { Input } from "baseui/input";
import { useState } from "react";
import { useNavigate } from "react-router";
import { get, send } from "@/lib/client";
import { ago, DEMO_PROJECT, fmt, lateness, reasonSentence } from "@/lib/format";
import type { AskItem, DraftItem, HomeView, Session } from "@/lib/types";
import { ApproveButtons } from "./Approve";
import { STEPS, useTutorial } from "./Tutorial";
import { Accordion, Panel } from "baseui/accordion";
import { home as say } from "@/copy/home";
import { project } from "@/copy/project";
import { tutorial as t } from "@/copy/tutorial";
import { Chip, Drawer, Empty, Field, Grow, Line, Muted, Outgoing, Page, Rich, Row, Section } from "./ui";
import { app } from "@/copy/app";

// "Did 1 on its own, asked you about 1, denied 1", leaving out what's zero.
function did(c: { allow: number; ask: number; deny: number }): string {
  const parts = [c.allow ? say.activity.did(c.allow) : "", c.ask ? say.activity.asked(c.ask) : "", c.deny ? say.activity.refused(c.deny) : ""].filter(Boolean);
  const text = parts.join(", ") || say.activity.nothing;
  return text.charAt(0).toUpperCase() + text.slice(1);
}


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
  // Your own projects' asks and drafts first; the demo's carry a Demo tag.
  const asks = [...h.asks].sort((a, b) => Number(a.project === DEMO_PROJECT) - Number(b.project === DEMO_PROJECT));
  const draftsMine = [...h.drafts].sort((a, b) => Number(a.project === DEMO_PROJECT) - Number(b.project === DEMO_PROJECT));
  const demoTag = (project: string) =>
    project === DEMO_PROJECT && h.projects.length > 1 ? (
      <Chip kind="gray" tip={say.needsYou.demoTip} testId="demo-tag">
        {say.needsYou.demo}
      </Chip>
    ) : null;
  const archived = h.archived ?? [];
  const runs = allRuns ? h.runs : h.runs.slice(0, 3);
  const demo = h.projects.some((p) => p.project === DEMO_PROJECT);
  const hosted = !!session.health.hosted;
  return (
    <Page>
      {hosted && (
        <div data-testid="demo-banner" className={css({ ...theme.typography.ParagraphSmall, padding: `${theme.sizing.scale400} ${theme.sizing.scale600}`, marginBottom: theme.sizing.scale600, borderRadius: theme.borders.radius300, background: theme.colors.backgroundWarningLight, color: theme.colors.contentPrimary })}>
          <Rich text={app.demo.banner} />
        </div>
      )}
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
            <HeadingXSmall margin={0}>{tutorial.paused === null ? t.card.title : t.card.pausedTitle}</HeadingXSmall>
            <ParagraphSmall margin={0} color={theme.colors.contentSecondary}>
              {tutorial.paused === null ? t.card.body : t.card.pausedBody(tutorial.paused + 1, STEPS.length)}
            </ParagraphSmall>
          </div>
          <Button onClick={tutorial.start} data-testid="tutorial-card-start">
            {tutorial.paused === null ? t.card.start : t.card.resume}
          </Button>
        </div>
      )}
      <Section
        title={waiting ? say.needsYou.titleWithCount(waiting) : say.needsYou.title}
        hint={say.needsYou.hint}
        testId="needs-you"
      >
        {waiting === 0 && <Empty>{say.needsYou.empty}</Empty>}
        {asks.map((a) => (
          <Row key={a.id} onClick={() => setAsk(a)} testId={`ask-${a.ref}`}>
            <Chip kind="yellow">{say.needsYou.ask}</Chip>
            {demoTag(a.project)}
            <Grow>
              <Line>{a.title}</Line>
              <Muted>{say.needsYou.row(a.project_name, ago(a.at))}</Muted>
            </Grow>
            <ChevronRight size={20} color={theme.colors.contentTertiary} />
          </Row>
        ))}
        {draftsMine.map((d) => (
          <Row key={d.id} onClick={() => setDraft(d)} testId={`draft-${d.id}`}>
            <Chip kind={d.kind === "delete" ? "red" : "blue"}>{say.draftKinds[d.kind]}</Chip>
            {demoTag(d.project)}
            <Grow>
              <Line>{d.title}</Line>
              <Muted>{say.needsYou.row(d.project, ago(d.at))}</Muted>
            </Grow>
            <ChevronRight size={20} color={theme.colors.contentTertiary} />
          </Row>
        ))}
      </Section>

      <Section
        title={say.projects.title}
        testId="projects"
        right={
          !hosted && (
            <Button kind={KIND.secondary} size={SIZE.mini} onClick={() => navigate("/projects/new")} data-testid="new-project">
              {say.projects.newProject}
            </Button>
          )
        }
      >
        {h.projects.length === 0 && <Empty>{say.projects.empty}</Empty>}
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
                        {say.projects.tutorial}
                      </Tag>
                    </span>
                  )}
                </span>
                <Muted>
                  {p.finish}
                  {p.sets_the_date ? say.projects.waitingOn(p.sets_the_date) : ""}
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

      {archived.length > 0 && (
        <Accordion overrides={{ Content: { style: { paddingLeft: 0, paddingRight: 0 } }, Header: { style: { paddingLeft: 0, paddingRight: 0 } } }}>
          <Panel title={say.archived.title(archived.length)}>
            <Muted>{say.archived.hint}</Muted>
            {archived.map((p) => (
              <Row key={p.project} onClick={() => navigate(`/projects/${p.project}`)} testId={`archived-${p.project}`}>
                <Grow>
                  <Line>{p.name}</Line>
                  <Muted>{say.archived.row(p.archived_at ? ago(p.archived_at) : "")}</Muted>
                </Grow>
                <ChevronRight size={20} color={theme.colors.contentTertiary} />
              </Row>
            ))}
          </Panel>
        </Accordion>
      )}

      <Section
        title={say.activity.title}
        hint={say.activity.hint}
        right={
          h.runs.length > 3 && (
            <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => setAllRuns(!allRuns)}>
              {allRuns ? say.activity.showFewer : say.activity.showAll}
            </Button>
          )
        }
        testId="runs"
      >
        {h.runs.length === 0 && <Empty>{say.activity.empty}</Empty>}
        {runs.map((r) => (
          <Row key={r.run} onClick={() => navigate(`/projects/${r.project}/actions`)} testId="run">
            <Grow>
              <Line>{r.message}</Line>
              <Muted>{say.activity.row(did(r.counts), r.project_name, ago(r.at))}</Muted>
            </Grow>
            {r.report_ok === false && (
              <Chip kind="red" tip={say.activity.mismatchTip}>
                {say.activity.mismatch}
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
  const say2 = project.action;
  return (
    <Drawer open={!!ask} onClose={onClose} title={ask?.title} testId="ask-drawer">
      {ask && (
        <>
          <Muted>{ask.project_name}</Muted>
          <Outgoing
            label={ask.subject || ask.text ? say2.asItGoesOut : say2.whatItWouldDo}
            to={say2.to(ask.recipient ?? ask.route[ask.route.length - 1])}
            subject={ask.subject}
            text={ask.text}
            testId="outgoing"
          />
          <ApproveButtons actionId={ask.id} version={ask.mandate_version} canApprove={ask.can_approve} approvers={ask.approvers} onDone={onClose} />
          {ask.reason && <Field label={say2.why.ask}>{reasonSentence(ask.reason)}</Field>}
          <Accordion renderAll overrides={{ Content: { style: { paddingLeft: 0, paddingRight: 0 } }, Header: { style: { paddingLeft: 0, paddingRight: 0 } } }}>
            <Panel title={say.ask.details}>
              <div style={{ display: "grid", gap: 16 }}>
                <Field label={say.ask.route}>{ask.route.join(" → ")}</Field>
                <Field label={say2.clause(ask.mandate_version)}>{ask.clause}</Field>
              </div>
            </Panel>
          </Accordion>
        </>
      )}
    </Drawer>
  );
}

function DraftDrawer({ draft, local, onClose }: { draft: DraftItem | null; local: boolean; onClose: () => void }) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const needs = draft?.type_to_confirm ?? null;
  const decide = async (verdict: "confirm" | "reject") => {
    if (!draft) return;
    setBusy(true);
    try {
      const r = await send<{ message: string }>("POST", `drafts/${draft.id}`, { verdict, ...(needs ? { typed } : {}) });
      setTyped("");
      await qc.invalidateQueries();
      toaster.info(r.message, {});
      onClose();
    } catch (e) {
      toaster.negative((e as Error).message, {});
    } finally {
      setBusy(false);
    }
  };
  const color = { add: theme.colors.contentPositive, remove: theme.colors.contentNegative, assumed: theme.colors.contentWarning, cancel: theme.colors.contentTertiary };
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
            <Button onClick={() => decide("confirm")} isLoading={busy} disabled={!!needs && typed.trim() !== needs} data-testid="confirm">
              {needs ? say.draft.deleteForGood : say.draft.confirm}
            </Button>
            <Button kind={KIND.secondary} onClick={() => decide("reject")} disabled={busy} data-testid="reject">
              {say.draft.reject}
            </Button>
          </>
        )
      }
    >
      {draft && (
        <>
          <Muted>
            {say.draft.prepared(say.draftKinds[draft.kind], draft.project, ago(draft.at))}
          </Muted>
          <ul className={css({ margin: 0, paddingLeft: theme.sizing.scale600, display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale200 })}>
            {draft.lines.map((l, i) => (
              <li
                key={i}
                className={css({
                  ...theme.typography.ParagraphSmall,
                  color: l.change ? color[l.change] : theme.colors.contentPrimary,
                  textDecoration: l.change === "remove" || l.change === "cancel" ? "line-through" : "none",
                })}
              >
                {l.text}
              </li>
            ))}
          </ul>
          {draft.note && <Muted>{draft.note}</Muted>}
          {needs && local && (
            <Input value={typed} onChange={(e) => setTyped((e.target as HTMLInputElement).value)} placeholder={say.draft.typeToConfirm(needs)} overrides={{ Input: { props: { "data-testid": "draft-typed" } } }} />
          )}
          <Muted>{needs ? say.draft.footerDelete : say.draft.footer}</Muted>
        </>
      )}
    </Drawer>
  );
}
