"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/client";
import { Prov } from "./Tip";

interface Evidence {
  key: string;
  kind: string;
  title: string;
  party: string | null;
  data: Record<string, unknown>;
  provenance: string;
  source: string;
}

export function EvidenceDialog({ site, evidenceKey, onClose }: { site: string; evidenceKey: string | null; onClose: () => void }) {
  const q = useQuery({
    queryKey: ["evidence", site, evidenceKey],
    queryFn: () => get<Evidence>(`sites/${site}/evidence/${evidenceKey}`),
    enabled: !!evidenceKey,
  });
  const ev = q.data;
  return (
    <Dialog.Root open={!!evidenceKey} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="dialog" style={{ width: "min(760px, calc(100vw - 32px))" }} aria-describedby={undefined}>
          <Dialog.Title>{ev?.title ?? "Evidence"}</Dialog.Title>
          {ev && (
            <>
              <p className="small muted">
                {ev.kind.replace("_", " ")} · from {ev.party ?? "unknown"} · <Prov provenance={ev.provenance} source={ev.source} />
              </p>
              {typeof ev.data.text === "string" ? (
                <pre className="json" style={{ maxHeight: "60vh", color: "var(--fg)" }}>{ev.data.text}</pre>
              ) : (
                <pre className="json">{JSON.stringify(ev.data, null, 2)}</pre>
              )}
            </>
          )}
          {q.isError && <p className="bad">{String((q.error as Error).message)}</p>}
          <div className="actions">
            <Dialog.Close className="btn">Close</Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
