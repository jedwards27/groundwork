// Approving is a typed action by a named person, bound to the action's exact content and the
// mandate version. The same buttons serve the home view and a project's Actions tab.
import { useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND } from "baseui/button";
import { toaster } from "baseui/toast";
import { useState } from "react";
import { send } from "@/lib/client";
import { Muted } from "./ui";

export function ApproveButtons({ actionId, version, canApprove, approvers, onDone }: {
  actionId: string;
  version: number | null;
  canApprove: boolean;
  approvers: string[];
  onDone: () => void;
}) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const decide = async (verdict: "approve" | "decline") => {
    setBusy(true);
    try {
      const r = await send<{ executed: string[] }>("POST", `actions/${actionId}/approvals`, { verdict, idempotency_key: crypto.randomUUID() });
      await qc.invalidateQueries();
      toaster.positive(verdict === "approve" ? (r.executed.length ? "Approved. It ran in dry run: recorded, not sent." : "Approved.") : "Declined.", {});
      onDone();
    } catch (e) {
      toaster.negative((e as Error).message, {});
    } finally {
      setBusy(false);
    }
  };
  if (!canApprove) return <Muted>Waiting for {approvers.join(" or ")}.</Muted>;
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale300 })}>
      <div className={css({ display: "flex", gap: theme.sizing.scale300 })}>
        <Button onClick={() => decide("approve")} isLoading={busy} data-testid="approve">
          Approve
        </Button>
        <Button kind={KIND.secondary} onClick={() => decide("decline")} disabled={busy} data-testid="decline">
          Decline
        </Button>
      </div>
      <Muted>
        Your approval is bound to this exact text{version ? ` and mandate v${version}` : ""}. Replies, forwards and auto-replies never approve
        anything.
      </Muted>
    </div>
  );
}
