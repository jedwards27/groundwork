import { useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { Button, KIND, SIZE } from "baseui/button";
import { Modal, ModalBody, ModalButton, ModalFooter, ModalHeader } from "baseui/modal";
import { Select } from "baseui/select";
import { toaster } from "baseui/toast";
import { LabelMedium, ParagraphSmall } from "baseui/typography";
import { useEffect, useState } from "react";
import { send } from "@/lib/client";
import { DECISION_LABEL, TEMPLATE_LABEL as LABEL } from "@/lib/format";
import { project } from "@/copy/project";
import type { CompareRow, MandateView, Me, PlanView } from "@/lib/types";
import { Chip, DecisionTag, Grow, Hint, Line, Muted, Row, Section } from "./ui";

const say = project.mandate;

export function MandateTab({ site, mandate, compare, plan, me }: {
  site: string;
  mandate: MandateView;
  compare: CompareRow[];
  plan: PlanView | null;
  me: Me | null;
}) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const [chosen, setChosen] = useState(mandate.preset);
  const [confirm, setConfirm] = useState(false);
  useEffect(() => setChosen(mandate.preset), [mandate.preset]);
  const changed = chosen !== mandate.preset;
  const approver = !!me?.approver;
  const preview = compare.find((r) => r.preset === chosen);
  const now = compare.find((r) => r.current);
  // What the previewed template would decide differently on the latest plan.
  const changes = (plan?.actions ?? [])
    .map((a) => ({ a, from: now?.decisions[a.ref], to: preview?.decisions[a.ref] }))
    .filter((x) => x.from && x.to && x.from !== x.to);
  const issue = async () => {
    try {
      const r = await send<{ version: number; redecided: { ref: string; from: string; to: string }[]; executed: string[] }>("PUT", `sites/${site}/mandate`, {
        preset: chosen,
      });
      const moved = r.redecided.filter((x) => x.from !== x.to);
      toaster.positive(
        say.issued(r.version) +
          (moved.length
            ? say.decidedAgain(moved.map((x) => say.move(x.ref, DECISION_LABEL[x.from] ?? x.from, DECISION_LABEL[x.to] ?? x.to)).join(", "))
            : say.noneChanged) +
          (r.executed.length ? say.ranDry(r.executed.join(", ")) : ""),
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
            aria-label={say.templateLabel}
          />
        </div>
        <Chip testId="mandate-version">{changed ? say.preview : say.version(mandate.version)}</Chip>
        <Hint text={say.hint} />
        <span className={css({ marginLeft: "auto" })}>
          <Button size={SIZE.compact} disabled={!changed || !approver} onClick={() => setConfirm(true)} data-testid="issue">
            {say.issue(mandate.version + 1)}
          </Button>
        </span>
      </div>
      {changed && (
        <div
          data-testid="preview"
          className={css({
            padding: theme.sizing.scale500,
            borderRadius: theme.borders.radius300,
            background: theme.colors.backgroundAccentLight,
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr)",
            gap: theme.sizing.scale300,
          })}
        >
          <LabelMedium>{say.previewTitle(LABEL[chosen] ?? chosen)}</LabelMedium>
          <ParagraphSmall margin={0}>{!plan ? say.previewNoPlan : changes.length ? say.previewChanges : say.previewNoChange}</ParagraphSmall>
          {changes.map(({ a, from, to }) => (
            <div key={a.ref} className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", flexWrap: "wrap" })}>
              <DecisionTag decision={from ?? null} />
              <span aria-hidden>→</span>
              <DecisionTag decision={to ?? null} />
              <ParagraphSmall margin={0}>{a.title}</ParagraphSmall>
            </div>
          ))}
          <Muted>{say.previewNote}</Muted>
        </div>
      )}

      <Section title={say.rulesTitle(mandate.version)} testId="plain-lines">
        {mandate.plain_lines.map((l) => (
          <Row key={l}>
            <ParagraphSmall margin={0}>{l}</ParagraphSmall>
          </Row>
        ))}
      </Section>

      <Accordion>
        {compare.length > 0 && (
          <Panel title={say.compare}>
            {compare.map((r) => (
              <Row key={r.preset}>
                <Grow>
                  <Line>
                    {LABEL[r.preset] ?? r.preset}
                    {r.current ? say.current : ""}
                  </Line>
                  <Muted>{say.daysBack(r.recovered_if_they_agree)}</Muted>
                </Grow>
                <Chip kind="green">{say.allow(r.auto)}</Chip>
                <Chip kind="yellow">{say.ask(r.ask)}</Chip>
                <Chip kind="red">{say.deny(r.refuse)}</Chip>
                {r.held > 0 && <Chip tip={say.heldTip}>{say.held(r.held)}</Chip>}
              </Row>
            ))}
          </Panel>
        )}
        <Panel title={say.versions}>
          {mandate.history.map((v) => (
            <Row key={v.version}>
              <Grow>
                <Line>{say.versionRow(v.version, LABEL[v.preset] ?? v.preset)}</Line>
              </Grow>
              <Muted>{new Date(v.at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</Muted>
            </Row>
          ))}
        </Panel>
      </Accordion>
      <Muted>{say.footer}</Muted>

      <Modal isOpen={confirm} onClose={() => setConfirm(false)} closeable>
        <ModalHeader>{say.confirmTitle(mandate.version + 1, LABEL[chosen] ?? chosen)}</ModalHeader>
        <ModalBody>{say.confirmBody}</ModalBody>
        <ModalFooter>
          <ModalButton kind={KIND.tertiary} onClick={() => setConfirm(false)}>
            {say.cancel}
          </ModalButton>
          <ModalButton onClick={issue} data-testid="issue-confirm">
            {say.issue(mandate.version + 1)}
          </ModalButton>
        </ModalFooter>
      </Modal>
    </div>
  );
}
