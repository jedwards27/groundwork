import { useStyletron } from "baseui";
import { scaleTime } from "d3-scale";
import { timeMonth, timeWeek } from "d3-time";
import { useMemo } from "react";
import { fmt, parseDate } from "@/lib/format";
import type { ChainView, ItemView } from "@/lib/types";
import { project } from "@/copy/project";
import { Muted } from "./ui";

const say = project.overview.graph;

const W = 900;
const LEFT = 150;
const RIGHT = 14;
const TOP = 34;
const NODE_W = 150;
const NODE_H = 32;
const ROW = 40;

type Placed = { item: ItemView; x: number; y: number; clipped: boolean };

type Palette = Record<
  "paper" | "paperSoft" | "accent" | "accentSoft" | "crit" | "panel" | "base" | "line" | "line2" | "fg" | "muted" | "dim" | "body" | "mono",
  string
>;

// The steps that decide the date stand out: blue, heavier, bold. The one the date waits on now is
// amber. Finished steps fade back; everything else is quiet.
function color(i: ItemView, gate: string | null, c: Palette): { stroke: string; fill: string; width: number; text: string; bold: boolean } {
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
  const layout = useMemo(() => {
    const asOf = parseDate(chain.as_of)!;
    const target = parseDate(chain.milestone.target_date)!;
    const forecast = parseDate(chain.milestone.forecast_finish ?? chain.milestone.target_date)!;
    const near = chain.items.filter((i) => i.on_target_path || i.status !== "done").map((i) => parseDate(i.early_finish)!);
    const horizon = new Date(Math.max(target.getTime(), forecast.getTime()) + 35 * 86_400_000);
    const start = new Date(asOf.getTime() - 42 * 86_400_000);
    const t1 = new Date(Math.min(horizon.getTime(), Math.max(...near.map((d) => d.getTime()), horizon.getTime())));
    const x = scaleTime().domain([start, t1]).range([LEFT, W - RIGHT]);
    const placed: Placed[] = [];
    let y = TOP;
    const lanes = chain.lanes.map((lane) => {
      const items = chain.items
        .filter((i) => i.lane === lane.key && !(i.status === "done" && parseDate(i.early_finish)! < start))
        .sort((a, b) => (a.early_finish < b.early_finish ? -1 : 1));
      const rowsEnd: number[] = [];
      const laneTop = y;
      for (const item of items) {
        const end = parseDate(item.early_finish)!;
        let right = x(end);
        let clipped = false;
        if (end > t1) { right = W - RIGHT; clipped = true; }
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
    return { x, placed, lanes: lanes.filter((l) => l.items > 0), H: y + 40, asOf, target, forecast, start, t1 };
  }, [chain]);

  const { x, placed, lanes, H, asOf, target, forecast, start, t1 } = layout;
  const pos = new Map(placed.map((p) => [p.item.key, p]));
  const critLinks = new Set(chain.critical_path.slice(1).map((k, n) => `${chain.critical_path[n]}>${k}`));
  const months = timeMonth.range(timeMonth.ceil(start), t1);
  const weeks = timeWeek.range(start, t1);
  const late = (chain.milestone.delta_days ?? 0) > 0;
  return (
    <div>
      <div className={css({ overflowX: "auto" })}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={say.aria(chain.items.length)} className={css({ width: "100%", minWidth: "640px", display: "block" })}>
          <defs>
            <marker id="gw-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={c.accent} />
            </marker>
          </defs>
          {lanes.map((lane, n) => (
            <g key={lane.key}>
              <rect x={0} y={lane.top} width={W} height={lane.h} fill={n % 2 ? "rgba(127,140,170,0.05)" : "transparent"} />
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
                textAnchor={x(m.d) > W - 110 ? "end" : "start"} dx={x(m.d) > W - 110 ? -4 : 4}>
                {m.label}
              </text>
            </g>
          ))}
          {placed.map(({ item, x: nx, y: ny, clipped }) => {
            const box = color(item, chain.gate, c);
            const label = item.title.length > 26 ? item.title.slice(0, 25) + "…" : item.title;
            return (
              <g key={item.key} transform={`translate(${nx} ${ny})`} data-key={item.key}>
                <title>
                  {say.tooltip(item.title, item.status.replace("_", " "), fmt(item.planned_finish, true), fmt(item.early_finish, true)) +
                    (item.total_float !== null && item.total_float !== undefined ? say.float(item.total_float) : "") +
                    (item.notes ? `\n${item.notes}` : "")}
                </title>
                <rect width={NODE_W} height={NODE_H} rx={6} fill={box.fill} stroke={box.stroke} strokeWidth={box.width} />
                <text x={8} y={13} fill={box.text} fontSize={10.5} fontWeight={box.bold ? 700 : 500} fontFamily={c.body}>{label}</text>
                <text x={8} y={25} fill={item.finish_shift_days > 0 ? c.crit : c.dim} fontSize={9} fontFamily={c.mono}>
                  {item.status === "done" ? say.done : ""}
                  {fmt(item.early_finish)}
                  {item.finish_shift_days > 0 ? ` (+${item.finish_shift_days}d)` : ""}
                  {clipped ? " →" : ""}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <Muted>{say.legend}</Muted>
    </div>
  );
}
