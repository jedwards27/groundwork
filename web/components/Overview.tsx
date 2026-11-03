import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { LabelXSmall, ParagraphSmall } from "baseui/typography";
import { daysBetween, fmt, PROVENANCE_LABEL } from "@/lib/format";
import { stages } from "@/lib/stages";
import type { ChainView, PlanView, SiteView } from "@/lib/types";
import { Chain } from "./Chain";
import { Grow, Hint, Line, Muted, Row } from "./ui";

export function Overview({ chain, site, plan }: { chain: ChainView; site: SiteView; plan: PlanView | null }) {
  const [css, theme] = useStyletron();
  const st = stages(chain.items);
  const d = plan?.differential;
  const open = chain.items.filter((i) => i.status !== "done").sort((a, b) => (a.early_finish < b.early_finish ? -1 : 1));
  const party = (k: string) => site.parties.find((p) => p.key === k)?.name ?? k;
  const panel = { PanelContainer: { style: { borderBottomColor: theme.colors.borderOpaque } } };
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale600 })}>
      {st.length > 0 ? (
        <ol
          aria-label="Delivery stages"
          data-testid="stages"
          className={css({ display: "flex", gap: theme.sizing.scale300, listStyle: "none", margin: 0, padding: 0, overflowX: "auto" })}
        >
          {st.map((s) => {
            const bar = {
              done: theme.colors.contentPositive,
              delayed: theme.colors.contentNegative,
              active: theme.colors.contentAccent,
              pending: theme.colors.borderOpaque,
            }[s.status];
            return (
              <li key={s.key} className={css({ flex: "1 0 96px", borderTop: `3px solid ${bar}`, paddingTop: theme.sizing.scale200 })}>
                <LabelXSmall>{s.label}</LabelXSmall>
                <Muted>{s.note}</Muted>
              </li>
            );
          })}
        </ol>
      ) : (
        <div data-testid="waiting">
          {open.slice(0, 6).map((i) => (
            <Row key={i.key}>
              <Grow>
                <Line>{i.title}</Line>
                <Muted>{party(i.owner)}</Muted>
              </Grow>
              <ParagraphSmall margin={0} color={i.finish_shift_days > 0 ? theme.colors.contentNegative : theme.colors.contentSecondary}>
                {fmt(i.early_finish)}
                {i.finish_shift_days > 0 ? ` (+${i.finish_shift_days} d)` : ""}
              </ParagraphSmall>
            </Row>
          ))}
        </div>
      )}
      <Accordion overrides={panel}>
        <Panel
          title={
            <span className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", width: "100%" })}>
              What the plan changes
              <Muted>{d ? `${d.recovered_if_they_agree} days back if they agree` : "after a message is played"}</Muted>
            </span>
          }
        >
          <Differential chain={chain} plan={plan} />
        </Panel>
        <Panel title="Paper chain">
          <Chain chain={chain} />
        </Panel>
        {chain.calendar_losses.length > 0 && (
          <Panel title="Hidden in the calendar">
            {chain.calendar_losses.map((l, n) => (
              <ParagraphSmall key={n} marginTop={0}>
                {l.sentence}
              </ParagraphSmall>
            ))}
          </Panel>
        )}
        {site.facts.length > 0 && (
          <Panel title="Project facts">
            {site.facts.map((f) => (
              <Row key={f.label}>
                <Grow>
                  <Muted>{f.label}</Muted>
                  <Line>{f.value}</Line>
                </Grow>
                <Hint text={`${PROVENANCE_LABEL[f.provenance] ?? f.provenance}${f.source ? `. Source: ${f.source}` : ""}`} />
              </Row>
            ))}
            <Muted>
              Working for {party(site.principal)}. Every number carries its source; assumptions are listed in docs/PRACTITIONER-QUESTIONS.md.
            </Muted>
          </Panel>
        )}
      </Accordion>
    </div>
  );
}

function Differential({ chain, plan }: { chain: ChainView; plan: PlanView | null }) {
  const [css, theme] = useStyletron();
  const target = chain.milestone.target_date;
  const d = plan?.differential;
  const t = theme.colors;
  const rows: { label: string; date: string | null; color: string; hatch?: boolean }[] = [
    { label: "Target", date: target, color: t.borderOpaque },
    { label: d ? "Unmitigated" : "Forecast now", date: d ? d.unmitigated : (chain.milestone.forecast_finish ?? null), color: t.contentNegative },
  ];
  if (d)
    rows.push(
      { label: "With what ran", date: d.now, color: t.contentAccent },
      { label: "If you approve the asks", date: d.if_approved, color: t.contentPositive },
      { label: "If they agree", date: d.if_they_agree, color: t.contentPositive, hatch: true },
    );
  const deltas = rows.map((r) => daysBetween(target, r.date));
  const max = Math.max(1, ...deltas);
  return (
    <div data-testid="differential" className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale300 })}>
      {rows.map((r, i) => (
        <div key={r.label} className={css({ display: "grid", gridTemplateColumns: "150px 1fr 120px", gap: theme.sizing.scale400, alignItems: "center" })}>
          <ParagraphSmall margin={0}>{r.label}</ParagraphSmall>
          <div className={css({ height: "8px", background: t.backgroundSecondary, borderRadius: "4px", overflow: "hidden" })}>
            <div
              className={css({
                height: "100%",
                width: `${Math.max(0, Math.round((100 * deltas[i]) / max))}%`,
                background: r.hatch ? `repeating-linear-gradient(45deg, ${r.color} 0 4px, transparent 4px 8px)` : r.color,
              })}
            />
          </div>
          <ParagraphSmall margin={0} className={css({ textAlign: "right" })}>
            {deltas[i] > 0 ? `+${deltas[i]} d` : deltas[i] < 0 ? `${-deltas[i]} d early` : "on time"} · {fmt(r.date)}
          </ParagraphSmall>
        </div>
      ))}
      <Muted>
        {d
          ? `Days past the target, computed by the scheduler. Our own actions recover ${d.recovered_now}; approving the asks ${d.recovered_if_approved}; ${d.recovered_if_they_agree} come back only if they agree. Days that depend on another party are never counted when the request is sent.`
          : "Play a message: the agent proposes a plan, the gateway decides what runs on its own, and the scheduler computes the days."}
      </Muted>
    </div>
  );
}
