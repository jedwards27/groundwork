import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ButtonGroup, MODE } from "baseui/button-group";
import { Check } from "baseui/icon";
import { Spinner } from "baseui/spinner";
import { LabelSmall, ParagraphSmall } from "baseui/typography";
import { useEffect, useState } from "react";
import type { EventView, SiteView, Step } from "@/lib/types";
import { project } from "@/copy/project";
import { Chip, Drawer, Empty, Field, Grow, Line, matches, Muted, Quote, Row, Search, usePages } from "./ui";

const say = project.inbox;
const sayRun = project.run;

export interface RunState {
  id: string;
  event: string;
  status: "running" | "done" | "failed";
  steps: Step[];
}

const KIND_LABEL = say.kinds;

// The demo's messages in the order the walkthrough plays them; anything else, newest first.
const ORDER = ["demo-monday", "event-a", "event-b", "ack-approved", "event-b-expedite", "eo-62", "psc-26-e-0045", "injection-expedite-po", "injection-date-change"];

const FILTERS = [
  { key: "all", label: say.filters.all, test: () => true },
  { key: "new", label: say.filters.new, test: (e: EventView) => e.status !== "applied" },
  { key: "schedule", label: say.filters.schedule, test: (e: EventView) => e.kind === "schedule_change" },
  { key: "evidence", label: say.filters.evidence, test: (e: EventView) => e.kind !== "schedule_change" },
];

