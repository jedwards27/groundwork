import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { LabelMedium, ParagraphSmall } from "baseui/typography";
import { Skeleton } from "baseui/skeleton";
import { lazy, Suspense, type ReactNode } from "react";
import { daysBetween, fmt, PROVENANCE_LABEL } from "@/lib/format";
import type { ChainView, PlanView, SiteView } from "@/lib/types";
// The chart and its library load on their own, so home and the other tabs don't wait for them.
const Chain = lazy(() => import("./Chain").then((m) => ({ default: m.Chain })));
import { project } from "@/copy/project";
import { Calendar } from "./Calendar";
import { Grow, Hint, Line, Muted, Row, Section } from "./ui";

const say = project.overview;

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
      <Section title={say.graph.title} hint={say.graph.hint} testId="graph">
        <Suspense fallback={<Skeleton rows={4} height="200px" width="100%" animation />}>
          <Chain key={chain.site} chain={chain} />
        </Suspense>
      </Section>
      <Accordion>
        <Panel
          title={
            <Titled title={say.winBack.title} about={d ? say.winBack.about(d.recovered_if_they_agree) : say.winBack.aboutNoPlan} />
          }
        >
          <Differential chain={chain} plan={plan} />
        </Panel>
        <Panel title={<Titled title={say.calendar.title} about={say.calendar.about} />}>
          <Calendar chain={chain} site={site} />
        </Panel>
        {site.facts.length > 0 && (
          <Panel title={<Titled title={say.about.title} about={site.attrs.blurb || say.about.aboutFallback} />}>
            {site.facts.map((f) => (
              <Row key={f.label}>
                <Grow>
                  <Muted>{f.label}</Muted>
                  <Line>{f.value}</Line>
                </Grow>
                <Hint text={say.about.source(PROVENANCE_LABEL[f.provenance] ?? f.provenance, f.source)} />
              </Row>
            ))}
            <Muted>{say.about.workingFor(party(site.principal))}</Muted>
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
    { label: say.winBack.target, date: target, color: t.borderOpaque },
    { label: d ? say.winBack.ifNothing : say.winBack.forecastNow, date: d ? d.unmitigated : (chain.milestone.forecast_finish ?? null), color: t.contentNegative },
  ];
  if (d)
    rows.push(
      { label: say.winBack.withWhatRan, date: d.now, color: t.contentAccent },
      { label: say.winBack.ifApproved, date: d.if_approved, color: t.contentPositive },
      { label: say.winBack.ifTheyAgree, date: d.if_they_agree, color: t.contentPositive, hatch: true },
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
            {deltas[i] > 0 ? say.winBack.late(deltas[i]) : deltas[i] < 0 ? say.winBack.early(-deltas[i]) : say.winBack.onTime}, {fmt(r.date)}
          </ParagraphSmall>
        </div>
      ))}
      {d && d.recovered_if_they_agree === 0 && <Muted testId="recovery-none">{say.winBack.none}</Muted>}
      <Muted>{say.winBack.note}</Muted>
    </div>
  );
}
