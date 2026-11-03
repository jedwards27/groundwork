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
import { Chip, Drawer, Empty, Field, Grow, Line, Mono, Muted, Quote, Row } from "./ui";

function what(e: LedgerEntry): string {
  const p = e.payload as Record<string, unknown>;
  const preset = typeof p.preset === "string" ? (TEMPLATE_LABEL[p.preset] ?? p.preset) : undefined;
  const decision = typeof p.decision === "string" ? (DECISION_LABEL[p.decision] ?? p.decision) : undefined;
  return [p.ref, p.title ?? preset ?? p.event ?? p.subject, decision ?? p.verdict].filter(Boolean).join(" · ") || e.type.replace(/_/g, " ");
}

// `tamper`: the demo's "try to break it" control, on the demo project away from the hosted demo.
export function LedgerTab({ site, tamper }: { site: string; tamper: boolean }) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const ledger = useQuery({
    queryKey: ["ledger", site, "informed"],
    queryFn: () => get<{ entries: LedgerEntry[] }>(`sites/${site}/ledger?arm=informed`),
  });
  const verify = useQuery({ queryKey: ["verify", site], queryFn: () => get<Verify>(`sites/${site}/ledger/verify`) });
  const v = verify.data;
  const entries = [...(ledger.data?.entries ?? [])].reverse();
  const shown = all ? entries : entries.slice(0, 20);
  const entry = entries.find((e) => e.seq === open) ?? null;
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale400 })}>
      <div className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", flexWrap: "wrap" })}>
        <span data-testid="verify">
          {v &&
            (v.ok ? (
              <Chip
                kind="green"
                tip="Each record is sealed to the one before it with a fingerprint (a hash). Editing any past record, even with access to the database, breaks the seal. Groundwork checks it every time you open this tab."
                testId="chain-ok"
              >
                Intact · {v.count} {v.count === 1 ? "record" : "records"}
              </Chip>
            ) : (
              <Chip kind="red" tip={v.problems.join(" ")} testId="chain-broken">
                Edited after the fact
              </Chip>
            ))}
        </span>
        <span className={css({ marginLeft: "auto" })}>
          <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => navigate(`/verify?project=${site}`)} data-testid="verify-receipt">
            Verify a receipt
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
        <Panel title="Receipt">
          <Receipt site={site} />
        </Panel>
        {tamper && (
          <Panel title="Try to break it">
            <div className={css({ display: "grid", gap: theme.sizing.scale300 })}>
              <ParagraphSmall margin={0}>
                Edit one recorded decision the way someone with full database access could. The tag above turns to "Edited after the fact".
                Restore puts the demo back the way it started.
              </ParagraphSmall>
              <div className={css({ display: "flex", gap: theme.sizing.scale300 })}>
                <Button
                  kind={KIND.secondary}
                  size={SIZE.compact}
                  data-testid="tamper"
                  onClick={async () => {
                    try {
                      const r = await send<{ edited_seq: number }>("POST", "demo/tamper");
                      await qc.invalidateQueries();
                      toaster.warning(`Record #${r.edited_seq} was edited behind the ledger's back.`, {});
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    } catch (e) {
                      toaster.negative((e as Error).message, {});
                    }
                  }}
                >
                  Tamper with one record
                </Button>
                <Button
                  kind={KIND.tertiary}
                  size={SIZE.compact}
                  data-testid="restore"
                  onClick={async () => {
                    try {
                      await send("POST", "demo/reset");
                      await qc.invalidateQueries();
                      toaster.positive("The demo is back the way it started.", {});
                    } catch (e) {
                      toaster.negative((e as Error).message, {});
                    }
                  }}
                >
                  Restore
                </Button>
              </div>
            </div>
          </Panel>
        )}
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
