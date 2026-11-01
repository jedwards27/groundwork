"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { local } from "@/lib/client";
import type { Session } from "@/lib/types";

export function PersonaDialog({ session, open, onOpenChange }: { session: Session; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [err, setErr] = useState("");
  const choose = async (person: string) => {
    setErr("");
    try {
      await local("/api/session", "POST", { person });
      await qc.invalidateQueries();
      onOpenChange(false);
    } catch (e) {
      setErr(String((e as Error).message));
    }
  };
  const disabled = session.health && !session.health.demo_login;
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="dialog" aria-describedby="persona-desc">
          <Dialog.Title>Act as a demo persona</Dialog.Title>
          <p id="persona-desc" className="muted small">
            These are fictional people seeded with the Lake Mariner fixture. Anyone with access to this app can act as
            any of them; approvals are recorded under the persona&apos;s name. A real deployment uses the
            organization&apos;s sign-in instead.
            {session.health?.sandboxes &&
              " Here you get your own copy of the demo: nobody else sees what you do, and switching persona keeps your copy."}
          </p>
          {disabled ? (
            <p className="banner crit">Demo login is off. Set GROUNDWORK_DEMO_LOGIN=true in .env and restart the API.</p>
          ) : (
            <div style={{ display: "grid", gap: 8 }}>
              {session.personas.map((p) => (
                <button key={p.key} className="persona" onClick={() => choose(p.key)}>
                  <b>{p.name}</b>
                  <span className="mono dim">{p.approver ? "approver" : ""}</span>
                  <span className="t">
                    {p.title} · {p.party}
                  </span>
                </button>
              ))}
            </div>
          )}
          {err && <p className="bad small">{err}</p>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
