import { useQuery } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { Button, KIND, SIZE } from "baseui/button";
import { ChevronRight } from "baseui/icon";
import { Segment, SegmentedControl } from "baseui/segmented-control";
import { ParagraphSmall } from "baseui/typography";
import { useState } from "react";
import { useNavigate } from "react-router";
import { get } from "@/lib/client";
import { DECISION_LABEL, TEMPLATE_LABEL } from "@/lib/format";
import type { Attestation, LedgerEntry, ScoreRow, Verify } from "@/lib/types";
import { Chip, Drawer, Empty, Field, Grow, Hint, Line, Mono, Muted, Quote, Row } from "./ui";

type Arm = "informed" | "blind" | "all";

function what(e: LedgerEntry): string {
  const p = e.payload as Record<string, unknown>;
  const preset = typeof p.preset === "string" ? (TEMPLATE_LABEL[p.preset] ?? p.preset) : undefined;
  const decision = typeof p.decision === "string" ? (DECISION_LABEL[p.decision] ?? p.decision) : undefined;
  return [p.ref, p.title ?? preset ?? p.event ?? p.subject, decision ?? p.verdict].filter(Boolean).join(" · ") || e.type.replace(/_/g, " ");
}

export function LedgerTab({ site }: { site: string }) {
  const [css, theme] = useStyletron();
  const navigate = useNavigate();
  const [arm, setArm] = useState<Arm>("informed");
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const ledger = useQuery({
    queryKey: ["ledger", site, arm],
    queryFn: () => get<{ entries: LedgerEntry[] }>(`sites/${site}/ledger${arm === "all" ? "?arm=" : `?arm=${arm}`}`),
  });
  const verify = useQuery({ queryKey: ["verify", site], queryFn: () => get<Verify>(`sites/${site}/ledger/verify`) });
  const v = verify.data;
  const entries = [...(ledger.data?.entries ?? [])].reverse();
  const shown = all ? entries : entries.slice(0, 20);
  const entry = entries.find((e) => e.seq === open) ?? null;
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale400 })}>
      <div className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", flexWrap: "wrap" })}>
        <div className={css({ width: "340px", maxWidth: "100%" })}>
          <SegmentedControl activeKey={arm} onChange={({ activeKey }) => setArm(activeKey as Arm)} width="100%">
            <Segment key="informed" label="Your plan" />
            <Segment key="blind" label="Blind arm" />
            <Segment key="all" label="Everything" />
          </SegmentedControl>
        </div>
        <Hint text="The blind arm is the same model planning from your goals without seeing the mandate. The gap between the arms shows how much staying in scope comes from the model's own judgment rather than the written rules." />
        <span className={css({ marginLeft: "auto", display: "flex", gap: theme.sizing.scale200, alignItems: "center" })} data-testid="verify">
          {v &&
            (v.ok ? (
              <Chip kind="green" tip={`Every record links to the one before it, and each hashes to what was stored. Head ${v.head_hash.slice(0, 12)}…`} testId="chain-ok">
                Verified · {v.count} {v.count === 1 ? "record" : "records"}
              </Chip>
            ) : (
              <Chip kind="red" tip={v.problems.join(" ")} testId="chain-broken">
                Chain broken
              </Chip>
            ))}
          <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => verify.refetch()}>
            Verify again
          </Button>
        </span>
      </div>
      {v && !v.ok && <Muted testId="verify-problem">{v.problems[0]}</Muted>}

      <div>
        {shown.length === 0 && <Empty>No records yet.</Empty>}
        {shown.map((e) => (
          <Row key={e.seq} onClick={() => setOpen(e.seq)} testId={`record-${e.seq}`}>
            <span className={css({ width: "40px", flex: "0 0 auto" })}>
              <Mono>#{e.seq}</Mono>
            </span>
            <Grow>
              <Line>{what(e)}</Line>
              <Muted>
                {e.type.replace(/_/g, " ")}
                {e.arm === "blind" ? " · blind arm" : ""}
              </Muted>
            </Grow>
            {e.dry_run && <Chip tip="It would have been sent; nothing left in dry run.">Not sent · dry run</Chip>}
            <ChevronRight size={20} color={theme.colors.contentTertiary} />
          </Row>
        ))}
        {entries.length > 20 && (
          <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => setAll(!all)}>
            {all ? "Show fewer" : `Show all ${entries.length}`}
          </Button>
        )}
      </div>

      <Accordion>
        <Panel title="How the model did">
          <Scorecard site={site} />
        </Panel>
        <Panel title="Receipt">
          <Receipt site={site} />
        </Panel>
      </Accordion>

      <Drawer
        open={!!entry}
        onClose={() => setOpen(null)}
        title={entry ? `Record #${entry.seq}` : ""}
        testId="record-drawer"
        footer={
          entry && (
            <Button kind={KIND.secondary} onClick={() => navigate(`/verify?project=${site}&record=${entry.seq}`)} data-testid="verify-record">
              Verify this record
            </Button>
          )
        }
      >
        {entry && (
          <>
            <Muted>
              {entry.type.replace(/_/g, " ")} · {new Date(entry.recorded_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
            </Muted>
            <Field label="What">{what(entry)}</Field>
            {typeof entry.payload.clause === "string" && entry.payload.clause && <Field label="Mandate clause">{entry.payload.clause}</Field>}
            {(entry.subject || entry.text) && (
              <Field label={entry.dry_run ? "Would have been sent (dry run: nothing left)" : "Text"}>
                {entry.subject && <ParagraphSmall margin={0}>{entry.subject}</ParagraphSmall>}
                {entry.text && <Quote>{entry.text}</Quote>}
              </Field>
            )}
            <Field label="Hash">
              <Mono>{entry.hash}</Mono>
            </Field>
            <Field label="Links to">
              <Mono>{entry.prev_hash}</Mono>
            </Field>
          </>
        )}
      </Drawer>
    </div>
  );
}

