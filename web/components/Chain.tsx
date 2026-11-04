import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ButtonGroup, MODE } from "baseui/button-group";
import { scaleTime } from "d3-scale";
import { timeMonth, timeWeek } from "d3-time";
import { useEffect, useMemo, useRef, useState } from "react";
import { fmt, parseDate } from "@/lib/format";
import type { ChainView, ItemView } from "@/lib/types";
import { project } from "@/copy/project";
import { Muted } from "./ui";

const say = project.overview.graph;

const W = 900;
const LEFT = 150;
const RIGHT = 14;
const TOP = 34;
const NODE_W = 168;
const NODE_H = 44;
const ROW = 52;
const DAY_PX = 3.2; // the whole project: about a year per 1,170 pixels, scrolled sideways
const LINE = 27; // characters per title line

type Range = "near" | "all";

// A step's title on up to two lines, broken between words; the full title is in the tooltip.
function wrap(title: string): [string, string] {
  if (title.length <= LINE) return [title, ""];
  const cut = title.lastIndexOf(" ", LINE);
  const first = cut > 8 ? title.slice(0, cut) : title.slice(0, LINE);
  const rest = title.slice(first.length).trim();
  return [first, rest.length > LINE ? rest.slice(0, LINE - 1) + "…" : rest];
}

type Placed = { item: ItemView; x: number; y: number; clipped: boolean };

type Palette = Record<
  "paper" | "paperSoft" | "accent" | "accentSoft" | "crit" | "panel" | "base" | "line" | "line2" | "fg" | "muted" | "dim" | "body" | "mono",
  string
>;

// The steps that decide the date stand out: blue, heavier, bold. The one the date waits on now is
// amber. Finished steps fade back; everything else is quiet.
function color(i: ItemView, gate: string | null, c: Palette): { stroke: string; fill: string; width: number; text: string; bold: boolean } {
  if (i.status === "cancelled") return { stroke: c.line2, fill: "transparent", width: 1, text: c.dim, bold: false };
  if (i.key === gate) return { stroke: c.paper, fill: c.paperSoft, width: 2.6, text: c.fg, bold: true };
  if (i.status === "done") return { stroke: c.line, fill: c.panel, width: 1, text: c.dim, bold: false };
  if (i.critical) return { stroke: c.accent, fill: c.accentSoft, width: 2.2, text: c.fg, bold: true };
  return { stroke: c.line2, fill: c.base, width: 1, text: c.muted, bold: false };
}

