"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { get, local, send } from "@/lib/client";
import { time } from "@/lib/format";
import type { ChainView, CompareRow, EventView, MandateView, PlanView, RunView, Session, SiteView, Step } from "@/lib/types";
import { Chain } from "./Chain";
import { Dial } from "./Dial";
import { EvidenceDialog } from "./EvidenceDialog";
import { Facts } from "./Facts";
import { Header } from "./Header";
import { Hero } from "./Hero";
import { Inbox, type RunState } from "./Inbox";
import { PersonaDialog } from "./PersonaDialog";
import { PlanPanel } from "./PlanPanel";
import { Roadmap } from "./Roadmap";
import { AttestationPanel, LedgerPanel, Scorecard } from "./Trust";

export function MissionControl({ site }: { site: string }) {
  const qc = useQueryClient();
  const session = useQuery({ queryKey: ["session"], queryFn: () => local<Session>("/api/session") });
  const me = session.data?.me ?? null;
  const enabled = !!me;
  const siteQ = useQuery({ queryKey: ["site", site], queryFn: () => get<SiteView>(`sites/${site}`), enabled });
  const chain = useQuery({ queryKey: ["chain", site], queryFn: () => get<ChainView>(`sites/${site}/chain`), enabled });
  const events = useQuery({ queryKey: ["events", site], queryFn: () => get<EventView[]>(`sites/${site}/events`), enabled });
  const plan = useQuery({ queryKey: ["plan", site], queryFn: () => get<PlanView | null>(`sites/${site}/latest-plan`), enabled });
  const mandate = useQuery({ queryKey: ["mandate", site], queryFn: () => get<MandateView>(`sites/${site}/mandate`), enabled });
  const compare = useQuery({
    queryKey: ["compare", site],
    queryFn: () => get<{ presets: CompareRow[] }>(`sites/${site}/mandate/compare`),
    enabled,
  });
  const [personaOpen, setPersonaOpen] = useState(false);
  const [evidence, setEvidence] = useState<string | null>(null);
  const [run, setRun] = useState<RunState | null>(null);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState("");
  const source = useRef<EventSource | null>(null);
  const replayTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (session.data && !session.data.me) setPersonaOpen(true);
  }, [session.data]);
  useEffect(() => () => { source.current?.close(); if (replayTimer.current) clearTimeout(replayTimer.current); }, []);

  const refresh = useCallback(() => qc.invalidateQueries(), [qc]);

  const play = async (eventKey: string) => {
    setError("");
    try {
      const { run_id } = await send<{ run_id: string }>("POST", `sites/${site}/events`, { event: eventKey });
      setRun({ id: run_id, event: eventKey, status: "running", steps: [] });
      source.current?.close();
      const es = new EventSource(`/api/gw/runs/${run_id}/stream`);
      source.current = es;
      es.addEventListener("step", (m) => {
        const step = JSON.parse((m as MessageEvent).data) as Step;
        setRun((r) => (r && r.id === run_id ? { ...r, steps: [...r.steps.filter((s) => s.i !== step.i), step] } : r));
        if (["forecast", "executed", "differential"].includes(step.kind)) void refresh();
      });
      es.addEventListener("end", (m) => {
        const rv = JSON.parse((m as MessageEvent).data) as RunView;
        setRun((r) => (r && r.id === run_id ? { ...r, status: rv.status === "failed" ? "failed" : "done" } : r));
        es.close();
        void refresh();
        // The blind arm trails the run; pick up its scorecard rows shortly after.
        setTimeout(() => void qc.invalidateQueries({ queryKey: ["scorecard"] }), 4000);
      });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const replay = async () => {
    if (!run) return;
    const rv = await get<RunView>(`runs/${run.id}`);
    const steps = ((rv.summary?.steps as Step[] | undefined) ?? []).filter((s) => !s.kind.startsWith("blind"));
    const at = steps.length ? time(steps[0].at) : "";
    let n = 0;
    setRun({ ...run, replay: at, status: "running", steps: [] });
    const tick = () => {
      n += 1;
      setRun((r) => (r ? { ...r, steps: steps.slice(0, n) } : r));
      if (n < steps.length) replayTimer.current = setTimeout(tick, 650);
      else setRun((r) => (r ? { ...r, status: "done", replay: undefined } : r));
    };
    replayTimer.current = setTimeout(tick, 300);
  };

  const reset = async () => {
    setResetting(true);
    setError("");
    try {
      await local("/api/admin/reset", "POST");
      setRun(null);
      await local("/api/session", "POST", { person: me?.person ?? "dana" });
      await refresh();
    } catch (e) {
      setError(`Reset failed: ${(e as Error).message}`);
    } finally {
      setResetting(false);
    }
  };

  if (session.isLoading) return <p className="muted" style={{ padding: 24 }}>Loading…</p>;
  if (session.data?.error || !session.data)
    return (
      <p className="banner crit" style={{ marginTop: 24 }}>
        The Groundwork API is not reachable at the configured address. Start it with <code>make api</code>, then reload.
      </p>
    );
  if (!me)
    return (
      <>
        <p className="muted" style={{ padding: 24 }}>Choose a demo persona to continue.</p>
        <PersonaDialog session={session.data} open={personaOpen} onOpenChange={setPersonaOpen} />
      </>
    );

  const health = session.data.health;
  const p = plan.data ?? null;
  return (
    <>
      <Header site={siteQ.data} me={me} health={health} plan={p} onPersona={() => setPersonaOpen(true)} onReset={reset} resetting={resetting} />
      {health?.hosted && (
        <p className="banner info">Hosted demo: synthetic and public Lake Mariner fixtures only. Personas are shared; anyone with the link can act as them.</p>
      )}
      {health?.live_planner && (
        <p className="banner info small">
          Live planner on: project data for this site leaves this machine only to Anthropic&apos;s API, with email addresses
          removed (docs/DATA-BOUNDARY.md).
        </p>
      )}
      {error && <p className="banner crit">{error}</p>}
      {chain.data && siteQ.data ? (
        <Hero chain={chain.data} site={siteQ.data} plan={p} onEvidence={setEvidence} />
      ) : (
        <p className="muted" style={{ padding: 16 }}>Loading the paper chain…</p>
      )}
      <section className="grid">
        <div className="col left">
          {siteQ.data && <Facts site={siteQ.data} />}
          {mandate.data && <Dial site={site} mandate={mandate.data} compare={compare.data?.presets ?? []} me={me} />}
        </div>
        <div className="col mid">
          {chain.data && <Chain chain={chain.data} />}
          {siteQ.data && <PlanPanel plan={p} site={siteQ.data} me={me} chain={chain.data} />}
        </div>
        <div className="col right">
          {events.data && siteQ.data && <Inbox events={events.data} site={siteQ.data} run={run} onPlay={play} onReplay={replay} />}
          <Scorecard site={site} />
          <LedgerPanel site={site} hosted={!!health?.hosted} />
          <AttestationPanel site={site} />
        </div>
      </section>
      <Roadmap />
      <PersonaDialog session={session.data} open={personaOpen} onOpenChange={setPersonaOpen} />
      <EvidenceDialog site={site} evidenceKey={evidence} onClose={() => setEvidence(null)} />
    </>
  );
}
