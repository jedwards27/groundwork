// A month at a time: when each step is due, the holidays (red when one costs the project a day),
// today, the target and the forecast. Click a day for what's due on it.
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ChevronLeft, ChevronRight } from "baseui/icon";
import { LabelMedium, ParagraphSmall } from "baseui/typography";
import { useMemo, useState } from "react";
import { fmt, parseDate } from "@/lib/format";
import type { ChainView, ItemView, SiteView } from "@/lib/types";
import { project } from "@/copy/project";
import { Chip, Muted } from "./ui";

const say = project.overview.calendar;
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function Calendar({ chain, site }: { chain: ChainView; site: SiteView }) {
  const [css, theme] = useStyletron();
  const t = theme.colors;
  const asOf = parseDate(chain.as_of)!;
  const [month, setMonth] = useState(() => new Date(asOf.getFullYear(), asOf.getMonth(), 1));
  const [day, setDay] = useState<string | null>(null);

  const { due, holidays, costly } = useMemo(() => {
    const due = new Map<string, ItemView[]>();
    for (const i of chain.items) {
      if (i.status === "cancelled") continue;
      const d = i.status === "done" ? (i.actual_finish ?? i.early_finish) : i.early_finish;
      due.set(d, [...(due.get(d) ?? []), i]);
    }
    const costly = new Map<string, string>();
    for (const l of chain.calendar_losses) for (const h of l.holidays) costly.set(h, l.sentence);
    return { due, holidays: new Set(site.holidays), costly };
  }, [chain, site]);

  const marks = new Map<string, string[]>();
  const mark = (d: string | null | undefined, label: string) => d && marks.set(d, [...(marks.get(d) ?? []), label]);
  mark(chain.as_of, say.today);
  mark(chain.milestone.target_date, say.target);
  if (chain.milestone.forecast_finish !== chain.milestone.target_date) mark(chain.milestone.forecast_finish, say.forecast);

  // Six weeks from the Sunday on or before the 1st.
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = new Date(first);
  start.setDate(1 - first.getDay());
  const days = Array.from({ length: 42 }, (_, n) => {
    const d = new Date(start);
    d.setDate(start.getDate() + n);
    return d;
  });
  const shift = (n: number) => {
    setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1));
    setDay(null);
  };
  const picked = day ? (due.get(day) ?? []) : [];

  return (
    <div data-testid="calendar" className={css({ display: "grid", gap: theme.sizing.scale400 })}>
      <div className={css({ display: "flex", alignItems: "center", gap: theme.sizing.scale300 })}>
        <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => shift(-1)} aria-label={say.previous}>
          <ChevronLeft size={20} />
        </Button>
        <LabelMedium className={css({ minWidth: "140px", textAlign: "center" })} data-testid="calendar-month">
          {month.toLocaleDateString("en-US", { month: "long", year: "numeric" })}
        </LabelMedium>
        <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => shift(1)} aria-label={say.next}>
          <ChevronRight size={20} />
        </Button>
        <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => { setMonth(new Date(asOf.getFullYear(), asOf.getMonth(), 1)); setDay(null); }}>
          {say.today}
        </Button>
      </div>
      <div className={css({ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", border: `1px solid ${t.borderOpaque}`, borderRadius: theme.borders.radius300, overflow: "hidden" })}>
        {say.weekdays.map((w) => (
          <div key={w} className={css({ ...theme.typography.LabelXSmall, color: t.contentTertiary, padding: theme.sizing.scale200, borderBottom: `1px solid ${t.borderOpaque}` })}>
            {w}
          </div>
        ))}
        {days.map((d, n) => {
          const key = iso(d);
          const inMonth = d.getMonth() === month.getMonth();
          const items = due.get(key) ?? [];
          const holiday = holidays.has(key);
          const cost = costly.get(key);
          const labels = marks.get(key) ?? [];
          const selected = day === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setDay(selected ? null : key)}
              data-testid={`day-${key}`}
              title={cost ?? (holiday ? say.holiday : undefined)}
              className={css({
                all: "unset",
                boxSizing: "border-box",
                cursor: "pointer",
                minHeight: "72px",
                padding: theme.sizing.scale200,
                display: "flex",
                flexDirection: "column",
                gap: "2px",
                borderTop: n >= 7 ? `1px solid ${t.borderOpaque}` : undefined,
                borderLeft: n % 7 ? `1px solid ${t.borderOpaque}` : undefined,
                background: selected ? t.backgroundAccentLight : cost ? t.backgroundNegativeLight : holiday ? t.backgroundSecondary : "transparent",
                opacity: inMonth ? 1 : 0.45,
                ":focus-visible": { outline: `2px solid ${t.borderSelected}`, outlineOffset: "-2px" },
              })}
            >
              <span className={css({ ...theme.typography.LabelXSmall, color: labels.includes(say.today) ? t.contentAccent : t.contentSecondary, fontWeight: labels.length ? 700 : 400 })}>
                {d.getDate()}
              </span>
              {labels.map((l) => (
                <span key={l} className={css({ ...theme.typography.ParagraphXSmall, color: l === say.forecast ? t.contentNegative : t.contentAccent })}>
                  {l}
                </span>
              ))}
              {holiday && (
                <span className={css({ ...theme.typography.ParagraphXSmall, color: cost ? t.contentNegative : t.contentTertiary })}>{cost ? say.costsADay : say.holiday}</span>
              )}
              {items.slice(0, 2).map((i) => (
                <span
                  key={i.key}
                  className={css({
                    ...theme.typography.ParagraphXSmall,
                    color: i.status === "done" ? t.contentTertiary : i.key === chain.gate ? t.contentWarning : i.critical ? t.contentAccent : t.contentPrimary,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  })}
                >
                  {i.title}
                </span>
              ))}
              {items.length > 2 && <span className={css({ ...theme.typography.ParagraphXSmall, color: t.contentTertiary })}>{say.more(items.length - 2)}</span>}
            </button>
          );
        })}
      </div>
      {day && (
        <div data-testid="calendar-day" className={css({ display: "grid", gap: theme.sizing.scale200 })}>
          <LabelMedium>{fmt(day, true)}</LabelMedium>
          {costly.get(day) && <ParagraphSmall margin={0} color={t.contentNegative}>{costly.get(day)}</ParagraphSmall>}
          {picked.length === 0 && <Muted>{say.nothingDue}</Muted>}
          {picked.map((i) => (
            <div key={i.key} className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center" })}>
              <ParagraphSmall margin={0}>{i.title}</ParagraphSmall>
              {i.key === chain.gate && <Chip kind="yellow">{say.setsTheDate}</Chip>}
              {i.status === "done" && <Chip>{say.done}</Chip>}
            </div>
          ))}
        </div>
      )}
      <Muted>{say.legend}</Muted>
    </div>
  );
}
