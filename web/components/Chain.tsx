import { useStyletron } from "baseui";
import { scaleTime } from "d3-scale";
import { timeMonth, timeWeek } from "d3-time";
import { useMemo } from "react";
import { fmt, parseDate } from "@/lib/format";
import type { ChainView, ItemView } from "@/lib/types";
import { Muted } from "./ui";

const W = 860;
const LEFT = 150;
const RIGHT = 14;
const TOP = 34;
const NODE_W = 116;
const NODE_H = 26;
const ROW = 32;

type Placed = { item: ItemView; x: number; y: number; clipped: boolean };

type Palette = Record<"paper" | "paperSoft" | "good" | "goodSoft" | "crit" | "critSoft" | "panel" | "line" | "line2" | "fg" | "muted" | "dim" | "body" | "mono", string>;

function color(i: ItemView, gate: string | null, c: Palette): { stroke: string; fill: string; width: number } {
  if (i.key === gate) return { stroke: c.paper, fill: c.paperSoft, width: 2.4 };
  if (i.status === "done") return { stroke: c.good, fill: c.goodSoft, width: 1.4 };
  if (i.finish_shift_days > 0) return { stroke: c.crit, fill: c.critSoft, width: i.critical ? 2.4 : 1.6 };
  if (i.critical) return { stroke: c.crit, fill: c.panel, width: 2 };
  if (i.near_critical) return { stroke: c.paper, fill: c.panel, width: 1.4 };
  return { stroke: c.line2, fill: c.panel, width: 1.2 };
}

