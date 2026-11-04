import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { Button, KIND, SIZE } from "baseui/button";
import { Banner, KIND as BANNER } from "baseui/banner";
import { Skeleton } from "baseui/skeleton";
import { Tab, Tabs } from "baseui/tabs-motion";
import { toaster } from "baseui/toast";
import { ChevronRight } from "baseui/icon";
import { HeadingLarge, LabelSmall, ParagraphSmall } from "baseui/typography";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { get, send, stream } from "@/lib/client";
import { getKey, useKey } from "@/lib/key";
import { DEMO_PROJECT, fmt, fmtLong, lateness } from "@/lib/format";
import type { ChainView, CompareRow, EventView, MandateView, Me, PlanView, RunView, Session, SiteView, Step } from "@/lib/types";
import { ActionsTab } from "./ActionsTab";
import { InboxTab, type RunState } from "./InboxTab";
import { LedgerTab } from "./LedgerTab";
import { Overview } from "./Overview";
import { SettingsTab } from "./SettingsTab";
import { StepsTab } from "./StepsTab";
import { DEMO_EXTRAS, useTutorial } from "./Tutorial";
import { Chip, Drawer, Field, Muted, Page, Quote } from "./ui";
import { project as say } from "@/copy/project";
import { tutorial as t } from "@/copy/tutorial";

const TABS = ["overview", "steps", "inbox", "actions", "ledger", "settings"] as const;
const PANEL = { TabPanel: { style: { paddingLeft: 0, paddingRight: 0, minWidth: 0 } } };

