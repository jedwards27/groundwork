import { useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { Button, KIND, SIZE } from "baseui/button";
import { Modal, ModalBody, ModalButton, ModalFooter, ModalHeader } from "baseui/modal";
import { Select } from "baseui/select";
import { toaster } from "baseui/toast";
import { ParagraphSmall } from "baseui/typography";
import { useEffect, useState } from "react";
import { send } from "@/lib/client";
import { DECISION_LABEL, TEMPLATE_LABEL as LABEL } from "@/lib/format";
import type { CompareRow, MandateView, Me } from "@/lib/types";
import { Chip, Grow, Hint, Line, Muted, Row } from "./ui";

export function MandateTab({ site, mandate, compare, me }: { site: string; mandate: MandateView; compare: CompareRow[]; me: Me | null }) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const [chosen, setChosen] = useState(mandate.preset);
  const [confirm, setConfirm] = useState(false);
  useEffect(() => setChosen(mandate.preset), [mandate.preset]);
  const changed = chosen !== mandate.preset;
  const approver = !!me?.approver;
  const preview = compare.find((r) => r.preset === chosen);
  const issue = async () => {
    try {
      const r = await send<{ version: number; redecided: { ref: string; from: string; to: string }[]; executed: string[] }>("PUT", `sites/${site}/mandate`, {
        preset: chosen,
      });
      const moved = r.redecided.filter((x) => x.from !== x.to);
      toaster.positive(
        `Mandate v${r.version} issued. ${
          moved.length
            ? `Decided again: ${moved.map((x) => `${x.ref} ${DECISION_LABEL[x.from] ?? x.from} → ${DECISION_LABEL[x.to] ?? x.to}`).join(", ")}.`
            : "No open action changed."
        }${r.executed.length ? ` Ran in dry run: ${r.executed.join(", ")}.` : ""}`,
        {},
      );
      await qc.invalidateQueries();
    } catch (e) {
      toaster.negative((e as Error).message, {});
    } finally {
      setConfirm(false);
    }
  };
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale500 })}>
      <div className={css({ display: "flex", gap: theme.sizing.scale400, alignItems: "center", flexWrap: "wrap" })}>
        <div className={css({ width: "200px" })} data-testid="template">
          <Select
            options={mandate.presets.map((p) => ({ id: p, label: LABEL[p] ?? p }))}
            value={[{ id: chosen, label: LABEL[chosen] ?? chosen }]}
            onChange={({ value }) => value[0] && setChosen(String(value[0].id))}
            clearable={false}
            searchable={false}
            size="compact"
            aria-label="Mandate template"
          />
        </div>
        <Chip testId="mandate-version">{changed ? "preview" : `v${mandate.version}`}</Chip>
        <Hint text="A template sets what may run on its own, what must ask a named person, and what is denied. Paying, signing and deleting are denied under every template." />
        <span className={css({ marginLeft: "auto" })}>
          <Button size={SIZE.compact} disabled={!changed || !approver} onClick={() => setConfirm(true)} data-testid="issue">
            Issue v{mandate.version + 1}
          </Button>
        </span>
      </div>
      {changed && preview && (
        <Muted testId="preview">
          Under {LABEL[chosen]}, the latest plan would get {preview.auto} allow, {preview.ask} ask and {preview.refuse} deny. Nothing changes
          until you issue a new version.
        </Muted>
      )}

      <div data-testid="plain-lines">
        {mandate.plain_lines.map((l) => (
          <Row key={l}>
            <ParagraphSmall margin={0}>{l}</ParagraphSmall>
          </Row>
        ))}
      </div>

      <Accordion>
        {compare.length > 0 && (
          <Panel title="Compare templates on the latest plan">
            {compare.map((r) => (
              <Row key={r.preset}>
                <Grow>
                  <Line>
                    {LABEL[r.preset] ?? r.preset}
                    {r.current ? " (now)" : ""}
                  </Line>
                  <Muted>{r.recovered_if_they_agree} days back if they agree</Muted>
                </Grow>
                <Chip kind="green">Allow {r.auto}</Chip>
                <Chip kind="yellow">Ask {r.ask}</Chip>
                <Chip kind="red">Deny {r.refuse}</Chip>
                {r.held > 0 && <Chip tip="Times the agent proposed more autonomy than this template allows.">Held {r.held}</Chip>}
              </Row>
            ))}
          </Panel>
        )}
        <Panel title="Versions">
          {mandate.history.map((v) => (
            <Row key={v.version}>
              <Grow>
                <Line>
                  v{v.version} · {LABEL[v.preset] ?? v.preset}
                </Line>
              </Grow>
              <Muted>{new Date(v.at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</Muted>
            </Row>
          ))}
        </Panel>
      </Accordion>
      <Muted>Same plan, different authority: the gateway decides open actions again; it never re-plans, and what already ran stays on the record.</Muted>

      <Modal isOpen={confirm} onClose={() => setConfirm(false)} closeable>
        <ModalHeader>
          Issue mandate v{mandate.version + 1}: {LABEL[chosen]}
        </ModalHeader>
        <ModalBody>
          Open actions are decided again under the new version, and any that may now run on their own run in dry run. The new version is a
          record on the ledger, issued by you.
        </ModalBody>
        <ModalFooter>
          <ModalButton kind={KIND.tertiary} onClick={() => setConfirm(false)}>
            Cancel
          </ModalButton>
          <ModalButton onClick={issue} data-testid="issue-confirm">
            Issue v{mandate.version + 1}
          </ModalButton>
        </ModalFooter>
      </Modal>
    </div>
  );
}
