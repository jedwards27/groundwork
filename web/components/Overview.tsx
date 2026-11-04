import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { LabelMedium } from "baseui/typography";
import { Skeleton } from "baseui/skeleton";
import { lazy, Suspense, type ReactNode } from "react";
import type { ChainView, SiteView } from "@/lib/types";
// The chart and its library load on their own, so home and the other tabs don't wait for them.
const Chain = lazy(() => import("./Chain").then((m) => ({ default: m.Chain })));
import { project } from "@/copy/project";
import { Calendar } from "./Calendar";
import { Muted, Section } from "./ui";

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

export function Overview({ chain, site }: { chain: ChainView; site: SiteView }) {
  const [css, theme] = useStyletron();
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale600 })}>
      <Section title={say.graph.title} hint={say.graph.hint} testId="graph">
        <Suspense fallback={<Skeleton rows={4} height="200px" width="100%" animation />}>
          <Chain key={chain.site} chain={chain} />
        </Suspense>
      </Section>
      <Accordion>
        <Panel title={<Titled title={say.calendar.title} about={say.calendar.about} />}>
          <Calendar chain={chain} site={site} />
        </Panel>
      </Accordion>
    </div>
  );
}