function Scorecard({ site }: { site: string }) {
  const q = useQuery({ queryKey: ["scorecard", site], queryFn: () => get<{ rows: ScoreRow[]; note: string }>(`sites/${site}/scorecard`) });
  const rows = q.data?.rows ?? [];
  const pct = (x: number) => `${Math.round(x * 1000) / 10}%`;
  if (!rows.length) return <Empty>No plans yet.</Empty>;
  return (
    <div data-testid="scorecard">
      {rows.map((r) => (
        <Row key={`${r.arm}-${r.model_id}`}>
          <Grow>
            <Line>{r.label}</Line>
            <Muted>
              {r.model_id} · {r.proposals} proposals
            </Muted>
          </Grow>
          <Chip kind={r.over_reach ? "red" : "gray"} tip="Proposed more autonomy than the mandate allows; the gateway held it.">
            Held {r.over_reach} ({pct(r.over_reach_rate)})
          </Chip>
          <Chip tip="Asked when the mandate allowed acting.">Cautious {r.over_caution}</Chip>
          <Chip kind={r.honest_rate === null || r.honest_rate === 1 ? "gray" : "red"} tip="Share of reports that match the ledger.">
            Honest {r.honest_rate === null ? "—" : pct(r.honest_rate)}
          </Chip>
        </Row>
      ))}
      {q.data?.note && <Muted>{q.data.note}</Muted>}
    </div>
  );
}

function Receipt({ site }: { site: string }) {
  const [css, theme] = useStyletron();
  const q = useQuery({ queryKey: ["attestation", site], queryFn: () => get<Attestation>(`sites/${site}/attestation`) });
  const a = q.data?.attestation;
  if (!a) return <Empty>Loading…</Empty>;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(q.data, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `receipt-${a.site}-${a.ledger.head_seq}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale300 })} data-testid="receipt">
      <Muted>A signed summary of the ledger, from its first record to its latest, that anyone can check.</Muted>
      <Field label="Violations">
        <span data-testid="violations">
          {a.violations.count} ({a.violations.definition})
        </span>
      </Field>
      <Field label="Chain">
        {a.ledger.chain_verified ? "verified" : "FAILED"} · {a.ledger.entries} records
      </Field>
      <Field label="Mandate">
        v{a.mandate.version} · {TEMPLATE_LABEL[a.mandate.preset] ?? a.mandate.preset}
      </Field>
      <Field label="What this does not prove">
        {a.what_this_does_not_prove.map((x) => (
          <ParagraphSmall key={x} margin={0}>
            {x}
          </ParagraphSmall>
        ))}
      </Field>
      <div>
        <Button kind={KIND.secondary} size={SIZE.compact} onClick={download}>
          Download the receipt
        </Button>
      </div>
    </div>
  );
}
