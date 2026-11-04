import { useStyletron } from "baseui";
import { ButtonGroup, MODE } from "baseui/button-group";
import { Button, SIZE } from "baseui/button";
import { TableBuilder, TableBuilderColumn } from "baseui/table-semantic";
import { useMemo, useState } from "react";
import { fmt } from "@/lib/format";
import type { ChainView, ItemView, SiteView } from "@/lib/types";
import { project } from "@/copy/project";
import { Chip, matches, Muted, Search, Section, usePages } from "./ui";

const say = project.steps;

type Row = ItemView & { owner_name: string; waits: string[]; date: string; past: number | null };
type Col = "title" | "owner" | "kind" | "status" | "date";

const closed = (i: ItemView) => i.status === "done" || i.status === "cancelled";

const FILTERS: { label: string; test: (r: Row) => boolean }[] = [
  { label: say.filters.all, test: () => true },
  { label: say.filters.open, test: (r) => !closed(r) },
  { label: say.filters.pastDue, test: (r) => r.past !== null },
  { label: say.filters.done, test: (r) => r.status === "done" },
  { label: say.filters.cancelled, test: (r) => r.status === "cancelled" },
];

const STATUS_ORDER: Record<string, number> = { in_progress: 0, not_started: 1, done: 2, cancelled: 3 };

// Every step in the project, done and cancelled ones included, as a table you can sort and filter.
export function StepsTab({ chain, site }: { chain: ChainView; site: SiteView }) {
  const [css, theme] = useStyletron();
  const [filter, setFilter] = useState(0);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ col: Col; dir: "ASC" | "DESC" }>({ col: "date", dir: "ASC" });
  const titles = useMemo(() => new Map(chain.items.map((i) => [i.key, i.title])), [chain]);
  const rows: Row[] = useMemo(() => {
    const party = (k: string) => site.parties.find((p) => p.key === k)?.name ?? k;
    const preds = new Map<string, string[]>();
    for (const l of chain.links) preds.set(l.succ, [...(preds.get(l.succ) ?? []), l.pred]);
    return chain.items.map((i) => {
      // A done step shows when it finished; an open one, when it's now expected.
      const date = i.status === "done" ? (i.actual_finish ?? i.early_finish) : i.status === "cancelled" ? i.planned_finish : i.early_finish;
      return { ...i, owner_name: party(i.owner), waits: preds.get(i.key) ?? [], date, past: chain.stale?.[i.key] ?? null };
    });
  }, [chain, site]);

  const shown = rows.filter((r) => FILTERS[filter].test(r) && matches(q, r.title, r.owner_name, r.source, r.notes, r.key));
  const key = (r: Row): string | number =>
    sort.col === "status" ? STATUS_ORDER[r.status] ?? 9 : sort.col === "owner" ? r.owner_name : sort.col === "kind" ? r.kind : sort.col === "title" ? r.title.toLowerCase() : r.date;
  shown.sort((a, b) => {
    const [x, y] = [key(a), key(b)];
    const c = x < y ? -1 : x > y ? 1 : a.date < b.date ? -1 : a.date > b.date ? 1 : 0;
    return sort.dir === "ASC" ? c : -c;
  });
  const { rows: page, pager } = usePages(shown, 25, `${filter}|${q}|${sort.col}|${sort.dir}`);
  const onSort = (id: string) => setSort((s) => ({ col: id as Col, dir: s.col === id && s.dir === "ASC" ? "DESC" : "ASC" }));
  const statusChip = (r: Row) => {
    const kind = r.status === "done" ? "green" : r.status === "cancelled" ? "gray" : r.status === "in_progress" ? "blue" : "gray";
    return <Chip kind={kind}>{say.status[r.status] ?? r.status}</Chip>;
  };

  return (
    <Section title={say.title} hint={say.hint} testId="steps">
      <div className={css({ display: "flex", flexWrap: "wrap", gap: theme.sizing.scale400, alignItems: "center" })}>
        <ButtonGroup mode={MODE.radio} size={SIZE.compact} selected={filter} onClick={(_, i) => setFilter(i)} overrides={{ Root: { style: { flexWrap: "wrap" } } }}>
          {FILTERS.map((f) => (
            <Button key={f.label}>{say.filterCount(f.label, rows.filter(f.test).length)}</Button>
          ))}
        </ButtonGroup>
        <Search value={q} onChange={setQ} placeholder={say.search} testId="steps-search" />
        <Muted>{say.count(shown.length, rows.length)}</Muted>
      </div>
      <div className={css({ overflowX: "auto" })} data-testid="steps-table">
        <TableBuilder
          data={page}
          sortColumn={sort.col}
          sortOrder={sort.dir}
          onSort={onSort}
          emptyMessage={say.empty}
          size="compact"
          overrides={{ Root: { style: { minWidth: "760px" } }, TableBodyCell: { style: { verticalAlign: "top" } } }}
        >
          <TableBuilderColumn<Row> header={say.cols.title} id="title" sortable>
            {(r) => (
              <div data-testid={`step-${r.key}`} className={css({ maxWidth: "320px" })}>
                <span className={css({ textDecoration: r.status === "cancelled" ? "line-through" : "none", color: r.status === "cancelled" ? theme.colors.contentTertiary : undefined })}>
                  {r.title}
                </span>{" "}
                {r.key === chain.gate && <Chip kind="yellow">{say.sets}</Chip>}
                {r.notes && <Muted>{r.notes}</Muted>}
              </div>
            )}
          </TableBuilderColumn>
          <TableBuilderColumn<Row> header={say.cols.owner} id="owner" sortable>
            {(r) => r.owner_name}
          </TableBuilderColumn>
          <TableBuilderColumn<Row> header={say.cols.kind} id="kind" sortable>
            {(r) => say.kinds[r.kind] ?? r.kind}
          </TableBuilderColumn>
          <TableBuilderColumn<Row> header={say.cols.status} id="status" sortable>
            {(r) => statusChip(r)}
          </TableBuilderColumn>
          <TableBuilderColumn<Row> header={say.cols.date} id="date" sortable>
            {(r) => (
              <div className={css({ whiteSpace: "nowrap" })}>
                <span title={r.estimated ? say.estimatedTip : undefined}>
                  {r.estimated ? "~" : ""}
                  {fmt(r.date, true)}
                </span>
                <Muted>
                  {r.status === "done" ? say.date.finished : r.status === "cancelled" ? say.date.planned : say.date.due}
                  {!closed(r) && r.planned_finish !== r.early_finish ? `, ${say.date.planned} ${fmt(r.planned_finish)}` : ""}
                </Muted>
                {r.past !== null && (
                  <div className={css({ color: theme.colors.contentNegative, ...theme.typography.ParagraphXSmall })}>{say.pastDue(r.past)}</div>
                )}
              </div>
            )}
          </TableBuilderColumn>
          <TableBuilderColumn<Row> header={say.cols.waits} id="waits">
            {(r) => (
              <div className={css({ maxWidth: "220px" })}>
                <Muted>{r.waits.map((k) => titles.get(k) ?? k).join("; ")}</Muted>
              </div>
            )}
          </TableBuilderColumn>
          <TableBuilderColumn<Row> header={say.cols.source} id="source">
            {(r) => (
              <div className={css({ maxWidth: "200px", overflowWrap: "anywhere" })}>
                <Muted>{r.source}</Muted>
              </div>
            )}
          </TableBuilderColumn>
        </TableBuilder>
      </div>
      {pager}
      <Muted>{say.change}</Muted>
    </Section>
  );
}
