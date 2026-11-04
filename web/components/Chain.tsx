// The schedule: every step on the calendar, one row each, grouped by who owes it. The steps that
// decide the date are blue and joined by arrows; the one the date waits on now is amber. Drawn with
// Apache ECharts (a custom series per layer), so it zooms, pans and explains each bar on hover.
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ButtonGroup, MODE } from "baseui/button-group";
import { CustomChart } from "echarts/charts";
import { AriaComponent, DataZoomComponent, GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import type { CustomSeriesRenderItemAPI, CustomSeriesRenderItemParams, CustomSeriesRenderItemReturn, EChartsOption } from "echarts";
import { useEffect, useMemo, useRef, useState } from "react";
import { fmt, parseDate } from "@/lib/format";
import type { ChainView, ItemView } from "@/lib/types";
import { project } from "@/copy/project";
import { Muted } from "./ui";

echarts.use([CustomChart, GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, AriaComponent, SVGRenderer]);

const say = project.overview.graph;
const DAY = 86_400_000;
const ROW = 26;
const LABEL_W = 230;

type Range = "near" | "all";
type Row = { kind: "lane"; label: string } | { kind: "step"; item: ItemView; start: number; end: number };

const closed = (i: ItemView) => i.status === "done" || i.status === "cancelled";
const ms = (d: string | null | undefined) => parseDate(d ?? null)?.getTime() ?? NaN;

export function Chain({ chain }: { chain: ChainView }) {
  const [css, theme] = useStyletron();
  const t = theme.colors;
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  const asOf = ms(chain.as_of);
  const nearStart = asOf - 42 * DAY;
  const hidden = chain.items.filter((i) => closed(i) && ms(i.early_finish) < nearStart).length;
  // When most steps finished long ago, start on the whole project.
  const [range, setRange] = useState<Range>(hidden > chain.items.length - hidden ? "all" : "near");

  const { rows, x0, x1 } = useMemo(() => {
    const target = ms(chain.milestone.target_date);
    const forecast = ms(chain.milestone.forecast_finish ?? chain.milestone.target_date);
    const horizon = Math.max(target, forecast) + 35 * DAY;
    const all = range === "all";
    const shown = chain.items.filter((i) => all || !(closed(i) && ms(i.early_finish) < nearStart));
    const span = (i: ItemView) => {
      const end = ms(i.status === "done" ? (i.actual_finish ?? i.early_finish) : i.status === "cancelled" ? i.planned_finish : i.early_finish);
      const start = Math.min(end, ms(i.status === "not_started" ? i.early_start : (i.planned_start ?? i.early_start)) || end);
      return { start, end };
    };
    const out: Row[] = [];
    for (const lane of chain.lanes) {
      const items = shown
        .filter((i) => i.lane === lane.key)
        .map((i) => ({ item: i, ...span(i) }))
        .sort((a, b) => a.start - b.start || a.end - b.end);
      if (!items.length) continue;
      out.push({ kind: "lane", label: lane.label });
      for (const r of items) out.push({ kind: "step", ...r });
    }
    const steps = out.filter((r): r is Extract<Row, { kind: "step" }> => r.kind === "step");
    const first = Math.min(...steps.map((r) => r.start), asOf);
    const last = Math.max(...steps.map((r) => r.end), horizon);
    return { rows: out, x0: all ? first - 14 * DAY : nearStart, x1: all ? last + 14 * DAY : horizon };
  }, [chain, range, nearStart, asOf]);

  const option = useMemo<EChartsOption>(() => {
    const row = new Map<string, number>();
    rows.forEach((r, n) => r.kind === "step" && row.set(r.item.key, n));
    const steps = rows.flatMap((r, n) => (r.kind === "step" ? [{ r, n }] : []));
    const critical = new Set(chain.critical_path);
    const pairs = chain.critical_path.slice(1).map((k, n) => [chain.critical_path[n], k] as const).filter(([a, b]) => row.has(a) && row.has(b));
    const font = theme.typography.LabelXSmall.fontFamily as string;
    const mono = theme.typography.MonoLabelXSmall.fontFamily as string;
    const late = (chain.milestone.delta_days ?? 0) > 0;

    const style = (i: ItemView) => {
      if (i.status === "cancelled") return { fill: "transparent", stroke: t.contentTertiary, dash: [3, 3], text: t.contentTertiary };
      if (i.key === chain.gate) return { fill: t.backgroundWarningLight, stroke: t.contentWarning, dash: null, text: t.contentPrimary };
      if (i.status === "done") return { fill: t.backgroundTertiary, stroke: t.borderOpaque, dash: null, text: t.contentTertiary };
      if (critical.has(i.key)) return { fill: t.backgroundAccentLight, stroke: t.contentAccent, dash: null, text: t.contentPrimary };
      return { fill: t.backgroundSecondary, stroke: t.contentTertiary, dash: null, text: t.contentSecondary };
    };

    // A bar from start to finish, or a diamond for a single date; the date sits to its right.
    const bar = (params: CustomSeriesRenderItemParams, api: CustomSeriesRenderItemAPI): CustomSeriesRenderItemReturn => {
      const { r, n } = steps[params.dataIndex];
      const i = r.item;
      // Clamp to the plot, so a step that runs past the window doesn't spill over the labels.
      const sys = params.coordSys as unknown as { x: number; width: number };
      const [ra, y] = api.coord([r.start, n]);
      const [rb] = api.coord([r.end, n]);
      const xa = Math.max(sys.x, ra);
      const xb = Math.min(sys.x + sys.width, rb);
      if (rb < sys.x || ra > sys.x + sys.width) return { type: "group", children: [] } as CustomSeriesRenderItemReturn;
      const h = (api.size?.([0, 1]) as number[])[1] * 0.56;
      const s = style(i);
      const stale = chain.stale?.[i.key];
      const shifted = !closed(i) && i.finish_shift_days > 0;
      const label =
        (i.status === "cancelled" ? say.cancelled : (i.estimated ? say.estimated : "") + fmt(i.status === "done" ? (i.actual_finish ?? i.early_finish) : i.early_finish)) +
        (shifted ? ` +${i.finish_shift_days}d` : "") +
        (stale ? say.noWord : "");
      const point = rb - ra < 6;
      const shape = point
        ? { type: "polygon" as const, shape: { points: [[xb, y - h / 2], [xb + h / 2, y], [xb, y + h / 2], [xb - h / 2, y]] } }
        : { type: "rect" as const, shape: { x: xa, y: y - h / 2, width: xb - xa, height: h, r: 3 } };
      return {
        type: "group",
        children: [
          {
            ...shape,
            style: { fill: s.fill, stroke: s.stroke, lineWidth: critical.has(i.key) || i.key === chain.gate ? 1.6 : 1, lineDash: s.dash ?? undefined },
          },
          {
            type: "text",
            invisible: rb > sys.x + sys.width,
            x: xb + (point ? h / 2 + 4 : 5),
            y,
            style: { text: label, fill: shifted || stale ? t.contentNegative : t.contentTertiary, font: `10px ${mono}`, verticalAlign: "middle" },
          },
        ],
      } as CustomSeriesRenderItemReturn;
    };

    // The chain that decides the date: from one step's finish down to the next one's start.
    const link = (params: CustomSeriesRenderItemParams, api: CustomSeriesRenderItemAPI): CustomSeriesRenderItemReturn => {
      const [a, b] = pairs[params.dataIndex];
      const ra = rows[row.get(a)!] as Extract<Row, { kind: "step" }>;
      const rb = rows[row.get(b)!] as Extract<Row, { kind: "step" }>;
      const [xa, ya] = api.coord([ra.end, row.get(a)!]);
      const [xb, yb] = api.coord([rb.start, row.get(b)!]);
      const bend = Math.max(xa + 6, Math.min(xb - 6, xa + 10));
      const color = t.contentAccent;
      return {
        type: "group",
        children: [
          { type: "polyline", shape: { points: [[xa, ya], [bend, ya], [bend, yb], [xb - 4, yb]] }, style: { stroke: color, lineWidth: 1.4, fill: "none", opacity: 0.8 } },
          { type: "polygon", shape: { points: [[xb, yb], [xb - 6, yb - 3.5], [xb - 6, yb + 3.5]] }, style: { fill: color, opacity: 0.8 } },
        ],
      } as CustomSeriesRenderItemReturn;
    };

    // A faint band behind each owner's rows.
    const bands = rows.flatMap((r, n) => (r.kind === "lane" ? [n] : []));
    const band = (params: CustomSeriesRenderItemParams, api: CustomSeriesRenderItemAPI): CustomSeriesRenderItemReturn => {
      const from = bands[params.dataIndex];
      const to = (bands[params.dataIndex + 1] ?? rows.length) - 1;
      const sys = params.coordSys as unknown as { x: number; width: number };
      const [, y0] = api.coord([x0, from]);
      const [, y1] = api.coord([x0, to]);
      const half = ROW / 2;
      return params.dataIndex % 2
        ? { type: "rect", shape: { x: sys.x - LABEL_W, y: y0 - half, width: sys.width + LABEL_W, height: y1 - y0 + ROW }, style: { fill: t.backgroundSecondary, opacity: 0.55 }, silent: true }
        : ({ type: "group", children: [] } as CustomSeriesRenderItemReturn);
    };

    // Today, the target and the forecast. When the target and forecast are close, the earlier
    // label sits left of its line and the later one right, so they never overlap.
    const target = ms(chain.milestone.target_date);
    const forecast = chain.milestone.forecast_finish && chain.milestone.forecast_finish !== chain.milestone.target_date ? ms(chain.milestone.forecast_finish) : null;
    const side = (d: number, other: number | null) => (other === null ? "center" : d < other ? "right" : "left");
    const marks = [
      { xAxis: asOf, name: say.today, lineStyle: { color: t.contentPrimary, type: [2, 3] as number[] }, label: { align: "center" } },
      { xAxis: target, name: say.target(fmt(chain.milestone.target_date)), lineStyle: { color: t.contentTertiary, type: "dashed" as const }, label: { align: side(target, forecast) } },
      ...(forecast !== null
        ? [{ xAxis: forecast, name: say.forecast(fmt(chain.milestone.forecast_finish)), lineStyle: { color: late ? t.contentNegative : t.contentAccent, type: "dashed" as const }, label: { align: side(forecast, target), color: late ? t.contentNegative : t.contentAccent } }]
        : []),
    ];

    return {
      animation: false,
      aria: { enabled: true, label: { description: say.aria(steps.length) } },
      textStyle: { fontFamily: font },
      grid: { left: LABEL_W + 8, right: 70, top: 28, bottom: 44 },
      xAxis: {
        type: "time",
        min: x0,
        max: x1,
        position: "top",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: true, lineStyle: { color: t.borderOpaque, opacity: 0.6 } },
        axisLabel: { color: t.contentTertiary, fontSize: 10, fontFamily: mono, hideOverlap: true },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: rows.map((r) => (r.kind === "lane" ? r.label : r.item.title)),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          interval: 0,
          margin: LABEL_W,
          align: "left",
          formatter: (value: string, n: number) => {
            const r = rows[n];
            if (r?.kind === "lane") return `{lane|${value}}`;
            return closed((r as Extract<Row, { kind: "step" }>).item) ? `{done|${value}}` : `{step|${value}}`;
          },
          rich: {
            lane: { fontSize: 11, fontWeight: 600, color: t.contentSecondary, width: LABEL_W - 12, overflow: "truncate" },
            step: { fontSize: 11.5, color: t.contentPrimary, width: LABEL_W - 24, overflow: "truncate", padding: [0, 0, 0, 12] },
            done: { fontSize: 11.5, color: t.contentTertiary, width: LABEL_W - 24, overflow: "truncate", padding: [0, 0, 0, 12] },
          },
        },
      },
      dataZoom: [
        { type: "inside", xAxisIndex: 0, filterMode: "none", zoomOnMouseWheel: "ctrl", moveOnMouseWheel: false, moveOnMouseMove: true },
        { type: "slider", xAxisIndex: 0, filterMode: "none", height: 16, bottom: 10, brushSelect: false, showDetail: false, borderColor: t.borderOpaque, fillerColor: "rgba(127,140,170,0.15)", dataBackground: { lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 } } },
      ],
      tooltip: {
        trigger: "item",
        confine: true,
        backgroundColor: t.backgroundPrimary,
        borderColor: t.borderOpaque,
        textStyle: { color: t.contentPrimary, fontSize: 12 },
        formatter: (p: unknown) => {
          const { seriesId, dataIndex } = p as { seriesId: string; dataIndex: number };
          if (seriesId !== "steps") return "";
          const i = steps[dataIndex].r.item;
          const waits = chain.links.filter((l) => l.succ === i.key).map((l) => chain.items.find((x) => x.key === l.pred)?.title ?? l.pred);
          const esc = (x: string) => x.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
          return [
            `<b>${esc(i.title)}</b>`,
            say.tooltip(i.status.replace("_", " "), fmt(i.planned_finish, true), fmt(i.status === "done" ? (i.actual_finish ?? i.early_finish) : i.early_finish, true)) +
              (i.total_float !== null && i.total_float !== undefined && !closed(i) ? say.float(i.total_float) : ""),
            i.estimated ? say.estimatedTip : "",
            chain.stale?.[i.key] ? say.staleTip(chain.stale[i.key]) : "",
            waits.length ? say.waitsOn(waits.map(esc).join("; ")) : "",
            i.notes ? esc(i.notes) : "",
          ]
            .filter(Boolean)
            .join("<br/>");
        },
      },
      series: [
        { id: "bands", type: "custom", renderItem: band, data: bands.map((n) => [x0, n]), silent: true, z: 0, clip: false },
        { id: "links", type: "custom", renderItem: link, data: pairs.map((_, n) => [n]), silent: true, z: 1 },
        {
          id: "steps",
          type: "custom",
          renderItem: bar,
          data: steps.map(({ r, n }) => [r.start, n, r.end]),
          encode: { x: [0, 2], y: 1 },
          z: 2,
          markLine: {
            silent: true,
            symbol: "none",
            label: { formatter: "{b}", position: "end", fontFamily: mono, fontSize: 10, color: t.contentSecondary },
            data: marks,
          },
        },
      ],
    } as EChartsOption;
  }, [rows, x0, x1, chain, theme, t, asOf]);

  useEffect(() => {
    if (!box.current) return;
    const c = echarts.init(box.current, null, { renderer: "svg" });
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(box.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);
  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true });
  }, [option]);

  const height = rows.length * ROW + 72;
  return (
    <div>
      <div className={css({ display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.sizing.scale400, marginBottom: theme.sizing.scale300 })}>
        <ButtonGroup mode={MODE.radio} size={SIZE.compact} selected={range === "near" ? 0 : 1} onClick={(_, i) => setRange(i === 0 ? "near" : "all")}>
          <Button data-testid="range-near">{say.near}</Button>
          <Button data-testid="range-all">{say.all}</Button>
        </ButtonGroup>
        {range === "near" && hidden > 0 && (
          <span className={css({ display: "inline-flex", alignItems: "center", gap: theme.sizing.scale200 })} data-testid="hidden-steps">
            <Muted>{say.hidden(hidden)}</Muted>
            <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => setRange("all")}>
              {say.showAll}
            </Button>
          </span>
        )}
      </div>
      <div ref={box} data-testid="schedule-chart" data-rows={rows.filter((r) => r.kind === "step").length} className={css({ width: "100%", height: `${height}px` })} />
      <Muted>{say.legend}</Muted>
    </div>
  );
}
