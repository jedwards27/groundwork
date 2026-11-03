import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { Button, KIND, SIZE } from "baseui/button";
import { Skeleton } from "baseui/skeleton";
import { Tab, Tabs } from "baseui/tabs-motion";
import { toaster } from "baseui/toast";
import { HeadingLarge, LabelSmall, ParagraphSmall } from "baseui/typography";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { get, send, stream } from "@/lib/client";
import { DEMO_PROJECT, fmt, fmtLong, lateness, PROVENANCE_LABEL } from "@/lib/format";
import type { ChainView, CompareRow, EventView, MandateView, Me, PlanView, RunView, Session, SiteView, Step } from "@/lib/types";
import { ActionsTab } from "./ActionsTab";
import { InboxTab, type RunState } from "./InboxTab";
import { LedgerTab } from "./LedgerTab";
import { MandateTab } from "./MandateTab";
import { Overview } from "./Overview";
import { Chip, Drawer, Field, Hint, Muted, Page, Quote } from "./ui";

const TABS = ["overview", "inbox", "actions", "mandate", "ledger"] as const;
const PANEL = { TabPanel: { style: { paddingLeft: 0, paddingRight: 0, minWidth: 0 } } };

export function Project({ session }: { session: Session }) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { key = "", tab: rawTab } = useParams();
  const tab = (TABS as readonly string[]).includes(rawTab ?? "") ? (rawTab as string) : "overview";
  const site = useQuery({ queryKey: ["site", key], queryFn: () => get<SiteView>(`sites/${key}`) });
  const chain = useQuery({ queryKey: ["chain", key], queryFn: () => get<ChainView>(`sites/${key}/chain`) });
  const events = useQuery({ queryKey: ["events", key], queryFn: () => get<EventView[]>(`sites/${key}/events`) });
  const plan = useQuery({ queryKey: ["plan", key], queryFn: () => get<PlanView | null>(`sites/${key}/latest-plan`) });
  const mandate = useQuery({ queryKey: ["mandate", key], queryFn: () => get<MandateView>(`sites/${key}/mandate`) });
  const compare = useQuery({ queryKey: ["compare", key], queryFn: () => get<{ presets: CompareRow[] }>(`sites/${key}/mandate/compare`) });
  const me = useQuery({ queryKey: ["me", key], queryFn: () => get<Me>(`sites/${key}/me`) });
  const [run, setRun] = useState<RunState | null>(null);
  const [why, setWhy] = useState(false);
  const source = useRef<EventSource | null>(null);
  useEffect(() => () => source.current?.close(), []);
  useEffect(() => {
    source.current?.close();
    setRun(null);
  }, [key]);

  const refresh = useCallback(() => qc.invalidateQueries(), [qc]);

  // Play a message: the run streams its steps; the views refresh as the forecast and decisions land.
  const play = async (eventKey: string) => {
    try {
      const { run_id } = await send<{ run_id: string }>("POST", `sites/${key}/events`, { event: eventKey });
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
        <Muted>No project “{key}”.</Muted>
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
  const party = (k: string) => s.parties.find((p) => p.key === k)?.name ?? k;
  const p = plan.data ?? null;
  const asks = p ? p.actions.filter((a) => a.state === "pending").length : 0;
  const fresh = (events.data ?? []).filter((e) => e.status !== "applied").length;
  const claudePlans = session.local && key !== DEMO_PROJECT;
  const legs = gate
    ? (events.data ?? []).filter((e) => e.status === "applied").flatMap((e) => e.impacts.filter((i) => i.item === gate.key).map((i) => ({ i, e })))
    : [];
  const subtitle = [s.asset, s.capacity_mw ? `${s.capacity_mw} MW` : "", s.location].filter(Boolean).join(" · ");
  const title = (label: string, n: number, testId: string) => (
    <span className={css({ display: "inline-flex", gap: theme.sizing.scale200, alignItems: "center" })} data-testid={testId}>
      {label}
      {n > 0 && <Chip kind={label === "Actions" ? "yellow" : "gray"}>{n}</Chip>}
    </span>
  );

  return (
    <Page>
      <section data-testid="summary">
        <Muted>{subtitle}</Muted>
        <LabelSmall color={theme.colors.contentTertiary} marginTop={theme.sizing.scale600}>
          Forecast · {ms.label}
        </LabelSmall>
        <div className={css({ display: "flex", alignItems: "center", gap: theme.sizing.scale400, flexWrap: "wrap" })}>
          <HeadingLarge margin={0} data-testid="forecast">
            {fmtLong(ms.forecast_finish)}
          </HeadingLarge>
          <Chip kind={late.late ? "red" : "green"} testId="lateness">
            {late.text}
          </Chip>
          <Hint
            text={`Target ${fmtLong(ms.target_date)} (${PROVENANCE_LABEL[ms.provenance] ?? ms.provenance}${ms.source ? `: ${ms.source}` : ""}). ${
              ms.forecast_low !== ms.forecast_high ? `Range ${fmt(ms.forecast_low)} to ${fmt(ms.forecast_high)}. ` : ""
            }${ms.days_remaining ?? "—"} days from ${fmtLong(c.as_of)}, the project's date.`}
          />
        </div>
        {gate && (
          <div className={css({ display: "flex", alignItems: "center", gap: theme.sizing.scale300, marginTop: theme.sizing.scale300, flexWrap: "wrap" })} data-testid="gate">
            <LabelSmall color={theme.colors.contentTertiary}>Waiting on</LabelSmall>
            <ParagraphSmall margin={0}>
              {gate.title} · {party(gate.owner)}
            </ParagraphSmall>
            {gate.finish_shift_days > 0 && <Chip kind="red">slipped {gate.finish_shift_days} d</Chip>}
            <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => setWhy(true)} data-testid="why">
              Why
            </Button>
          </div>
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
          <Tab key="overview" title="Overview" overrides={PANEL}>
            <Overview chain={c} site={s} plan={p} />
          </Tab>
          <Tab key="inbox" overrides={PANEL} title={title("Inbox", fresh, "tab-inbox")}>
            <InboxTab events={events.data ?? []} site={s} run={run} onPlay={play} claudePlans={claudePlans} onSeeActions={() => navigate(`/projects/${key}/actions`)} />
          </Tab>
          <Tab key="actions" overrides={PANEL} title={title("Actions", asks, "tab-actions")}>
            <ActionsTab plan={p} site={s} chain={c} me={me.data ?? null} onOpenInbox={() => navigate(`/projects/${key}/inbox`)} />
          </Tab>
          <Tab key="mandate" overrides={PANEL} title={title("Mandate", 0, "tab-mandate")}>
            {mandate.data && <MandateTab site={key} mandate={mandate.data} compare={compare.data?.presets ?? []} me={me.data ?? null} />}
          </Tab>
          <Tab key="ledger" overrides={PANEL} title={title("Ledger", 0, "tab-ledger")}>
            <LedgerTab site={key} />
          </Tab>
        </Tabs>
      </div>

      <Drawer open={why} onClose={() => setWhy(false)} title={gate ? `Why ${gate.title} sets the date` : "Why"} testId="why-drawer">
        {gate && (
          <>
            <Field label="Owner">{party(gate.owner)}</Field>
            <Field label="Dates">
              Planned {fmt(gate.planned_finish)}
              {gate.finish_shift_days > 0 ? `, now forecast ${fmt(gate.early_finish)}` : ""}.{" "}
              {(c.min_float ?? 0) >= 0 ? `${c.min_float} business days of float.` : `${-(c.min_float ?? 0)} business days behind the target.`}
            </Field>
            <Field label="Source">
              {PROVENANCE_LABEL[gate.provenance] ?? gate.provenance}
              {gate.source ? `: ${gate.source}` : ""}
            </Field>
            {legs.length > 0 && (
              <Field label="Why it moved">
                <Accordion>
                  {legs.map(({ i, e }, n) => (
                    <Panel
                      key={n}
                      title={`${i.leg} (+${i.low} to ${i.high} days)`}
                    >
                      <Muted>
                        From {party(e.from_party)}
                        {e.forwarded_from ? `, forwarding ${party(e.forwarded_from)}` : ""}, {new Date(e.received_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                      </Muted>
                      <Quote>{e.body}</Quote>
                    </Panel>
                  ))}
                </Accordion>
              </Field>
            )}
          </>
        )}
      </Drawer>
    </Page>
  );
}
