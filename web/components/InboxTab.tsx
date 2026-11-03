import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ButtonGroup, MODE } from "baseui/button-group";
import { Spinner } from "baseui/spinner";
import { LabelSmall, ParagraphSmall } from "baseui/typography";
import { useState } from "react";
import type { EventView, SiteView, Step } from "@/lib/types";
import { Chip, Drawer, Empty, Field, Grow, Line, Muted, Quote, Row } from "./ui";

export interface RunState {
  id: string;
  event: string;
  status: "running" | "done" | "failed";
  steps: Step[];
}

const KIND_LABEL: Record<string, string> = {
  schedule_change: "Schedule change",
  evidence: "Evidence",
  acknowledgment: "Auto-reply",
  injection: "Injection test",
  progress: "Progress",
};

// The demo's messages in the order the walkthrough plays them; anything else, newest first.
const ORDER = ["demo-monday", "event-a", "event-b", "ack-approved", "event-b-expedite", "eo-62", "psc-26-e-0045", "injection-expedite-po", "injection-date-change"];

const FILTERS = [
  { key: "all", label: "All", test: () => true },
  { key: "new", label: "New", test: (e: EventView) => e.status !== "applied" },
  { key: "schedule", label: "Schedule changes", test: (e: EventView) => e.kind === "schedule_change" },
  { key: "evidence", label: "Evidence", test: (e: EventView) => e.kind !== "schedule_change" },
];

export function InboxTab({ events, site, run, onPlay, claudePlans, onSeeActions }: {
  events: EventView[];
  site: SiteView;
  run: RunState | null;
  onPlay: (key: string) => void;
  claudePlans: boolean;
  onSeeActions: () => void;
}) {
  const [css, theme] = useStyletron();
  const [filter, setFilter] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  // Playing a message opens it, so its steps are in view; coming back to the tab later does not.
  const start = (key: string) => {
    setOpen(key);
    onPlay(key);
  };
  const party = (k: string | null) => (k === "public" ? "Public source" : (site.parties.find((p) => p.key === k)?.name ?? k ?? ""));
  const rank = (k: string) => (ORDER.includes(k) ? ORDER.indexOf(k) : 99);
  const sorted = [...events].sort((a, b) => rank(a.key) - rank(b.key) || (a.received_at < b.received_at ? 1 : -1));
  const shown = sorted.filter(FILTERS[filter].test);
  const busy = run?.status === "running";
  const msg = events.find((e) => e.key === open) ?? null;
  const thisRun = run && msg && run.event === msg.key ? run : null;
  const playable = (e: EventView) => e.status !== "applied" && !claudePlans;

  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale400 })}>
      <ButtonGroup mode={MODE.radio} size={SIZE.compact} selected={filter} onClick={(_, i) => setFilter(i)} overrides={{ Root: { style: { flexWrap: "wrap" } } }}>
        {FILTERS.map((f) => (
          <Button key={f.key} kind={KIND.secondary}>
            {f.label} · {sorted.filter(f.test).length}
          </Button>
        ))}
      </ButtonGroup>
      <div>
        {shown.length === 0 && <Empty>No messages here.</Empty>}
        {shown.map((e) => (
          <Row key={e.key} onClick={() => setOpen(e.key)} testId={`message-${e.key}`}>
            <span className={css({ width: "44px", flex: "0 0 auto" })}>
              <Muted>{new Date(e.received_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</Muted>
            </span>
            <Grow>
              <Line>{e.title}</Line>
              <Muted nowrap>
                {party(e.from_party)}
                {e.forwarded_from ? ` · forwarding ${party(e.forwarded_from)}` : ""} · {KIND_LABEL[e.kind] ?? e.kind}
              </Muted>
            </Grow>
            {e.scripted && (
              <Chip kind="blue" tip="Always plays the same hand-written plan, so the walkthrough is repeatable.">
                Demo
              </Chip>
            )}
            {e.status === "applied" ? (
              <Muted nowrap>Played</Muted>
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
                Play
              </Button>
            ) : (
              <Chip tip="Ask Claude in the app to play it. Claude writes the plan; Groundwork's gateway decides each action.">Claude plans this</Chip>
            )}
          </Row>
        ))}
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
                  Play this message
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
              {msg.forwarded_from ? `, forwarding ${party(msg.forwarded_from)}` : ""} ·{" "}
              {new Date(msg.received_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} ·{" "}
              {KIND_LABEL[msg.kind] ?? msg.kind}
            </Muted>
            {thisRun && (
              <Field label={thisRun.status === "running" ? "Working" : thisRun.status === "failed" ? "The run stopped" : "What happened"}>
                <ol data-testid="steps" aria-live="polite" className={css({ margin: 0, paddingLeft: theme.sizing.scale800, display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale200 })}>
                  {thisRun.steps.map((s) => (
                    <li key={s.i}>
                      <ParagraphSmall margin={0}>{s.text}</ParagraphSmall>
                    </li>
                  ))}
                </ol>
                {thisRun.status === "running" && <Spinner $size="24px" />}
                {thisRun.status === "done" && (
                  <div className={css({ marginTop: theme.sizing.scale400 })}>
                    <Button
                      onClick={() => {
                        setOpen(null);
                        onSeeActions();
                      }}
                      data-testid="see-actions"
                    >
                      See the decisions
                    </Button>
                  </div>
                )}
                {thisRun.status === "failed" && (
                  <Muted testId="run-interrupted">Everything it did up to that point is on the ledger. Play the message again to retry.</Muted>
                )}
              </Field>
            )}
            {msg.body && (
              <Field label="Message">
                <Quote>{msg.body}</Quote>
              </Field>
            )}
            {msg.impacts.length > 0 && (
              <Field label="Dates it moves">
                {msg.impacts.map((i, n) => (
                  <ParagraphSmall key={n} margin={0}>
                    {i.leg} <LabelSmall as="span" color={theme.colors.contentNegative}>+{i.low} to {i.high} days</LabelSmall>
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
