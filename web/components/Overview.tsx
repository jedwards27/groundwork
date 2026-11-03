import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { LabelMedium, ParagraphSmall } from "baseui/typography";
import type { ReactNode } from "react";
import { daysBetween, fmt, PROVENANCE_LABEL } from "@/lib/format";
import type { ChainView, PlanView, SiteView } from "@/lib/types";
import { Chain } from "./Chain";
import { Grow, Hint, Line, Muted, Row, Section } from "./ui";

// A section title with one line saying what it is, so a closed accordion still explains itself.
function Titled({ title, about }: { title: string; about: ReactNode }) {
  const [css] = useStyletron();
  return (
    <span className={css({ display: "grid" })}>
      <LabelMedium>{title}</LabelMedium>
      <Muted>{about}</Muted>
    </span>
  );
}

export function Overview({ chain, site, plan }: { chain: ChainView; site: SiteView; plan: PlanView | null }) {
  const [css, theme] = useStyletron();
  const d = plan?.differential;
  const party = (k: string) => site.parties.find((p) => p.key === k)?.name ?? k;
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale600 })}>
      <Section title="What depends on what" hint="Every step in the project and what it waits on, laid out on the calendar." testId="graph">
        <Chain chain={chain} />
      </Section>
      <Accordion>
        <Panel
          title={
            <Titled
              title="Days the plan can win back"
              about={d ? `${d.recovered_if_they_agree} days back if you approve and they agree` : "After a message comes in and Groundwork plans"}
            />
          }
        >
          <Differential chain={chain} plan={plan} />
        </Panel>
        {chain.calendar_losses.length > 0 && (
          <Panel title={<Titled title="Holidays that cost days" about="Days off that fall on the steps that decide the date" />}>
            {chain.calendar_losses.map((l, n) => (
              <ParagraphSmall key={n} marginTop={0}>
                {l.sentence}
              </ParagraphSmall>
            ))}
          </Panel>
        )}
        {site.facts.length > 0 && (
          <Panel title={<Titled title="About this project" about={site.attrs.blurb || "Facts, each with its source"} />}>
            {site.facts.map((f) => (
              <Row key={f.label}>
                <Grow>
                  <Muted>{f.label}</Muted>
                  <Line>{f.value}</Line>
                </Grow>
                <Hint text={`${PROVENANCE_LABEL[f.provenance] ?? f.provenance}${f.source ? `. Source: ${f.source}` : ""}`} />
              </Row>
            ))}
            <Muted>Working for {party(site.principal)}. Every number carries its source.</Muted>
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
    { label: d ? "If nothing is done" : "Forecast now", date: d ? d.unmitigated : (chain.milestone.forecast_finish ?? null), color: t.contentNegative },
  ];
  if (d)
    rows.push(
      { label: "With what already ran", date: d.now, color: t.contentAccent },
      { label: "If you approve the asks", date: d.if_approved, color: t.contentPositive },
      { label: "If they agree too", date: d.if_they_agree, color: t.contentPositive, hatch: true },
    );
  const deltas = rows.map((r) => daysBetween(target, r.date));
  const max = Math.max(1, ...deltas);
  return (
    <div data-testid="differential" className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale300 })}>
      {rows.map((r, i) => (
        <div key={r.label} className={css({ display: "grid", gridTemplateColumns: "160px 1fr 120px", gap: theme.sizing.scale400, alignItems: "center" })}>
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
        Days past the target, worked out from the schedule. Days that depend on someone else agreeing are counted only once they do.
      </Muted>
    </div>
  );
}