export function InboxTab({ events, site, run, onPlay, claudePlans, onSeeActions, note }: {
  events: EventView[];
  note?: string;
  site: SiteView;
  run: RunState | null;
  onPlay: (key: string) => void;
  claudePlans: boolean;
  onSeeActions: () => void;
}) {
  const [css, theme] = useStyletron();
  const [filter, setFilter] = useState(0);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  // Playing a message opens it, so its steps are in view; coming back to the tab later does not.
  const start = (key: string) => {
    setOpen(key);
    onPlay(key);
  };
  const party = (k: string | null) => (k === "public" ? say.publicSource : (site.parties.find((p) => p.key === k)?.name ?? k ?? ""));
  const rank = (k: string) => (ORDER.includes(k) ? ORDER.indexOf(k) : 99);
  const sorted = [...events].sort((a, b) => rank(a.key) - rank(b.key) || (a.received_at < b.received_at ? 1 : -1));
  const shown = sorted.filter((e) => FILTERS[filter].test(e) && matches(q, e.title, e.body, party(e.from_party), e.forwarded_from ? party(e.forwarded_from) : ""));
  const { rows: page, pager } = usePages(shown, 20, `${filter}|${q}`);
  const busy = run?.status === "running";
  const msg = events.find((e) => e.key === open) ?? null;
  const thisRun = run && msg && run.event === msg.key ? run : null;
  const playable = (e: EventView) => e.status !== "applied" && !claudePlans;

  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale400 })}>
      <div className={css({ display: "flex", flexWrap: "wrap", gap: theme.sizing.scale400, alignItems: "center" })}>
        <ButtonGroup mode={MODE.radio} size={SIZE.compact} selected={filter} onClick={(_, i) => setFilter(i)} overrides={{ Root: { style: { flexWrap: "wrap" } } }}>
          {FILTERS.map((f) => (
            <Button key={f.key} kind={KIND.secondary}>
              {say.filterCount(f.label, sorted.filter(f.test).length)}
            </Button>
          ))}
        </ButtonGroup>
        <Search value={q} onChange={setQ} placeholder={say.search} testId="inbox-search" />
      </div>
      <div>
        {shown.length === 0 && <Empty>{say.empty}</Empty>}
        {note && <Muted testId="inbox-note">{note}</Muted>}
        {page.map((e) => (
          <Row key={e.key} onClick={() => setOpen(e.key)} testId={`message-${e.key}`}>
            <span className={css({ width: "44px", flex: "0 0 auto" })}>
              <Muted>{new Date(e.received_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</Muted>
            </span>
            <Grow>
              <Line>{e.title}</Line>
              <Muted nowrap>
                {party(e.from_party)}
                {e.forwarded_from ? say.forwarding(party(e.forwarded_from)) : ""} ({KIND_LABEL[e.kind] ?? e.kind})
              </Muted>
            </Grow>
            {e.scripted && (
              <Chip kind="blue" tip={say.demoTip}>
                {say.demo}
              </Chip>
            )}
            {e.status === "applied" ? (
              <Muted nowrap>{say.played}</Muted>
            ) : playable(e) ? (
              <Button
                size={SIZE.mini}
                kind={e.scripted ? KIND.primary : KIND.secondary}
                disabled={busy}
                onClick={(ev) => {
                  ev.stopPropagation();
                  start(e.key);
                }}
                data-testid={`play-${e.key}`}
              >
                {say.play}
              </Button>
            ) : (
              <Chip tip={say.claudePlansTip}>{say.claudePlans}</Chip>
            )}
          </Row>
        ))}
        {pager}
      </div>

      <Drawer
        open={!!msg}
        onClose={() => setOpen(null)}
        title={msg?.title}
        testId="message-drawer"
        footer={
          msg && (
            <>
              {playable(msg) && !thisRun && (
                <Button onClick={() => start(msg.key)} disabled={busy} data-testid="drawer-play">
                  {say.playThis}
                </Button>
              )}
            </>
          )
        }
      >
        {msg && (
          <>
            <Muted>
              {party(msg.from_party)}
              {msg.forwarded_from ? say.forwardingComma(party(msg.forwarded_from)) : ""},{" "}
              {new Date(msg.received_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} ({KIND_LABEL[msg.kind] ?? msg.kind})
            </Muted>
            {thisRun && (
              <RunSteps
                key={thisRun.id}
                run={thisRun}
                simulated={msg.scripted}
                onSeeActions={() => {
                  setOpen(null);
                  onSeeActions();
                }}
              />
            )}
            {msg.body && (
              <Field label={say.message}>
                <Quote>{msg.body}</Quote>
              </Field>
            )}
            {msg.impacts.length > 0 && (
              <Field label={say.datesItMoves}>
                {msg.impacts.map((i, n) => (
                  <ParagraphSmall key={n} margin={0}>
                    {i.leg} <LabelSmall as="span" color={theme.colors.contentNegative}>{say.moves(i.low, i.high)}</LabelSmall>
                  </ParagraphSmall>
                ))}
              </Field>
            )}
          </>
        )}
      </Drawer>
    </div>
  );
}

// How long each step stays the newest before the next appears. A live run takes about this long
// per step; a demo message's written plan finishes at once, so it is shown at this pace instead.
const PACE_MS = 1100;

// The run as it happens, one plain line per step. The comparison plan made without the mandate is
// kept on the ledger for the record but is not part of what the person follows here.
function RunSteps({ run, simulated, onSeeActions }: { run: RunState; simulated: boolean; onSeeActions: () => void }) {
  const [css, theme] = useStyletron();
  const steps = run.steps.filter((s) => !s.kind.startsWith("blind"));
  // A run you open after it finished shows all of it; one you start plays out step by step.
  const [shown, setShown] = useState(() => (run.status === "running" ? 0 : steps.length));
  useEffect(() => {
    if (shown >= steps.length) return;
    const timer = setTimeout(() => setShown((n) => n + 1), shown === 0 ? 300 : PACE_MS);
    return () => clearTimeout(timer);
  }, [shown, steps.length]);
  const visible = steps.slice(0, shown);
  const working = run.status === "running" || shown < steps.length;
  const status = working ? "running" : run.status;
  const counts = steps.find((s) => s.kind === "decided")?.counts as { auto: number; ask: number; refuse: number } | undefined;
  const total = counts ? counts.auto + counts.ask + counts.refuse : 0;
  return (
    <Field label={status === "running" ? sayRun.working : status === "failed" ? sayRun.stopped : sayRun.done}>
      {/* Finished: the result and the next click come first, so the drawer opens at the top. */}
      {status === "done" && total > 0 && (
        <div data-testid="run-done" className={css({ marginBottom: theme.sizing.scale500, padding: theme.sizing.scale500, borderRadius: theme.borders.radius300, background: theme.colors.backgroundSecondary, display: "grid", gap: theme.sizing.scale400 })}>
          <ParagraphSmall margin={0}>{sayRun.finished(total)}</ParagraphSmall>
          <div>
            <Button size={SIZE.compact} onClick={onSeeActions} data-testid="see-actions">
              {sayRun.seeSteps(total)}
            </Button>
          </div>
        </div>
      )}
      {simulated && (
        <Muted testId="simulated-run">{sayRun.simulated}</Muted>
      )}
      <ol data-testid="steps" aria-live="polite" className={css({ listStyle: "none", margin: 0, padding: 0, display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale300 })}>
        {visible.map((s, n) => {
          const current = working && n === visible.length - 1;
          return (
            <li key={s.i} className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "flex-start" })}>
              <span className={css({ flex: "0 0 18px", display: "flex", justifyContent: "center", paddingTop: "2px" })}>
                {current ? <Spinner $size="14px" $borderWidth="2px" /> : <Check size={18} color={theme.colors.contentPositive} />}
              </span>
              <ParagraphSmall margin={0}>{s.text}</ParagraphSmall>
            </li>
          );
        })}
        {working && visible.length === 0 && <Spinner $size="18px" $borderWidth="2px" />}
      </ol>
      {status === "done" && total === 0 && <Muted testId="run-done">{sayRun.nothingToDo}</Muted>}
      {status === "failed" && <Muted testId="run-interrupted">{sayRun.interrupted}</Muted>}
    </Field>
  );
}