// The paper chain: what gates delivery, by who does the work, on a time axis.
export function Chain({ chain }: { chain: ChainView }) {
  const [css, theme] = useStyletron();
  const t = theme.colors;
  const c: Palette = {
    paper: t.contentWarning,
    paperSoft: t.backgroundWarningLight,
    good: t.contentPositive,
    goodSoft: t.backgroundPositiveLight,
    crit: t.contentNegative,
    critSoft: t.backgroundNegativeLight,
    panel: t.backgroundSecondary,
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
        .filter((i) => i.lane === lane.key)
        .sort((a, b) => (a.early_finish < b.early_finish ? -1 : 1));
      const rowsEnd: number[] = [];
      const laneTop = y;
      for (const item of items) {
        const end = parseDate(item.early_finish)!;
        let right = x(end);
        let clipped = false;
        if (end > t1) { right = W - RIGHT; clipped = true; }
        if (end < start) right = LEFT + NODE_W;
        const left = Math.max(LEFT, right - NODE_W);
        let row = rowsEnd.findIndex((r) => r < left - 4);
        if (row === -1) { row = rowsEnd.length; rowsEnd.push(0); }
        rowsEnd[row] = left + NODE_W;
        placed.push({ item, x: left, y: laneTop + 6 + row * ROW, clipped });
      }
      const h = Math.max(1, rowsEnd.length) * ROW + 10;
      y += h;
      return { ...lane, top: laneTop, h };
    });
    return { x, placed, lanes, H: y + 26, asOf, target, forecast, start, t1 };
  }, [chain]);

  const { x, placed, lanes, H, asOf, target, forecast, start, t1 } = layout;
  const pos = new Map(placed.map((p) => [p.item.key, p]));
  const months = timeMonth.range(timeMonth.ceil(start), t1);
  const weeks = timeWeek.range(start, t1);
  const late = (chain.milestone.delta_days ?? 0) > 0;
  return (
    <div>
      <div className={css({ overflowX: "auto" })}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Dependency chain of ${chain.items.length} items`} className={css({ width: "100%", minWidth: "640px", display: "block" })}>
          {lanes.map((lane, n) => (
            <g key={lane.key}>
              <rect x={0} y={lane.top} width={W} height={lane.h} fill={n % 2 ? "rgba(127,140,170,0.05)" : "transparent"} />
              <text x={8} y={lane.top + 20} fill={c.muted} fontSize={11} fontFamily={c.body}>
                {lane.label.length > 24 ? lane.label.slice(0, 23) + "…" : lane.label}
              </text>
            </g>
          ))}
          {weeks.map((w) => (
            <line key={+w} x1={x(w)} x2={x(w)} y1={TOP - 4} y2={H - 22} stroke={c.line} strokeOpacity={0.35} />
          ))}
          {months.map((m) => (
            <g key={+m}>
              <line x1={x(m)} x2={x(m)} y1={TOP - 8} y2={H - 22} stroke={c.line} />
              <text x={x(m) + 4} y={TOP - 12} fill={c.dim} fontSize={10} fontFamily={c.mono}>
                {m.toLocaleDateString("en-US", { month: "short", year: m.getMonth() === 0 ? "2-digit" : undefined })}
              </text>
            </g>
          ))}
          <g fill="none" strokeWidth={1.2}>
            {chain.links.map((l) => {
              const a = pos.get(l.pred);
              const b = pos.get(l.succ);
              if (!a || !b) return null;
              const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2;
              const mx = (x1 + x2) / 2;
              const crit = a.item.critical && b.item.critical;
              return (
                <path key={`${l.pred}-${l.succ}`} d={`M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`}
                  stroke={crit ? c.crit : c.line2} strokeOpacity={crit ? 0.9 : 0.6}
                  strokeDasharray={a.item.status === "done" ? "3 3" : undefined} />
              );
            })}
          </g>
          {[
            { d: asOf, label: "as of", c: c.fg, dash: "2 3" },
            { d: target, label: `target ${fmt(chain.milestone.target_date)}`, c: c.paper, dash: "5 4" },
            ...(+forecast !== +target ? [{ d: forecast, label: `forecast ${fmt(chain.milestone.forecast_finish)}`, c: late ? c.crit : c.good, dash: "5 4" }] : []),
          ].map((m, n) => (
            <g key={m.label}>
              <line x1={x(m.d)} x2={x(m.d)} y1={TOP - 4} y2={H - 22} stroke={m.c} strokeDasharray={m.dash} strokeWidth={1.4} opacity={0.85} />
              <text x={x(m.d) + 4} y={H - 8 - (n === 2 ? 0 : 0)} fill={m.c} fontSize={10} fontFamily={c.mono}
                textAnchor={n === 2 && x(m.d) > W - 120 ? "end" : "start"} dx={n === 2 && x(m.d) > W - 120 ? -8 : 0}>
                {m.label}
              </text>
            </g>
          ))}
          {placed.map(({ item, x: nx, y: ny, clipped }) => {
            const box = color(item, chain.gate, c);
            const label = item.title.length > 21 ? item.title.slice(0, 20) + "…" : item.title;
            return (
              <g key={item.key} transform={`translate(${nx} ${ny})`} data-key={item.key}>
                <title>
                  {`${item.title}\n${item.status.replace("_", " ")} · planned ${fmt(item.planned_finish, true)} · forecast ${fmt(item.early_finish, true)}` +
                    (item.total_float !== null && item.total_float !== undefined ? ` · float ${item.total_float} bd` : "") +
                    (item.notes ? `\n${item.notes}` : "")}
                </title>
                <rect width={NODE_W} height={NODE_H} rx={5} fill={box.fill} stroke={box.stroke} strokeWidth={box.width} />
                <text x={7} y={11} fill={c.fg} fontSize={10} fontWeight={600} fontFamily={c.body}>{label}</text>
                <text x={7} y={21} fill={item.finish_shift_days > 0 ? c.crit : c.muted} fontSize={9} fontFamily={c.mono}>
                  {item.status === "done" ? "done · " : ""}
                  {fmt(item.early_finish)}
                  {item.finish_shift_days > 0 ? ` (+${item.finish_shift_days}d)` : ""}
                  {clipped ? " →" : ""}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <Muted>
        Green: done. Amber: gating or nearly critical. Red: on the critical path or slipped. Dashed links leave finished items. Hover a box
        for its dates and float.
      </Muted>
    </div>
  );
}
