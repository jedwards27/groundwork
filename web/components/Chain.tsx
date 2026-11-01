"use client";
import { scaleTime } from "d3-scale";
import { timeMonth, timeWeek } from "d3-time";
import { useMemo } from "react";
import { fmt, parseDate } from "@/lib/format";
import type { ChainView, ItemView } from "@/lib/types";

const W = 860;
const LEFT = 150;
const RIGHT = 14;
const TOP = 34;
const NODE_W = 116;
const NODE_H = 26;
const ROW = 32;

type Placed = { item: ItemView; x: number; y: number; clipped: boolean };

function color(i: ItemView, gate: string | null): { stroke: string; fill: string; width: number } {
  if (i.key === gate) return { stroke: "var(--paper)", fill: "var(--paper-soft)", width: 2.4 };
  if (i.status === "done") return { stroke: "var(--good)", fill: "var(--good-soft)", width: 1.4 };
  if (i.finish_shift_days > 0) return { stroke: "var(--crit)", fill: "var(--crit-soft)", width: i.critical ? 2.4 : 1.6 };
  if (i.critical) return { stroke: "var(--crit)", fill: "var(--panel-2)", width: 2 };
  if (i.near_critical) return { stroke: "var(--paper)", fill: "var(--panel-2)", width: 1.4 };
  return { stroke: "var(--line-2)", fill: "var(--panel-2)", width: 1.2 };
}

export function Chain({ chain }: { chain: ChainView }) {
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
    <section className="panel" aria-label="The paper chain">
      <h2>
        The paper chain <span className="hint">what gates delivery, by who does the work, on a time axis</span>
      </h2>
      <div className="chainwrap">
        <svg className="chain" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Dependency chain of ${chain.items.length} items`}>
          {lanes.map((lane, n) => (
            <g key={lane.key}>
              <rect x={0} y={lane.top} width={W} height={lane.h} fill={n % 2 ? "rgba(127,140,170,0.05)" : "transparent"} />
              <text x={8} y={lane.top + 20} fill="var(--muted)" fontSize={11} fontFamily="var(--body)">
                {lane.label.length > 24 ? lane.label.slice(0, 23) + "…" : lane.label}
              </text>
            </g>
          ))}
          {weeks.map((w) => (
            <line key={+w} x1={x(w)} x2={x(w)} y1={TOP - 4} y2={H - 22} stroke="var(--line)" strokeOpacity={0.35} />
          ))}
          {months.map((m) => (
            <g key={+m}>
              <line x1={x(m)} x2={x(m)} y1={TOP - 8} y2={H - 22} stroke="var(--line)" />
              <text x={x(m) + 4} y={TOP - 12} fill="var(--dim)" fontSize={10} fontFamily="var(--mono)">
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
                  stroke={crit ? "var(--crit)" : "var(--line-2)"} strokeOpacity={crit ? 0.9 : 0.6}
                  strokeDasharray={a.item.status === "done" ? "3 3" : undefined} />
              );
            })}
          </g>
          {[
            { d: asOf, label: "as of", c: "var(--fg)", dash: "2 3" },
            { d: target, label: `target ${fmt(chain.milestone.target_date)}`, c: "var(--paper)", dash: "5 4" },
            ...(+forecast !== +target ? [{ d: forecast, label: `forecast ${fmt(chain.milestone.forecast_finish)}`, c: late ? "var(--crit)" : "var(--good)", dash: "5 4" }] : []),
          ].map((m, n) => (
            <g key={m.label}>
              <line x1={x(m.d)} x2={x(m.d)} y1={TOP - 4} y2={H - 22} stroke={m.c} strokeDasharray={m.dash} strokeWidth={1.4} opacity={0.85} />
              <text x={x(m.d) + 4} y={H - 8 - (n === 2 ? 0 : 0)} fill={m.c} fontSize={10} fontFamily="var(--mono)"
                textAnchor={n === 2 && x(m.d) > W - 120 ? "end" : "start"} dx={n === 2 && x(m.d) > W - 120 ? -8 : 0}>
                {m.label}
              </text>
            </g>
          ))}
          {placed.map(({ item, x: nx, y: ny, clipped }) => {
            const c = color(item, chain.gate);
            const label = item.title.length > 21 ? item.title.slice(0, 20) + "…" : item.title;
            return (
              <g key={item.key} className="node" style={{ transform: `translate(${nx}px, ${ny}px)` }} data-key={item.key}>
                <title>
                  {`${item.title}\n${item.status.replace("_", " ")} · planned ${fmt(item.planned_finish, true)} · forecast ${fmt(item.early_finish, true)}` +
                    (item.total_float !== null && item.total_float !== undefined ? ` · float ${item.total_float} bd` : "") +
                    (item.notes ? `\n${item.notes}` : "")}
                </title>
                <rect width={NODE_W} height={NODE_H} rx={5} fill={c.fill} stroke={c.stroke} strokeWidth={c.width} />
                <text x={7} y={11} fill="var(--fg)" fontSize={10} fontWeight={600} fontFamily="var(--body)">{label}</text>
                <text x={7} y={21} fill={item.finish_shift_days > 0 ? "var(--crit)" : "var(--muted)"} fontSize={9} fontFamily="var(--mono)">
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
      <div className="legend">
        <span><i style={{ background: "var(--good)" }} />done</span>
        <span><i style={{ background: "var(--paper)" }} />gating / near-critical</span>
        <span><i style={{ background: "var(--crit)" }} />critical path or slipped</span>
        <span><i style={{ background: "var(--line-2)" }} />on track</span>
        <span>dashed links leave finished items · hover a box for dates and float</span>
      </div>
    </section>
  );
}
