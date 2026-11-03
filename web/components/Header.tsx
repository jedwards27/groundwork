import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { ChevronDown } from "baseui/icon";
import { StatefulMenu } from "baseui/menu";
import { PLACEMENT, StatefulPopover } from "baseui/popover";
import { toaster } from "baseui/toast";
import { LabelLarge, LabelMedium } from "baseui/typography";
import { Link, useMatch, useNavigate } from "react-router";
import { get, send } from "@/lib/client";
import { DEMO_PROJECT } from "@/lib/format";
import type { Session, SiteView } from "@/lib/types";
import { Chip } from "./ui";

type Item = { id: string; label: string; disabled?: boolean };

function hoursLeft(iso: string): string {
  const h = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000));
  return h <= 1 ? "under an hour" : `${h} hours`;
}

export function Header({ session }: { session: Session }) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const match = useMatch("/projects/:key/*");
  const key = match?.params.key;
  const site = useQuery({ queryKey: ["site", key], queryFn: () => get<SiteView>(`sites/${key}`), enabled: !!key });
  const h = session.health;
  const you = session.you;
  const where = session.local ? "this computer" : "this server";

  const items: Item[] = [
    { id: "who", label: you ? (you.demo_lead ? `${you.name} · you, in the demo` : `${you.name} · on this computer`) : "", disabled: true },
    { id: "verify", label: "Verify a receipt" },
  ];
  if (h.sandboxes && !session.local) items.push({ id: "reset", label: "Start over with a fresh copy" });
  else if (you?.approver || session.local) items.push({ id: "reset", label: "Reset the demo project" });
  if (!h.hosted) items.push({ id: "tamper", label: "Tamper with one demo record" });

  const act = async (id: string) => {
    try {
      if (id === "verify") navigate("/verify");
      if (id === "reset") {
        await send("POST", "demo/reset");
        await qc.invalidateQueries();
        toaster.positive("The demo project starts over.", {});
      }
      if (id === "tamper") {
        const r = await send<{ edited_seq: number }>("POST", "demo/tamper");
        await qc.invalidateQueries();
        toaster.warning(
          `Record #${r.edited_seq} was edited with database owner credentials. The ledger tab now shows the chain broken; reset the demo to restore it.`,
          {},
        );
        navigate(`/projects/${DEMO_PROJECT}/ledger`);
      }
    } catch (e) {
      toaster.negative((e as Error).message, {});
    }
  };

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
          <LabelLarge $style={{ fontWeight: 700 }}>Groundwork</LabelLarge>
        </Link>
        {key && site.data && (
          <LabelMedium color={theme.colors.contentTertiary} className={css({ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "none", "@media (min-width: 640px)": { display: "block" } })}>
            / {site.data.name}
          </LabelMedium>
        )}
        <div className={css({ marginLeft: "auto", display: "flex", alignItems: "center", gap: theme.sizing.scale300 })}>
          <span className={css({ display: "none", gap: theme.sizing.scale300, "@media (min-width: 640px)": { display: "flex" } })}>
            {h.dry_run && (
              <Chip tip={`Allowed actions are recorded, not sent. Nothing leaves ${where}.`} testId="dry-run">
                Dry run
              </Chip>
            )}
            {!session.local &&
              (h.live_planner ? (
                <Chip kind="blue" tip={`Plans come from ${h.planner_model}. Project data goes only to Anthropic's API, with email addresses removed.`} testId="planner">
                  Live planner
                </Chip>
              ) : (
                <Chip tip="No API key here, so messages play hand-written plans and the demo runs the same way every time. The gateway, the ledger and the report check are live code." testId="planner">
                  Simulated planner
                </Chip>
              ))}
            {you?.sandbox_expires_at && (
              <Chip tip={`Your own copy of the demo. Nobody else sees it, and it's deleted in ${hoursLeft(you.sandbox_expires_at)}.`} testId="sandbox">
                Private copy
              </Chip>
            )}
          </span>
          <StatefulPopover
            placement={PLACEMENT.bottomRight}
            content={({ close }) => (
              <StatefulMenu
                items={items}
                onItemSelect={({ item }) => {
                  close();
                  void act((item as Item).id);
                }}
                overrides={{ List: { style: { minWidth: "240px" }, props: { "data-testid": "you-menu" } } }}
              />
            )}
          >
            <Button kind={KIND.tertiary} size={SIZE.compact} endEnhancer={() => <ChevronDown size={18} />} data-testid="you">
              You
            </Button>
          </StatefulPopover>
        </div>
      </div>
    </header>
  );
}
