// The tutorial: a small panel that walks through the demo one feature at a time. Each step opens
// the right screen and points at what to look at; "Do it for me" presses the same button you would.
// It starts from a fresh copy of the demo project, so every step finds what it expects.
import { useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { Delete } from "baseui/icon";
import { Modal, ModalBody, ModalButton, ModalFooter, ModalHeader } from "baseui/modal";
import { toaster } from "baseui/toast";
import { LabelLarge, LabelXSmall, ParagraphSmall } from "baseui/typography";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { send } from "@/lib/client";
import { DEMO_PROJECT } from "@/lib/format";
import type { Session } from "@/lib/types";

const STORE = "gw-tutorial";
const P = `/projects/${DEMO_PROJECT}`;

interface Step {
  title: string;
  body: ReactNode;
  route: string;
  target?: string;
  // `stay`: the step's result is worth a look, so don't move on by yourself.
  act?: { label: string; target: string; wait?: number; stay?: boolean };
  end?: boolean;
}

function steps(): Step[] {
  return [
    {
      title: "Welcome to Groundwork",
      body: "Groundwork keeps projects moving when they wait on other companies. In this demo you're Dana at Anthropic, which is moving into a data center a landlord is building. Nothing here is ever sent.",
      route: "/",
      target: `project-${DEMO_PROJECT}`,
    },
    {
      title: "When it's ready, and what it waits on",
      body: "This is when the data hall will be ready, and the one thing that date waits on. Why shows where each delay came from.",
      route: P,
      target: "summary",
    },
    {
      title: "A message arrives",
      body: "Fluidstack, the tenant, forwards two things: the utility wants another review, and a vendor's change order hides an instruction for AI. Play it.",
      route: `${P}/inbox`,
      target: "play-demo-monday",
      act: { label: "Play it", target: "play-demo-monday" },
    },
    {
      title: "Groundwork makes a plan",
      body: "It moves the forecast and plans follow-ups. Then a gateway, plain code outside the AI, checks each one against your rules.",
      route: `${P}/inbox`,
      target: "steps",
      act: { label: "See the decisions", target: "see-actions", wait: 60 },
    },
    {
      title: "Allow, ask, deny",
      body: (
        <>
          <b>Allow:</b> a routine status request, recorded but not sent. <b>Ask:</b> anything to the landlord waits for you.{" "}
          <b>Deny:</b> signing is never allowed, whatever a document says.
        </>
      ),
      route: `${P}/actions`,
      target: "actions-list",
    },
    {
      title: "Try to fool it",
      body: "This auto-reply says \"approved, please proceed\". Play it: nothing changes. Only you can approve.",
      route: `${P}/inbox`,
      target: "play-ack-approved",
      act: { label: "Play it", target: "play-ack-approved", stay: true },
    },
    {
      title: "What needs you",
      body: "Your asks wait here. Open this one to see exactly what would be sent, then approve it.",
      route: "/",
      target: "ask-a2",
      act: { label: "Open it", target: "ask-a2", stay: true },
    },
    {
      title: "Your rules",
      body: "The mandate says what Groundwork may do on its own, must ask about, and may never do. Pick another template to preview the difference.",
      route: `${P}/mandate`,
      target: "template",
    },
    {
      title: "Everything is recorded",
      body: "Each step is a record, linked to the one before it. \"Verified\" means nothing has been changed.",
      route: `${P}/ledger`,
      target: "chain-ok",
    },
    {
      title: "Check a receipt",
      body: "Anyone can check a record against the ledger. Verify one and it matches. Change a word in a copy and it won't.",
      route: `/verify?project=${DEMO_PROJECT}`,
      target: "verify-run",
      act: { label: "Verify it", target: "verify-run", stay: true },
    },
    {
      title: "Start your own project",
      body: "Groundwork works for anything that waits on other organizations: a remodel, a store opening, a grid connection.",
      route: "/",
      end: true,
    },
  ];
}

const Ctx = createContext<{ start: () => void; active: boolean }>({ start: () => undefined, active: false });

export function useTutorial() {
  return useContext(Ctx);
}

function load(): number | null {
  try {
    const raw = window.sessionStorage.getItem(STORE);
    return raw === null ? null : Number(raw);
  } catch {
    return null;
  }
}

function save(step: number | null) {
  try {
    if (step === null) window.sessionStorage.removeItem(STORE);
    else window.sessionStorage.setItem(STORE, String(step));
  } catch {
    // Private windows can refuse storage; the tutorial still works, it just forgets on reload.
  }
}

function find(testId: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
}

async function waitFor(testId: string, seconds: number): Promise<HTMLElement | null> {
  for (let i = 0; i < seconds * 10; i += 1) {
    const el = find(testId);
    if (el) return el;
    await new Promise((r) => setTimeout(r, 100));
  }
  return null;
}

export function TutorialProvider({ session, children }: { session: Session; children: ReactNode }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [step, setStep] = useState<number | null>(load);
  const [asking, setAsking] = useState(false);
  const [starting, setStarting] = useState(false);
  const fresh = !!session.health.sandboxes && !session.local;

  const go = useCallback((n: number | null) => {
    setStep(n);
    save(n);
  }, []);

  const begin = async () => {
    setStarting(true);
    try {
      await send("POST", "demo/reset");
      await qc.invalidateQueries();
      setAsking(false);
      go(0);
      navigate("/");
    } catch (e) {
      toaster.negative((e as Error).message, {});
    } finally {
      setStarting(false);
    }
  };

  return (
    <Ctx.Provider value={{ start: () => setAsking(true), active: step !== null }}>
      {children}
      {step !== null && <Panel step={step} local={session.local} go={go} />}
      <Modal isOpen={asking} onClose={() => setAsking(false)} closeable>
        <ModalHeader>Take the tutorial</ModalHeader>
        <ModalBody>
          About two minutes, eleven steps. It {fresh ? "gives you a fresh copy of the demo" : "reloads the demo project"} first, so anything
          you did in Lake Mariner is cleared. Your own projects aren't touched.
        </ModalBody>
        <ModalFooter>
          <ModalButton kind={KIND.tertiary} onClick={() => setAsking(false)}>
            Not now
          </ModalButton>
          <ModalButton onClick={begin} isLoading={starting} data-testid="tutorial-begin">
            Start
          </ModalButton>
        </ModalFooter>
      </Modal>
    </Ctx.Provider>
  );
}

function Panel({ step, local, go }: { step: number; local: boolean; go: (n: number | null) => void }) {
  const [css, theme] = useStyletron();
  const navigate = useNavigate();
  const location = useLocation();
  const all = steps();
  const s = all[Math.min(step, all.length - 1)];
  const [busy, setBusy] = useState(false);
  const here = location.pathname + location.search;

  // Room below the page, so nothing has to stay hidden behind the panel.
  useEffect(() => {
    document.body.style.paddingBottom = "360px";
    return () => {
      document.body.style.paddingBottom = "";
    };
  }, []);

  // Open the step's screen, then point at its target once it has rendered.
  useEffect(() => {
    if (here !== s.route) navigate(s.route);
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!s.target) return;
    let el: HTMLElement | null = null;
    let cancelled = false;
    void waitFor(s.target, 8).then((found) => {
      if (cancelled || !found) return;
      el = found;
      el.setAttribute("data-tour", "on");
      // Bring it near the top, clear of the panel at the bottom; inside a drawer, just into view.
      if (found.closest('[data-baseweb="drawer"]')) found.scrollIntoView({ block: "nearest", behavior: "smooth" });
      else window.scrollTo({ top: Math.max(0, found.getBoundingClientRect().top + window.scrollY - 120), behavior: "smooth" });
    });
    return () => {
      cancelled = true;
      el?.removeAttribute("data-tour");
    };
  }, [step, here, s.target]);

  const act = async () => {
    if (!s.act) return;
    setBusy(true);
    const el = await waitFor(s.act.target, s.act.wait ?? 8);
    setBusy(false);
    if (!el) {
      toaster.info("That isn't on the screen yet. Try the step before, or press Next.", {});
      return;
    }
    el.click();
    if (!s.act.stay) go(step + 1);
  };

  if (s.end)
    return (
      <Modal isOpen onClose={() => go(null)} closeable size="auto" overrides={{ Dialog: { style: { maxWidth: "720px", width: "calc(100vw - 32px)" } } }}>
        <ModalHeader>
          <span data-testid="tutorial-title">{s.title}</span>
        </ModalHeader>
        <ModalBody>
          <ParagraphSmall marginTop={0}>{s.body}</ParagraphSmall>
          <Finish local={local} done={() => go(null)} />
        </ModalBody>
      </Modal>
    );

  return (
    <aside
      aria-label="Tutorial"
      data-testid="tutorial"
      className={css({
        position: "fixed",
        zIndex: 20,
        bottom: theme.sizing.scale600,
        left: theme.sizing.scale600,
        right: theme.sizing.scale600,
        maxWidth: "360px",
        background: theme.colors.backgroundPrimary,
        color: theme.colors.contentPrimary,
        borderRadius: theme.borders.radius400,
        boxShadow: theme.lighting.shadow700,
        border: `1px solid ${theme.colors.borderOpaque}`,
        padding: theme.sizing.scale600,
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr)",
        gap: theme.sizing.scale300,
      })}
    >
      <div className={css({ display: "flex", alignItems: "center" })}>
        <LabelXSmall color={theme.colors.contentTertiary} data-testid="tutorial-count">
          Tutorial · {step + 1} of {all.length}
        </LabelXSmall>
        <span className={css({ marginLeft: "auto" })}>
          <Button kind={KIND.tertiary} size={SIZE.mini} onClick={() => go(null)} aria-label="Close the tutorial" data-testid="tutorial-close">
            <Delete size={18} />
          </Button>
        </span>
      </div>
      <LabelLarge data-testid="tutorial-title">{s.title}</LabelLarge>
      <ParagraphSmall margin={0}>{s.body}</ParagraphSmall>
      <div className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", flexWrap: "wrap" })}>
        {s.act && (
          <Button kind={KIND.secondary} size={SIZE.compact} onClick={act} isLoading={busy} data-testid="tutorial-act">
            {s.act.label}
          </Button>
        )}
        <span className={css({ marginLeft: "auto", display: "flex", gap: theme.sizing.scale200 })}>
          {step > 0 && (
            <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => go(step - 1)} data-testid="tutorial-back">
              Back
            </Button>
          )}
          <Button size={SIZE.compact} onClick={() => go(step + 1)} data-testid="tutorial-next">
            Next
          </Button>
        </span>
      </div>
    </aside>
  );
}