export function Project({ session }: { session: Session }) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { key = "", tab: rawTab } = useParams();
  // The mandate used to have its own tab; old links land on Settings, where it lives now.
  const wanted = rawTab === "mandate" ? "settings" : rawTab;
  const tab = (TABS as readonly string[]).includes(wanted ?? "") ? (wanted as string) : "overview";
  const site = useQuery({ queryKey: ["site", key], queryFn: () => get<SiteView>(`sites/${key}`) });
  const chain = useQuery({ queryKey: ["chain", key], queryFn: () => get<ChainView>(`sites/${key}/chain`) });
  const events = useQuery({ queryKey: ["events", key], queryFn: () => get<EventView[]>(`sites/${key}/events`) });
  const plan = useQuery({ queryKey: ["plan", key], queryFn: () => get<PlanView | null>(`sites/${key}/latest-plan`) });
  const mandate = useQuery({ queryKey: ["mandate", key], queryFn: () => get<MandateView>(`sites/${key}/mandate`) });
  const compare = useQuery({ queryKey: ["compare", key], queryFn: () => get<{ presets: CompareRow[] }>(`sites/${key}/mandate/compare`) });
  const me = useQuery({ queryKey: ["me", key], queryFn: () => get<Me>(`sites/${key}/me`) });
  const [run, setRun] = useState<RunState | null>(null);
  const [why, setWhy] = useState(false);
  const [busy, setBusy] = useState(false);
  const tutorial = useTutorial();
  const keyInTab = useKey();
  const source = useRef<EventSource | null>(null);
  useEffect(() => () => source.current?.close(), []);
  useEffect(() => {
    source.current?.close();
    setRun(null);
  }, [key]);

  const refresh = useCallback(() => qc.invalidateQueries(), [qc]);

  const restore = async () => {
    setBusy(true);
    try {
      const r = await send<{ message: string }>("POST", `projects/${key}/restore`);
      toaster.info(r.message, {});
      await qc.invalidateQueries();
    } catch (e) {
      toaster.negative((e as Error).message, {});
    } finally {
      setBusy(false);
    }
  };

  // Play a message: the run streams its steps; the views refresh as the forecast and decisions land.
  const play = async (eventKey: string) => {
    try {
      // With a key set for this tab, Claude plans it live; the key goes with this request only.
      const apiKey = getKey();
      const { run_id } = await send<{ run_id: string }>("POST", `sites/${key}/events`, { event: eventKey }, apiKey ? { "x-anthropic-api-key": apiKey } : undefined);
      setRun({ id: run_id, event: eventKey, status: "running", steps: [] });
      source.current?.close();
      const es = stream(`runs/${run_id}/stream`);
      source.current = es;
      es.addEventListener("step", (m) => {
        const step = JSON.parse((m as MessageEvent).data) as Step;
        setRun((r) => (r && r.id === run_id ? { ...r, steps: [...r.steps.filter((s) => s.i !== step.i), step] } : r));
        if (["forecast", "executed", "differential"].includes(step.kind)) void refresh();
      });
      es.addEventListener("end", (m) => {
        const rv = JSON.parse((m as MessageEvent).data) as RunView;
        setRun((r) => (r && r.id === run_id ? { ...r, status: rv.status === "failed" ? "failed" : "done" } : r));
        es.close();
        void refresh();
        // The blind arm trails the run; pick up its scorecard rows shortly after.
        setTimeout(() => void qc.invalidateQueries({ queryKey: ["scorecard"] }), 4000);
      });
    } catch (e) {
      toaster.negative((e as Error).message, {});
    }
  };

  if (site.isError)
    return (
      <Page>
        <Muted>{say.notFound(key)}</Muted>
      </Page>
    );
  if (!site.data || !chain.data)
    return (
      <Page>
        <Skeleton rows={5} height="220px" width="100%" animation />
      </Page>
    );
  const s = site.data;
  const c = chain.data;
  const ms = c.milestone;
  const late = lateness(ms.delta_days);
  const gate = c.items.find((i) => i.key === c.gate);
  // The steps that decide the date, from what it waits on now to the finish.
  const byKey = new Map(c.items.map((i) => [i.key, i]));
  const fromGate = c.gate ? c.critical_path.slice(Math.max(0, c.critical_path.indexOf(c.gate))) : c.critical_path;
  const path = fromGate.map((k) => byKey.get(k)).filter((i): i is NonNullable<typeof i> => !!i);
  const party = (k: string) => s.parties.find((p) => p.key === k)?.name ?? k;
  const p = plan.data ?? null;
  const asks = p ? p.actions.filter((a) => a.state === "pending").length : 0;
  // The demo's inbox keeps to the messages worth playing. The extras show once played, or whenever this
  // tab has an API key, so Claude has the hard cases to plan. Never during the tour, which plays one of them.
  const showExtras = Boolean(keyInTab) && !tutorial.open;
  const inbox = (events.data ?? []).filter((e) => key !== DEMO_PROJECT || showExtras || !DEMO_EXTRAS.has(e.key) || e.status === "applied");
  const fresh = inbox.filter((e) => e.status !== "applied").length;
  const claudePlans = session.local && key !== DEMO_PROJECT;
  const mine = session.local && !session.health.hosted;
  const stale = Object.keys(c.stale ?? {}).length;
  const follows = s.attrs.follows;
  const legs = gate
    ? (events.data ?? []).filter((e) => e.status === "applied").flatMap((e) => e.impacts.filter((i) => i.item === gate.key).map((i) => ({ i, e })))
    : [];
  const title = (label: string, n: number, testId: string, urgent = false) => (
    <span className={css({ display: "inline-flex", gap: theme.sizing.scale200, alignItems: "center" })} data-testid={testId}>
      {label}
      {n > 0 && <Chip kind={urgent ? "yellow" : "gray"}>{n}</Chip>}
    </span>
  );

  return (
    <Page>
      {s.archived_at && (
        <Banner
          kind={BANNER.info}
          overrides={{ Root: { style: { marginLeft: 0, marginRight: 0, marginTop: 0 } } }}
          action={mine && !busy ? { label: say.archived.restore, onClick: () => void restore() } : undefined}
        >
          <span data-testid="archived-banner">{say.archived.banner(fmtLong(s.archived_at.slice(0, 10)))}</span>
        </Banner>
      )}
      <section data-testid="summary">
        <div className={css({ display: "flex", alignItems: "center", gap: theme.sizing.scale300 })}>
          <LabelSmall color={theme.colors.contentTertiary}>{ms.label}</LabelSmall>
          {follows && (
            <LabelSmall color={theme.colors.contentTertiary}>
              (<a href={`/projects/${follows}`} onClick={(e) => { e.preventDefault(); navigate(`/projects/${follows}`); }}>{say.follows(follows)}</a>)
            </LabelSmall>
          )}
          <span className={css({ marginLeft: "auto", display: "inline-flex", gap: theme.sizing.scale200 })}>
            {key === DEMO_PROJECT && !tutorial.open && (
              <Button kind={KIND.secondary} size={SIZE.mini} onClick={tutorial.start} data-testid="tutorial-start">
                {t.projectButton}
              </Button>
            )}
          </span>
        </div>
        <div className={css({ display: "flex", alignItems: "center", gap: theme.sizing.scale400, flexWrap: "wrap" })}>
          <HeadingLarge margin={0} data-testid="forecast">
            {fmtLong(ms.forecast_finish)}
          </HeadingLarge>
          <Chip kind={late.late ? "red" : "green"} testId="lateness">
            {late.text}
          </Chip>
        </div>
        {gate && (
          <button
            type="button"
            onClick={() => setWhy(true)}
            data-testid="gate"
            className={css({
              all: "unset",
              boxSizing: "border-box",
              marginTop: theme.sizing.scale400,
              display: "flex",
              alignItems: "center",
              gap: theme.sizing.scale300,
              flexWrap: "wrap",
              cursor: "pointer",
              padding: `${theme.sizing.scale200} ${theme.sizing.scale300}`,
              marginLeft: `-${theme.sizing.scale300}`,
              borderRadius: theme.borders.radius200,
              ":hover": { background: theme.colors.backgroundSecondary },
              ":focus-visible": { outline: `2px solid ${theme.colors.borderSelected}` },
            })}
          >
            <LabelSmall color={theme.colors.contentTertiary}>{say.summary.waitingOn}</LabelSmall>
            <ParagraphSmall margin={0}>{gate.title}</ParagraphSmall>
            <ChevronRight size={18} color={theme.colors.contentTertiary} />
          </button>
        )}
      </section>

      <div className={css({ marginTop: theme.sizing.scale700, minWidth: 0, maxWidth: "100%", overflow: "hidden" })}>
        <Tabs
          activeKey={tab}
          onChange={({ activeKey }) => navigate(`/projects/${key}/${activeKey}`, { replace: true })}
          activateOnFocus
          overrides={{
            Root: { style: { minWidth: 0 } },
            TabList: { style: { overflowX: "auto" } },
          }}
        >
          <Tab key="overview" title={say.tabs.overview} overrides={PANEL}>
            <Overview chain={c} site={s} />
          </Tab>
          <Tab key="steps" overrides={PANEL} title={title(say.tabs.steps, 0, "tab-steps")}>
            <StepsTab chain={c} site={s} mine={mine} />
          </Tab>
          <Tab key="inbox" overrides={PANEL} title={title(say.tabs.inbox, fresh, "tab-inbox")}>
            <InboxTab events={inbox} site={s} run={run} onPlay={play} claudePlans={claudePlans} onSeeActions={() => navigate(`/projects/${key}/actions`)} />
          </Tab>
          <Tab key="actions" overrides={PANEL} title={title(say.tabs.actions, asks, "tab-actions", true)}>
            <ActionsTab plan={p} site={s} chain={c} me={me.data ?? null} onOpenInbox={() => navigate(`/projects/${key}/inbox`)} />
          </Tab>
          <Tab key="ledger" overrides={PANEL} title={title(say.tabs.ledger, 0, "tab-ledger")}>
            <LedgerTab site={key} tamper={key === DEMO_PROJECT && !session.health.hosted} />
          </Tab>
          <Tab key="settings" overrides={PANEL} title={title(say.tabs.settings, 0, "tab-settings")}>
            <SettingsTab site={s} mandate={mandate.data} compare={compare.data?.presets ?? []} plan={p} me={me.data ?? null} mine={mine} session={session} />
          </Tab>
        </Tabs>
      </div>


      <Drawer open={why} onClose={() => setWhy(false)} title={say.why.title} testId="why-drawer">
        <Muted>
          {say.why.forecast(
            ms.label,
            fmtLong(ms.forecast_finish),
            ms.forecast_low !== ms.forecast_high ? say.why.range(fmt(ms.forecast_low), fmt(ms.forecast_high)) : "",
            fmtLong(ms.target_date),
          )}
        </Muted>
        <Field label={say.why.pathLabel}>
          <ol className={css({ margin: 0, paddingLeft: theme.sizing.scale700, display: "grid", gap: theme.sizing.scale300 })} data-testid="path">
            {path.map((i) => (
              <li key={i.key}>
                <ParagraphSmall margin={0}>
                  {i.title} {i.key === c.gate && <Chip kind={i.finish_shift_days > 0 ? "red" : "gray"}>{say.why.now}</Chip>}
                </ParagraphSmall>
                <Muted>
                  {party(i.owner)}, {i.status === "done" ? say.why.done : say.why.due(fmt(i.early_finish))}
                  {i.finish_shift_days > 0 ? say.why.later(i.finish_shift_days) : ""}
                </Muted>
              </li>
            ))}
          </ol>
        </Field>
        <Muted>{say.why.slack}</Muted>
        {stale > 0 && <Muted testId="why-stale">{say.why.stale(stale)}</Muted>}
        {legs.length > 0 && (
          <Field label={say.why.movedLabel}>
            <Accordion>
              {legs.map(({ i, e }, n) => (
                <Panel key={n} title={say.why.moved(i.leg, i.low, i.high)}>
                  <Muted>
                    {say.why.from(
                      party(e.from_party),
                      e.forwarded_from ? party(e.forwarded_from) : null,
                      new Date(e.received_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
                    )}
                  </Muted>
                  <Quote>{e.body}</Quote>
                </Panel>
              ))}
            </Accordion>
          </Field>
        )}
      </Drawer>
    </Page>
  );
}
