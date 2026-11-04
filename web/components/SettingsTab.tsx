import { useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { FormControl } from "baseui/form-control";
import { Input } from "baseui/input";
import { Modal, ModalBody, ModalButton, ModalFooter, ModalHeader } from "baseui/modal";
import { toaster } from "baseui/toast";
import { ParagraphSmall } from "baseui/typography";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { send } from "@/lib/client";
import { DEMO_PROJECT, fmtLong } from "@/lib/format";
import { setKey, useKey } from "@/lib/key";
import type { CompareRow, MandateView, Me, PlanView, Session, SiteView } from "@/lib/types";
import { project } from "@/copy/project";
import { MandateTab } from "./MandateTab";
import { VerifyRecord } from "./VerifyRecord";
import { Chip, Muted, Section } from "./ui";

const say = project.settings;

// A project's settings: its mandate, and on your own computer, its name, archiving and deleting.
export function SettingsTab({ site, mandate, compare, plan, me, mine, session }: {
  site: SiteView;
  mandate: MandateView | undefined;
  compare: CompareRow[];
  plan: PlanView | null;
  me: Me | null;
  mine: boolean;
  session: Session;
}) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const key = site.key;
  const [name, setName] = useState(site.name);
  const [location, setLocation] = useState(site.location);
  const [deleting, setDeleting] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const liveKey = useKey();
  const [draftKey, setDraftKey] = useState("");
  useEffect(() => {
    setName(site.name);
    setLocation(site.location);
  }, [site.name, site.location]);
  // A link to check one record (from the Actions or Ledger tab) lands on Receipts.
  const [params] = useSearchParams();
  useEffect(() => {
    if (params.get("record")) document.querySelector('[data-testid="settings-receipts"]')?.scrollIntoView({ block: "start" });
  }, [params]);

  const post = async (what: string, path: string, body?: unknown, after?: () => void) => {
    setBusy(what);
    try {
      const r = await send<{ message: string }>("POST", path, body);
      toaster.info(r.message, {});
      after?.();
      await qc.invalidateQueries();
    } catch (e) {
      toaster.negative((e as Error).message, {});
    } finally {
      setBusy(null);
    }
  };
  const dirty = name.trim() !== site.name || location.trim() !== site.location;

  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale600 })}>
      <Section title={say.mandate} testId="settings-mandate">
        {mandate && <MandateTab site={key} mandate={mandate} compare={compare} plan={plan} me={me} />}
      </Section>

      {mine && (
        <Section title={say.details} testId="settings-details">
          <div className={css({ display: "grid", gap: theme.sizing.scale300, maxWidth: "480px" })}>
            <FormControl label={say.name} overrides={{ ControlContainer: { style: { marginBottom: 0 } } }}>
              <Input value={name} onChange={(e) => setName((e.target as HTMLInputElement).value)} size="compact" overrides={{ Input: { props: { "data-testid": "settings-name" } } }} />
            </FormControl>
            <FormControl label={say.location} overrides={{ ControlContainer: { style: { marginBottom: 0 } } }}>
              <Input value={location} onChange={(e) => setLocation((e.target as HTMLInputElement).value)} size="compact" />
            </FormControl>
            <div>
              <Button size={SIZE.compact} disabled={!dirty || !name.trim()} isLoading={busy === "details"} onClick={() => void post("details", `projects/${key}/details`, { name: name.trim(), location: location.trim() })} data-testid="settings-save">
                {say.save}
              </Button>
            </div>
            <Muted>{say.keyStays(key)}</Muted>
          </div>
        </Section>
      )}

      {!session.local && (
        <Section title={say.live} hint={say.liveHint} testId="settings-live">
          <div className={css({ display: "grid", gap: theme.sizing.scale300, maxWidth: "480px" })}>
            {liveKey ? (
              <div className={css({ display: "flex", gap: theme.sizing.scale400, alignItems: "center", flexWrap: "wrap" })}>
                <Chip kind="green" testId="live-on">{say.liveOn}</Chip>
                <Button kind={KIND.secondary} size={SIZE.compact} onClick={() => setKey(null)} data-testid="live-forget">
                  {say.liveForget}
                </Button>
              </div>
            ) : (
              <div className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", flexWrap: "wrap" })}>
                <div className={css({ flex: "1 1 240px" })}>
                  <Input
                    type="password"
                    value={draftKey}
                    onChange={(e) => setDraftKey((e.target as HTMLInputElement).value)}
                    placeholder={say.livePlaceholder}
                    size="compact"
                    overrides={{ Input: { props: { "data-testid": "live-key", autoComplete: "off", spellCheck: false } } }}
                  />
                </div>
                <Button
                  size={SIZE.compact}
                  disabled={!draftKey.trim().startsWith("sk-ant-")}
                  onClick={() => {
                    setKey(draftKey);
                    setDraftKey("");
                  }}
                  data-testid="live-use"
                >
                  {say.liveUse}
                </Button>
              </div>
            )}
            <Muted>{say.liveNote}</Muted>
          </div>
        </Section>
      )}

      <Section title={say.receipts} hint={say.receiptsHint} testId="settings-receipts">
        <VerifyRecord site={key} />
      </Section>

      {mine && (
        <Section title={say.remove} testId="settings-remove">
          <div className={css({ display: "grid", gap: theme.sizing.scale400 })}>
            <div className={css({ display: "flex", gap: theme.sizing.scale400, alignItems: "center", flexWrap: "wrap" })}>
              {site.archived_at ? (
                <Button kind={KIND.secondary} size={SIZE.compact} isLoading={busy === "restore"} onClick={() => void post("restore", `projects/${key}/restore`)} data-testid="restore-project">
                  {say.restore}
                </Button>
              ) : (
                <Button kind={KIND.secondary} size={SIZE.compact} isLoading={busy === "archive"} onClick={() => void post("archive", `projects/${key}/archive`, { why: say.archiveWhy })} data-testid="archive-project">
                  {say.archive}
                </Button>
              )}
              <Muted>{site.archived_at ? say.archivedOn(fmtLong(site.archived_at.slice(0, 10))) : say.archiveHint}</Muted>
            </div>
            {key !== DEMO_PROJECT ? (
              <div className={css({ display: "flex", gap: theme.sizing.scale400, alignItems: "center", flexWrap: "wrap" })}>
                <Button kind={KIND.secondary} size={SIZE.compact} onClick={() => setDeleting(true)} data-testid="delete-project"
                  overrides={{ BaseButton: { style: { color: theme.colors.contentNegative } } }}>
                  {say.delete}
                </Button>
                <Muted>{say.deleteHint}</Muted>
              </div>
            ) : (
              <Muted>{say.demoStays}</Muted>
            )}
          </div>
        </Section>
      )}

      <Modal isOpen={deleting} onClose={() => setDeleting(false)} closeable autoFocus>
        <ModalHeader>{say.deleteTitle(site.name)}</ModalHeader>
        <ModalBody>
          <ParagraphSmall>{say.deleteBody}</ParagraphSmall>
          <Input value={typed} onChange={(e) => setTyped((e.target as HTMLInputElement).value)} placeholder={say.typeKey(key)} overrides={{ Input: { props: { "data-testid": "delete-typed" } } }} />
        </ModalBody>
        <ModalFooter>
          <ModalButton kind={KIND.tertiary} onClick={() => setDeleting(false)}>
            {say.cancel}
          </ModalButton>
          <ModalButton
            disabled={typed.trim() !== key}
            isLoading={busy === "delete"}
            onClick={() => void post("delete", `projects/${key}/delete`, { typed }, () => { setDeleting(false); navigate("/"); })}
            data-testid="delete-confirm"
          >
            {say.deleteConfirm}
          </ModalButton>
        </ModalFooter>
      </Modal>
    </div>
  );
}