function Finish({ local, done }: { local: boolean; done: () => void }) {
  const [css, theme] = useStyletron();
  const navigate = useNavigate();
  const card = css({
    border: `1px solid ${theme.colors.borderOpaque}`,
    borderRadius: theme.borders.radius300,
    padding: theme.sizing.scale500,
    display: "grid",
    gap: theme.sizing.scale200,
  });
  return (
    <div
      className={css({ display: "grid", gap: theme.sizing.scale400, gridTemplateColumns: "minmax(0, 1fr)", "@media (min-width: 640px)": { gridTemplateColumns: "1fr 1fr" } })}
      data-testid="tutorial-finish"
    >
      <div className={card}>
        <LabelXSmall>On this website</LabelXSmall>
        <ParagraphSmall margin={0} color={theme.colors.contentSecondary}>
          Fill in a short form: what you're waiting on, from whom, and by when. You'll see the forecast before you save it.
        </ParagraphSmall>
        <div>
          <Button
            size={SIZE.compact}
            onClick={() => {
              done();
              navigate("/projects/new");
            }}
            data-testid="tutorial-new-project"
          >
            Create a project here
          </Button>
        </div>
      </div>
      <div className={card}>
        <LabelXSmall>In the Claude app</LabelXSmall>
        <ParagraphSmall margin={0} color={theme.colors.contentSecondary}>
          {local
            ? "In Claude, run /groundwork:new-project and describe the project. Claude drafts it; you confirm it here."
            : "Install the Groundwork plugin, then run /groundwork:new-project. Claude reads your email and drafts the project; you confirm it."}
        </ParagraphSmall>
      </div>
      <div className={css({ "@media (min-width: 640px)": { gridColumn: "1 / span 2" } })}>
        <Button kind={KIND.tertiary} size={SIZE.compact} onClick={done} data-testid="tutorial-done">
          Done
        </Button>
      </div>
    </div>
  );
}