// The paper chain: what gates delivery, by who does the work, on a time axis.
export function Chain({ chain }: { chain: ChainView }) {
  const [css, theme] = useStyletron();
  const t = theme.colors;
  const c: Palette = {
    paper: t.contentWarning,
    paperSoft: t.backgroundWarningLight,
    accent: t.contentAccent,
    accentSoft: t.backgroundAccentLight,
    crit: t.contentNegative,
    panel: t.backgroundSecondary,
    base: t.backgroundPrimary,
    line: t.borderOpaque,
    line2: t.contentTertiary,
    fg: t.contentPrimary,
    muted: t.contentSecondary,
    dim: t.contentTertiary,
    body: theme.typography.LabelXSmall.fontFamily as string,
    mono: theme.typography.MonoLabelXSmall.fontFamily as string,
  };
  const closed = (i: ItemView) => i.status === "done" || i.status === "cancelled";
  // Steps that finished well before today drop out of the default view. When that's most of the
  // project, start on the whole project instead.
  const nearStart = useMemo(() => new Date(parseDate(chain.as_of)!.getTime() - 42 * 86_400_000), [chain.as_of]);
  const hidden = chain.items.filter((i) => closed(i) && parseDate(i.early_finish)! < nearStart).length;
  const [range, setRange] = useState<Range>(hidden > chain.items.length - hidden ? "all" : "near");
  const scroller = useRef<HTMLDivElement>(null);

  const layout = useMemo(() => {
    const asOf = parseDate(chain.as_of)!;
    const target = parseDate(chain.milestone.target_date)!;
    const forecast = parseDate(chain.milestone.forecast_finish ?? chain.milestone.target_date)!;
    const near = chain.items.filter((i) => i.on_target_path || !closed(i)).map((i) => parseDate(i.early_finish)!);
    const horizon = new Date(Math.max(target.getTime(), forecast.getTime()) + 35 * 86_400_000);
    const all = range === "all";
    const earliest = Math.min(...chain.items.map((i) => parseDate(i.planned_start ?? i.early_finish)!.getTime()), asOf.getTime());
    const latest = Math.max(...chain.items.map((i) => parseDate(i.early_finish)!.getTime()), horizon.getTime());
    const start = all ? new Date(earliest - 14 * 86_400_000) : nearStart;
    const t1 = all ? new Date(latest + 14 * 86_400_000) : new Date(Math.min(horizon.getTime(), Math.max(...near.map((d) => d.getTime()), horizon.getTime())));
    const width = all ? Math.max(W, Math.round(LEFT + RIGHT + NODE_W + ((t1.getTime() - start.getTime()) / 86_400_000) * DAY_PX)) : W;
    const x = scaleTime().domain([start, t1]).range([LEFT, width - RIGHT]);
    const placed: Placed[] = [];
    let y = TOP;
    const lanes = chain.lanes.map((lane) => {
      const items = chain.items
        .filter((i) => i.lane === lane.key && (all || !(closed(i) && parseDate(i.early_finish)! < start)))
        .sort((a, b) => (a.early_finish < b.early_finish ? -1 : 1));
      const rowsEnd: number[] = [];
      const laneTop = y;
      for (const item of items) {
        const end = parseDate(item.early_finish)!;
        let right = x(end);
        let clipped = false;
        if (end > t1) { right = width - RIGHT; clipped = true; }
        const left = Math.max(LEFT, right - NODE_W);
        let row = rowsEnd.findIndex((r) => r < left - 4);
        if (row === -1) { row = rowsEnd.length; rowsEnd.push(0); }
        rowsEnd[row] = left + NODE_W;
        placed.push({ item, x: left, y: laneTop + 6 + row * ROW, clipped });
      }
      const h = rowsEnd.length ? rowsEnd.length * ROW + 10 : 0;
      y += h;
      return { ...lane, top: laneTop, h, items: items.length };
    });
    return { x, placed, lanes: lanes.filter((l) => l.items > 0), H: y + 40, asOf, target, forecast, start, t1, width };
  }, [chain, range, nearStart]);

  const { x, placed, lanes, H, asOf, target, forecast, start, t1, width } = layout;
  // On the whole project, open scrolled to a little before today.
  useEffect(() => {
    if (range === "all" && scroller.current) scroller.current.scrollLeft = Math.max(0, x(asOf) - 320);
  }, [range, x, asOf]);
  const pos = new Map(placed.map((p) => [p.item.key, p]));
  const critLinks = new Set(chain.critical_path.slice(1).map((k, n) => `${chain.critical_path[n]}>${k}`));
  const months = timeMonth.range(timeMonth.ceil(start), t1);
  const weeks = timeWeek.range(start, t1);
  const late = (chain.milestone.delta_days ?? 0) > 0;
  return (
    <div>
      <div className={css({ display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.sizing.scale400, marginBottom: theme.sizing.scale400 })}>
        <ButtonGroup mode={MODE.radio} size={SIZE.compact} selected={range === "near" ? 0 : 1} onClick={(_, i) => setRange(i === 0 ? "near" : "all")}>
          <Button data-testid="range-near">{say.near}</Button>
          <Button data-testid="range-all">{say.all}</Button>
        </ButtonGroup>
        {range === "near" && hidden > 0 && (
          <span className={css({ display: "inline-flex", alignItems: "center", gap: theme.sizing.scale200 })} data-testid="hidden-steps">
            <Muted>{say.hidden(hidden, fmt(nearStart.toISOString().slice(0, 10)))}</Muted>
            <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => setRange("all")}>
              {say.showAll}
            </Button>
          </span>
        )}
      </div>
      <div className={css({ position: "relative" })}>
      {range === "all" && (
        // On the scrolled view the row labels stay put, so you can tell whose row is whose.
        <svg width={LEFT - 8} height={H} aria-hidden className={css({ position: "absolute", left: 0, top: 0, pointerEvents: "none", zIndex: 1 })}>
          {lanes.map((lane) => (
            <g key={lane.key}>
              <rect x={0} y={lane.top} width={LEFT - 8} height={lane.h} fill={c.base} opacity={0.92} />
              <text x={8} y={lane.top + 20} fill={c.muted} fontSize={11} fontFamily={c.body}>
                {lane.label.length > 22 ? lane.label.slice(0, 21) + "…" : lane.label}
              </text>
            </g>
          ))}
        </svg>
      )}
      <div ref={scroller} className={css({ overflowX: "auto" })}>
        <svg
          viewBox={`0 0 ${width} ${H}`}
          role="img"
          aria-label={say.aria(placed.length)}
          className={css(range === "all" ? { width: `${width}px`, display: "block" } : { width: "100%", minWidth: "640px", display: "block" })}
        >
          <defs>
            <marker id="gw-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={c.accent} />
            </marker>
          </defs>
          {lanes.map((lane, n) => (
            <g key={lane.key}>
              <rect x={0} y={lane.top} width={width} height={lane.h} fill={n % 2 ? "rgba(127,140,170,0.05)" : "transparent"} />
              <text x={8} y={lane.top + 20} fill={c.muted} fontSize={11} fontFamily={c.body}>
                {lane.label.length > 24 ? lane.label.slice(0, 23) + "…" : lane.label}
              </text>
            </g>
          ))}
          {weeks.map((w) => (
            <line key={+w} x1={x(w)} x2={x(w)} y1={TOP - 4} y2={H - 32} stroke={c.line} strokeOpacity={0.35} />
          ))}
          {months.map((m) => (
            <g key={+m}>
              <line x1={x(m)} x2={x(m)} y1={TOP - 8} y2={H - 32} stroke={c.line} />
              <text x={x(m) + 4} y={TOP - 12} fill={c.dim} fontSize={10} fontFamily={c.mono}>
                {m.toLocaleDateString("en-US", { month: "short", year: m.getMonth() === 0 ? "2-digit" : undefined })}
              </text>
            </g>
          ))}
          <g fill="none" strokeWidth={1.2}>
            {/* Critical links last, so they draw over the rest. */}
            {[...chain.links.filter((l) => !critLinks.has(`${l.pred}>${l.succ}`)), ...chain.links.filter((l) => critLinks.has(`${l.pred}>${l.succ}`))].map((l) => {
              const a = pos.get(l.pred);
              const b = pos.get(l.succ);
              if (!a || !b) return null;
              const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2;
              const k = Math.max(36, Math.abs(x2 - x1) / 2);
              const crit = critLinks.has(`${l.pred}>${l.succ}`);
              return (
                <path key={`${l.pred}-${l.succ}`} d={`M${x1} ${y1} C${x1 + k} ${y1} ${x2 - k} ${y2} ${x2} ${y2}`}
                  stroke={crit ? c.accent : c.line2} strokeOpacity={crit ? 0.95 : 0.35} strokeWidth={crit ? 2.4 : 1}
                  strokeDasharray={a.item.status === "done" ? "3 3" : undefined} markerEnd={crit ? "url(#gw-arrow)" : undefined} />
              );
            })}
          </g>
          {[
            { d: asOf, label: say.today, c: c.fg, dash: "2 3" },
            { d: target, label: say.target(fmt(chain.milestone.target_date)), c: c.dim, dash: "5 4" },
            ...(+forecast !== +target ? [{ d: forecast, label: say.forecast(fmt(chain.milestone.forecast_finish)), c: late ? c.crit : c.accent, dash: "5 4" }] : []),
          ].map((m, n) => (
            <g key={m.label}>
              <line x1={x(m.d)} x2={x(m.d)} y1={TOP - 4} y2={n === 2 ? H - 18 : H - 32} stroke={m.c} strokeDasharray={m.dash} strokeWidth={1.4} opacity={0.85} />
              <text x={x(m.d)} y={n === 2 ? H - 6 : H - 20} fill={m.c} fontSize={10} fontFamily={c.mono}
                textAnchor={x(m.d) > width - 110 ? "end" : "start"} dx={x(m.d) > width - 110 ? -4 : 4}>
                {m.label}
              </text>
            </g>
          ))}
          {placed.map(({ item, x: nx, y: ny, clipped }) => {
            const box = color(item, chain.gate, c);
            const [l1, l2] = wrap(item.title);
            const cancelled = item.status === "cancelled";
            const stale = chain.stale?.[item.key];
            return (
              <g key={item.key} transform={`translate(${nx} ${ny})`} data-key={item.key}>
                <title>
                  {say.tooltip(item.title, item.status.replace("_", " "), fmt(item.planned_finish, true), fmt(item.early_finish, true)) +
                    (item.total_float !== null && item.total_float !== undefined ? say.float(item.total_float) : "") +
                    (item.notes ? `\n${item.notes}` : "")}
                </title>
                <rect width={NODE_W} height={NODE_H} rx={6} fill={box.fill} stroke={box.stroke} strokeWidth={box.width} strokeDasharray={cancelled ? "4 3" : undefined} />
                <text x={8} y={13} fill={box.text} fontSize={10.5} fontWeight={box.bold ? 700 : 500} fontFamily={c.body} textDecoration={cancelled ? "line-through" : undefined}>
                  {l1}
                  {l2 && <tspan x={8} dy={12}>{l2}</tspan>}
                </text>
                <text x={8} y={NODE_H - 6} fill={!cancelled && item.finish_shift_days > 0 ? c.crit : c.dim} fontSize={9} fontFamily={c.mono}>
                  {cancelled ? say.cancelled : (
                    <>
                      {item.status === "done" ? say.done : ""}
                      {item.estimated ? say.estimated : ""}
                      {fmt(item.early_finish)}
                      {item.finish_shift_days > 0 ? ` (+${item.finish_shift_days}d)` : ""}
                      {stale ? say.noWord : ""}
                      {clipped ? " →" : ""}
                    </>
                  )}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      </div>
      <Muted>{say.legend}</Muted>
    </div>
  );
}
