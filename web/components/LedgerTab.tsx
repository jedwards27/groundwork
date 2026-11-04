import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { Button, KIND, SIZE } from "baseui/button";
import { ChevronRight } from "baseui/icon";
import { toaster } from "baseui/toast";
import { ParagraphSmall } from "baseui/typography";
import { useState } from "react";
import { useNavigate } from "react-router";
import { get, send } from "@/lib/client";
import { DECISION_LABEL, TEMPLATE_LABEL } from "@/lib/format";
import type { Attestation, LedgerEntry, Verify } from "@/lib/types";
import { app } from "@/copy/app";
import { project } from "@/copy/project";
import { Chip, Drawer, Empty, Field, Grow, Line, matches, Mono, Muted, Quote, Row, Search, usePages } from "./ui";

const say = project.ledger;

function what(e: LedgerEntry): string {
  const p = e.payload as Record<string, unknown>;
  const preset = typeof p.preset === "string" ? (TEMPLATE_LABEL[p.preset] ?? p.preset) : undefined;
  const decision = typeof p.decision === "string" ? (DECISION_LABEL[p.decision] ?? p.decision) : undefined;
  return [p.ref, p.title ?? preset ?? p.event ?? p.subject, decision ?? p.verdict].filter(Boolean).join(", ") || e.type.replace(/_/g, " ");
}

// `tamper`: the demo's "try to break it" control, on the demo project away from the hosted demo.
export function LedgerTab({ site, tamper }: { site: string; tamper: boolean }) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const ledger = useQuery({
    queryKey: ["ledger", site, "informed"],
    queryFn: () => get<{ entries: LedgerEntry[] }>(`sites/${site}/ledger?arm=informed`),
  });
  const verify = useQuery({ queryKey: ["verify", site], queryFn: () => get<Verify>(`sites/${site}/ledger/verify`) });
  const v = verify.data;
  const entries = [...(ledger.data?.entries ?? [])].reverse();
  const found = entries.filter((e) => matches(q, what(e), e.type.replace(/_/g, " "), `#${e.seq}`, e.subject, e.text));
  const { rows: shown, pager } = usePages(found, 25, q);
  const entry = entries.find((e) => e.seq === open) ?? null;
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale400 })}>
      <div className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", flexWrap: "wrap" })}>
        <span data-testid="verify">
          {v &&
            (v.ok ? (
              <Chip kind="green" tip={say.intactTip} testId="chain-ok">
                {say.intact(v.count)}
              </Chip>
            ) : (
              <Chip kind="red" tip={v.problems.join(" ")} testId="chain-broken">
                {say.broken}
              </Chip>
            ))}
        </span>
        <Search value={q} onChange={setQ} placeholder={say.search} testId="ledger-search" />
      </div>
      {v && !v.ok && <Muted testId="verify-problem">{v.problems[0]}</Muted>}

      <div>
        {shown.length === 0 && <Empty>{say.empty}</Empty>}
        {shown.map((e) => (
          <Row key={e.seq} onClick={() => setOpen(e.seq)} testId={`record-${e.seq}`}>
            <span className={css({ width: "40px", flex: "0 0 auto" })}>
              <Mono>#{e.seq}</Mono>
            </span>
            <Grow>
              <Line>{what(e)}</Line>
              <Muted>
                {e.type.replace(/_/g, " ")}
              </Muted>
            </Grow>
            <ChevronRight size={20} color={theme.colors.contentTertiary} />
          </Row>
        ))}
        {pager}
      </div>

      <Accordion>
        <Panel title={say.receipt}>
          <Receipt site={site} />
        </Panel>
        {tamper && (
          <Panel title={say.tryToBreak}>
            <div className={css({ display: "grid", gap: theme.sizing.scale300 })}>
              <ParagraphSmall margin={0}>{say.tryToBreakBody}</ParagraphSmall>
              <div className={css({ display: "flex", gap: theme.sizing.scale300 })}>
                <Button
                  kind={KIND.secondary}
                  size={SIZE.compact}
                  data-testid="tamper"
                  onClick={async () => {
                    try {
                      const r = await send<{ edited_seq: number }>("POST", "demo/tamper");
                      await qc.invalidateQueries();
                      toaster.warning(say.tampered(r.edited_seq), {});
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    } catch (e) {
                      toaster.negative((e as Error).message, {});
                    }
                  }}
                >
                  {say.tamper}
                </Button>
                <Button
                  kind={KIND.tertiary}
                  size={SIZE.compact}
                  data-testid="restore"
                  onClick={async () => {
                    try {
                      await send("POST", "demo/reset");
                      await qc.invalidateQueries();
                      toaster.positive(say.restored, {});
                    } catch (e) {
                      toaster.negative((e as Error).message, {});
                    }
                  }}
                >
                  {say.restore}
                </Button>
              </div>
            </div>
          </Panel>
        )}
      </Accordion>

      <Drawer
        open={!!entry}
        onClose={() => setOpen(null)}
        title={entry ? say.record(entry.seq) : ""}
        testId="record-drawer"
        footer={
          entry && (
            <Button kind={KIND.secondary} onClick={() => navigate(`/projects/${site}/settings?record=${entry.seq}`)} data-testid="verify-record">
              {say.verifyRecord}
            </Button>
          )
        }
      >
        {entry && (
          <>
            <Muted>
              {entry.type.replace(/_/g, " ")}, {new Date(entry.recorded_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
            </Muted>
            <Field label={say.what}>{what(entry)}</Field>
            {typeof entry.payload.clause === "string" && entry.payload.clause && <Field label={say.clause}>{entry.payload.clause}</Field>}
            {(entry.subject || entry.text) && (
              <Field label={say.text}>
                {entry.subject && <ParagraphSmall margin={0}>{entry.subject}</ParagraphSmall>}
                {entry.text && <Quote>{entry.text}</Quote>}
              </Field>
            )}
            <Field label={say.hash}>
              <Mono>{entry.hash}</Mono>
            </Field>
            <Field label={say.linksTo}>
              <Mono>{entry.prev_hash}</Mono>
            </Field>
          </>
        )}
      </Drawer>
    </div>
  );
}

function Receipt({ site }: { site: string }) {
  const [css, theme] = useStyletron();
  const q = useQuery({ queryKey: ["attestation", site], queryFn: () => get<Attestation>(`sites/${site}/attestation`) });
  const a = q.data?.attestation;
  if (!a) return <Empty>{app.common.loading}</Empty>;
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
      <Muted>{say.receiptIntro}</Muted>
      <Field label={say.violations}>
        <span data-testid="violations">{say.violationsLine(a.violations.count, a.violations.definition)}</span>
      </Field>
      <Field label={say.chain}>{say.chainLine(a.ledger.chain_verified, a.ledger.entries)}</Field>
      <Field label={say.mandate}>{say.mandateLine(a.mandate.version, TEMPLATE_LABEL[a.mandate.preset] ?? a.mandate.preset)}</Field>
      <Field label={say.doesNotProve}>
        {a.what_this_does_not_prove.map((x) => (
          <ParagraphSmall key={x} margin={0}>
            {x}
          </ParagraphSmall>
        ))}
      </Field>
      <div>
        <Button kind={KIND.secondary} size={SIZE.compact} onClick={download}>
          {say.download}
        </Button>
      </div>
    </div>
  );
}
