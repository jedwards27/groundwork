import { useQuery } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ChevronDown } from "baseui/icon";
import { Input } from "baseui/input";
import { StatefulMenu } from "baseui/menu";
import { Modal, ModalBody, ModalButton, ModalFooter, ModalHeader } from "baseui/modal";
import { useState } from "react";
import { PLACEMENT, StatefulPopover } from "baseui/popover";
import { LabelLarge, LabelMedium, LabelSmall, ParagraphXSmall } from "baseui/typography";
import { Link, useMatch, useNavigate } from "react-router";
import { get } from "@/lib/client";
import { setKey, useKey } from "@/lib/key";
import { DEMO_PROJECT } from "@/lib/format";
import type { Session, SiteView } from "@/lib/types";
import { app } from "@/copy/app";
import { tutorial as t } from "@/copy/tutorial";
import { STEPS, useTutorial } from "./Tutorial";
import { Chip } from "./ui";

type Item = { id: string; label: string };

function hoursLeft(iso: string): string {
  const h = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000));
  return h <= 1 ? app.account.underAnHour : app.account.hours(h);
}

// The header holds the product, where you are, and you. Status lives where it applies, not here.
export function Header({ session }: { session: Session }) {
  const [css, theme] = useStyletron();
  const navigate = useNavigate();
  const tutorial = useTutorial();
  const match = useMatch("/projects/:key/*");
  const key = match?.params.key && match.params.key !== "new" ? match.params.key : undefined;
  const site = useQuery({ queryKey: ["site", key], queryFn: () => get<SiteView>(`sites/${key}`), enabled: !!key });
  const you = session.you;
  // Your own API key is for the demo and make dev; on your computer, Claude in the app plans.
  const liveKey = useKey();
  const keyable = !session.local;
  const [asking, setAsking] = useState(false);
  const [draft, setDraft] = useState("");
  const name = you?.name ?? app.account.fallbackName;
  const about = session.local
    ? you?.email || app.account.onThisComputer
    : you?.sandbox_expires_at
      ? app.account.demoWithExpiry(hoursLeft(you.sandbox_expires_at))
      : app.account.demo;

  // Open: start over (which closes the panel first). Paused: resume or start over. Otherwise: take it.
  const items: Item[] = tutorial.open
    ? [{ id: "restart", label: t.menu.restart }]
    : tutorial.paused !== null
      ? [
          { id: "resume", label: t.menu.resume(tutorial.paused + 1, STEPS.length) },
          { id: "restart", label: t.menu.restart },
        ]
      : [{ id: "resume", label: t.menu.take }];

  const allItems: Item[] = [
    ...items,
    ...(keyable ? [liveKey ? { id: "forget-key", label: app.account.forgetKey } : { id: "use-key", label: app.account.useKey }] : []),
  ];

  const act = (id: string) => {
    if (id === "resume") tutorial.start();
    if (id === "restart") tutorial.restart();
    if (id === "use-key") setAsking(true);
    if (id === "forget-key") setKey(null);
  };

  const avatar = css({
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    background: theme.colors.backgroundInversePrimary,
    color: theme.colors.contentInversePrimary,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    ...theme.typography.LabelSmall,
  });

  return (
    <header
      className={css({
        position: "sticky",
        top: 0,
        zIndex: 2,
        background: theme.colors.backgroundPrimary,
        borderBottom: `1px solid ${theme.colors.borderOpaque}`,
      })}
    >
      <div
        className={css({
          maxWidth: "1040px",
          margin: "0 auto",
          padding: `0 ${theme.sizing.scale600}`,
          height: "56px",
          display: "flex",
          alignItems: "center",
          gap: theme.sizing.scale400,
        })}
      >
        <Link to="/" className={css({ textDecoration: "none", color: "inherit" })} data-testid="home-link">
          <LabelLarge $style={{ fontWeight: 700 }}>{app.name}</LabelLarge>
        </Link>
        {/* Which copy this is: the public demo, or yours on this computer. */}
        {session.health.hosted ? (
          <Chip kind="yellow" tip={app.demo.tagTip} testId="demo-tag">{app.demo.tag}</Chip>
        ) : session.local ? (
          <Chip kind="gray" tip={app.yours.tagTip} testId="yours-tag">{app.yours.tag}</Chip>
        ) : null}
        {session.local && key === DEMO_PROJECT && you?.demo_as && (
          <Chip kind="gray" tip={app.yours.actsAsTip(you.demo_as)} testId="acts-as-tag">{app.yours.actsAs(you.demo_as)}</Chip>
        )}
        {key && site.data && (
          <LabelMedium color={theme.colors.contentTertiary} className={css({ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "none", "@media (min-width: 640px)": { display: "block" } })}>
            / {site.data.name}
          </LabelMedium>
        )}
        <div className={css({ marginLeft: "auto", display: "flex", alignItems: "center", gap: theme.sizing.scale300 })}>
          {liveKey && <Chip kind="green" tip={app.account.keyOnTip} testId="live-tag">{app.account.keyOn}</Chip>}
          <StatefulPopover
            placement={PLACEMENT.bottomRight}
            // One surface: the name block and the menu share a background, corners and border.
            overrides={{
              Body: { style: { borderRadius: theme.borders.radius400, overflow: "hidden", backgroundColor: theme.colors.backgroundPrimary, border: `1px solid ${theme.colors.borderOpaque}` } },
              Inner: { style: { backgroundColor: theme.colors.backgroundPrimary, borderRadius: theme.borders.radius400 } },
            }}
            content={({ close }) => (
              <div className={css({ minWidth: "260px" })} data-testid="account-menu">
                <div className={css({ display: "flex", gap: theme.sizing.scale400, alignItems: "center", padding: `${theme.sizing.scale500} ${theme.sizing.scale600}`, borderBottom: `1px solid ${theme.colors.borderOpaque}` })}>
                  <span className={avatar}>{name.slice(0, 1).toUpperCase()}</span>
                  <div>
                    <LabelSmall>{name}</LabelSmall>
                    <ParagraphXSmall margin={0} color={theme.colors.contentTertiary}>
                      {about}
                    </ParagraphXSmall>
                  </div>
                </div>
                <StatefulMenu
                  items={allItems}
                  onItemSelect={({ item }) => {
                    close();
                    act((item as Item).id);
                  }}
                  overrides={{ List: { style: { boxShadow: "none", outline: "none", borderRadius: 0, backgroundColor: "transparent", paddingTop: theme.sizing.scale200, paddingBottom: theme.sizing.scale200 } } }}
                />
              </div>
            )}
          >
            <Button kind={KIND.tertiary} size={SIZE.compact} endEnhancer={() => <ChevronDown size={18} />} data-testid="you">
              <span className={css({ display: "inline-flex", gap: theme.sizing.scale300, alignItems: "center" })}>
                <span className={avatar}>{name.slice(0, 1).toUpperCase()}</span>
                <span className={css({ display: "none", "@media (min-width: 480px)": { display: "inline" } })}>{name}</span>
              </span>
            </Button>
          </StatefulPopover>
        </div>
      </div>
      <Modal isOpen={asking} onClose={() => setAsking(false)} closeable autoFocus>
        <ModalHeader>{app.account.keyTitle}</ModalHeader>
        <ModalBody>
          <ParagraphXSmall marginTop={0}>{app.account.keyBody}</ParagraphXSmall>
          <Input
            type="password"
            value={draft}
            onChange={(e) => setDraft((e.target as HTMLInputElement).value)}
            placeholder={app.account.keyPlaceholder}
            overrides={{ Input: { props: { "data-testid": "live-key", autoComplete: "off", spellCheck: false } } }}
          />
          <ParagraphXSmall marginBottom={0} color={theme.colors.contentTertiary}>{app.account.keyPrivacy}</ParagraphXSmall>
        </ModalBody>
        <ModalFooter>
          <ModalButton kind={KIND.tertiary} onClick={() => setAsking(false)}>
            {app.account.keyCancel}
          </ModalButton>
          <ModalButton
            disabled={!draft.trim().startsWith("sk-ant-")}
            onClick={() => {
              setKey(draft);
              setDraft("");
              setAsking(false);
            }}
            data-testid="live-use"
          >
            {app.account.keyUse}
          </ModalButton>
        </ModalFooter>
      </Modal>
    </header>
  );
}
