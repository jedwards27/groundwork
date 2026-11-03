// Approving is a typed action by a named person, bound to the action's exact content and the
// mandate version. The same buttons serve the home view and a project's Actions tab.
import { useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND } from "baseui/button";
import { toaster } from "baseui/toast";
import { useState } from "react";
import { send } from "@/lib/client";
import { project } from "@/copy/project";
import { Muted } from "./ui";

const say = project.approve;

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
      toaster.positive(verdict === "approve" ? (r.executed.length ? say.approvedAndRan : say.approved) : say.declined, {});
      onDone();
    } catch (e) {
      toaster.negative((e as Error).message, {});
    } finally {
      setBusy(false);
    }
  };
  if (!canApprove) return <Muted>{say.waitingFor(approvers)}</Muted>;
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale300 })}>
      <div className={css({ display: "flex", gap: theme.sizing.scale300 })}>
        <Button onClick={() => decide("approve")} isLoading={busy} data-testid="approve">
          {say.approve}
        </Button>
        <Button kind={KIND.secondary} onClick={() => decide("decline")} disabled={busy} data-testid="decline">
          {say.decline}
        </Button>
      </div>
      <Muted>{say.bound(version)}</Muted>
    </div>
  );
}
