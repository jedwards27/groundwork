// The tutorial: a small panel that walks through the demo one feature at a time. Each step points at
// one thing on the page; you click it yourself and the step moves on, so you get around the app the way
// you would without it. Steps that only explain have Next, and Back steps through what you've seen.
// Closing it pauses it; opening it again picks up where you left off. Starting fresh restarts the demo,
// so every step finds what it expects.
import { useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND, SIZE } from "baseui/button";
import { Delete } from "baseui/icon";
import { Modal, ModalBody, ModalButton, ModalFooter, ModalHeader } from "baseui/modal";
import { toaster } from "baseui/toast";
import { LabelLarge, LabelMedium, LabelSmall, LabelXSmall, ParagraphSmall } from "baseui/typography";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { get, send, stream } from "@/lib/client";
import { tutorial as t } from "@/copy/tutorial";
import { DEMO_PROJECT } from "@/lib/format";
import type { EventView, Session } from "@/lib/types";
import { Rich } from "./ui";

const STORE = "gw-tutorial";
// Remembered for good once someone finishes, so home stops offering it.
const DONE = "gw-tutorial-done";
const P = `/projects/${DEMO_PROJECT}`;
// The message the tour plays, and the ones its inbox leaves out until the tour is over: a second
// telling of the same delay, the email the tour plays in the background later, the offer that follows
// it, and the two injection tests.
export const TOUR_MESSAGE = "demo-monday";
export const TOUR_HIDES = new Set(["event-a", "event-b", "event-b-expedite", "injection-expedite-po", "injection-date-change"]);

interface Step {
  title: string;
  body: string;
  route: string;
  // What the step outlines (defaults to `target`).
  highlight?: string;
  // What the step points at: the thing to click on a click step.
  target?: string;
  // A click step: the bubble beside the target, and the call to action in the panel.
  click?: { bubble: string; cta: string; below?: boolean };
  // What to say while the target is still on its way, as when a run is working.
  waiting?: string;
  // A step can also finish by reaching this page another way.
  doneAt?: string;
  // How long to let the click's own result show before moving on (ms).
  after?: number;
  // The step happens inside a drawer the previous step opened; other steps close drawers first.
  inDrawer?: boolean;
  // Reaching this step plays this message in the background, so a later page has something new on it.
  plays?: string;
  // Skip ahead to the plan if the tour's message was already played (say, before the tour began),
  // since there's nothing left to click here.
  skipIfPlayed?: boolean;
  end?: boolean;
}

const say = t.steps;
const click = (c: { bubble: string; cta: string }, below?: boolean) => ({ bubble: c.bubble, cta: c.cta, below });

// The words live in web/copy/tutorial.ts; this is where each step points and what finishes it.
export const STEPS: Step[] = [
  { ...say.welcome, route: "/", target: `project-${DEMO_PROJECT}`, click: click(say.welcome), doneAt: P },
  { ...say.date, route: P, highlight: "summary", target: "gate", click: click(say.date, true) },
  { ...say.path, route: P, target: "path", inDrawer: true },
  { ...say.graph, route: P, target: "graph" },
  { ...say.inbox, route: P, target: "tab-inbox", click: click(say.inbox), doneAt: `${P}/inbox` },
  { ...say.email, route: `${P}/inbox`, target: "play-demo-monday", click: click(say.email), skipIfPlayed: true },
  {
    ...say.run,
    route: `${P}/inbox`,
    target: "see-actions",
    click: click(say.run),
    doneAt: `${P}/actions`,
    inDrawer: true,
  },
  { ...say.plan, route: `${P}/actions`, target: "actions-list" },
  { ...say.rules, route: `${P}/actions`, highlight: "actions-list", target: "action-a2", click: click(say.rules) },
  { ...say.approve, route: `${P}/actions`, target: "approve", click: click(say.approve), after: 800, inDrawer: true },
  { ...say.mandateTab, route: `${P}/actions`, target: "tab-settings", click: click(say.mandateTab), doneAt: `${P}/settings` },
  { ...say.mandate, route: `${P}/settings`, highlight: "template", target: "tab-ledger", click: click(say.mandate), doneAt: `${P}/ledger` },
  {
    ...say.ledger,
    route: `${P}/ledger`,
    highlight: "chain-ok",
    target: "home-link",
    click: click(say.ledger),
    doneAt: "/",
    plays: "event-b",
  },
  { ...say.home, route: "/", highlight: "needs-you" },
  { ...say.end, route: "/", end: true },
];

interface Saved {
  step: number;
  open: boolean;
  // The furthest step reached; going Back below it shows steps already done, with Next.
  max: number;
}

const Ctx = createContext<{ start: () => void; restart: () => void; open: boolean; paused: number | null; done: boolean }>({
  start: () => undefined,
  restart: () => undefined,
  open: false,
  paused: null,
  done: false,
});

export function useTutorial() {
  return useContext(Ctx);
}

function load(): Saved | null {
  try {
    const raw = window.sessionStorage.getItem(STORE);
    if (!raw) return null;
    const saved = JSON.parse(raw) as Saved;
    return { ...saved, max: saved.max ?? saved.step };
  } catch {
    return null;
  }
}

function save(s: Saved | null) {
  try {
    if (s === null) window.sessionStorage.removeItem(STORE);
    else window.sessionStorage.setItem(STORE, JSON.stringify(s));
  } catch {
    // Private windows can refuse storage; the tutorial still works, it just forgets on reload.
  }
}

function loadDone(): boolean {
  try {
    return window.localStorage.getItem(DONE) === "1";
  } catch {
    return false;
  }
}

function saveDone() {
  try {
    window.localStorage.setItem(DONE, "1");
  } catch {
    // As above: without storage, home keeps offering the tutorial.
  }
}

function find(testId: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
}

// Scroll so `el` sits in the open space between the header and the tutorial's panel, if it isn't
// there already. Something taller than that space starts just under the header. The jump is
// instant, so what you're about to click is where it will stay.
function reveal(el: HTMLElement) {
  if (el.closest('[data-baseweb="drawer"]')) {
    el.scrollIntoView({ block: "center" });
    return;
  }
  const top = (document.querySelector("header")?.getBoundingClientRect().bottom ?? 0) + 16;
  const bottom = Math.max(top + 1, (find("tutorial")?.getBoundingClientRect().top ?? window.innerHeight) - 16);
  const r = el.getBoundingClientRect();
  if (r.top >= top && r.bottom <= bottom) return;
  const want = r.height > bottom - top || r.top < top ? top : bottom - r.height;
  window.scrollBy({ top: r.top - want });
}

function closeDrawers() {
  // Press each open drawer's own Close button, as you would.
  document.querySelectorAll<HTMLButtonElement>('[data-baseweb="drawer"] button[aria-label="Close"]').forEach((b) => b.click());
}

export function TutorialProvider({ session, children }: { session: Session; children: ReactNode }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [state, setState] = useState<Saved | null>(load);
  const [done, setDone] = useState(loadDone);
  const [asking, setAsking] = useState(false);
  const [starting, setStarting] = useState(false);

  const set = useCallback((s: Saved | null) => {
    setState(s);
    save(s);
  }, []);
  const go = useCallback((n: number) => {
    if (n === STEPS.length - 1) {
      saveDone();
      setDone(true);
    }
    setState((prev) => {
      const next = { step: n, open: true, max: Math.max(prev?.max ?? 0, n) };
      save(next);
      return next;
    });
  }, []);

  // Opening it again resumes a paused tutorial at the furthest step reached; otherwise it asks
  // before starting the demo over. Starting over closes the panel while it asks.
  const start = useCallback(() => {
    if (state && !state.open) set({ step: state.max, open: true, max: state.max });
    else setAsking(true);
  }, [state, set]);
  const restart = useCallback(() => {
    if (state?.open) set({ ...state, open: false });
    setAsking(true);
  }, [state, set]);

  const begin = async () => {
    setStarting(true);
    try {
      await send("POST", "demo/reset");
      await qc.invalidateQueries();
      setAsking(false);
      // Home first: the first step finishes on reaching Lake Mariner, so it mustn't start there.
      navigate("/");
      set({ step: 0, open: true, max: 0 });
    } catch (e) {
      toaster.negative((e as Error).message, {});
    } finally {
      setStarting(false);
    }
  };

  // A message the tutorial plays in the background, once: the views refresh when its run ends.
  const playInBackground = useCallback(
    async (event: string) => {
      try {
        const events = await get<EventView[]>(`sites/${DEMO_PROJECT}/events`);
        if (events.find((e) => e.key === event)?.status === "applied") return;
        const { run_id } = await send<{ run_id: string }>("POST", `sites/${DEMO_PROJECT}/events`, { event });
        const es = stream(`runs/${run_id}/stream`);
        // Refresh everything but the ledger, so the count you're reading doesn't jump under you.
        es.addEventListener("end", () => {
          es.close();
          void qc.invalidateQueries({ predicate: (q) => !["ledger", "verify", "attestation"].includes(String(q.queryKey[0])) });
        });
      } catch {
        // The tour goes on without it; home just has less to show.
      }
    },
    [qc],
  );

  return (
    <Ctx.Provider value={{ start, restart, open: !!state?.open, paused: state && !state.open ? state.max : null, done }}>
      {children}
      {state?.open && (
        <Panel
          step={state.step}
          review={state.step < state.max}
          local={session.local}
          go={go}
          play={playInBackground}
          pause={() => set({ ...state, open: false })}
          finish={() => set(null)}
        />
      )}
      <Modal isOpen={asking} onClose={() => setAsking(false)} closeable>
        <ModalHeader>{t.start.title}</ModalHeader>
        <ModalBody>
          {t.start.paragraphs.map((text, n) => (
            <ParagraphSmall key={n} marginTop={n ? undefined : 0} marginBottom={n === t.start.paragraphs.length - 1 ? 0 : undefined}>
              <Rich text={text} />
            </ParagraphSmall>
          ))}
        </ModalBody>
        <ModalFooter>
          <ModalButton kind={KIND.tertiary} onClick={() => setAsking(false)}>
            {t.start.cancel}
          </ModalButton>
          <ModalButton onClick={begin} isLoading={starting} data-testid="tutorial-begin">
            {t.start.begin}
          </ModalButton>
        </ModalFooter>
      </Modal>
    </Ctx.Provider>
  );
}

function Panel({ step, review, local, go, play, pause, finish }: {
  step: number;
  review: boolean;
  local: boolean;
  go: (n: number) => void;
  play: (event: string) => void;
  pause: () => void;
  finish: () => void;
}) {
  const [css, theme] = useStyletron();
  const navigate = useNavigate();
  const location = useLocation();
  const s = STEPS[Math.min(step, STEPS.length - 1)];
  const here = location.pathname + location.search;
  const [el, setEl] = useState<HTMLElement | null>(null);
  const [lost, setLost] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const moved = useRef(false);
  const away = useRef(false);

  const advance = useCallback(
    (delay = 0) => {
      if (moved.current) return;
      moved.current = true;
      setTimeout(() => go(step + 1), delay);
    },
    [go, step],
  );
  // Back skips a step that lived in a drawer, since the drawer is closed by then; it goes to the step
  // that opened it.
  const back = useCallback(() => {
    let n = step - 1;
    while (n > 0 && STEPS[n].inDrawer) n -= 1;
    go(n);
  }, [go, step]);

  // Room below the page, so nothing has to stay hidden behind the panel.
  useEffect(() => {
    document.body.style.paddingBottom = "360px";
    return () => {
      document.body.style.paddingBottom = "";
    };
  }, []);

  // Entering a step (or opening the tutorial again): close what the last step left open, unless
  // this step lives in it, then go to the step's page.
  useEffect(() => {
    moved.current = false;
    away.current = false;
    setLost(false);
    if (!s.inDrawer) closeDrawers();
    if (here !== s.route) navigate(s.route);
    if (s.plays && !review) play(s.plays);
    if (s.skipIfPlayed && !review) {
      const ahead = STEPS.findIndex((x) => x.target === "actions-list");
      void get<EventView[]>(`sites/${DEMO_PROJECT}/events`)
        .then((events) => {
          if (events.find((e) => e.key === TOUR_MESSAGE)?.status === "applied") go(ahead);
        })
        .catch(() => undefined);
    }
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  // Arriving at the step's goal page some other way also finishes it. Arriving, not being there:
  // a step that starts on its goal page (the page hasn't caught up yet) waits until you come back.
  useEffect(() => {
    if (review || !s.doneAt) return;
    if (here !== s.doneAt) away.current = true;
    else if (away.current) advance();
  }, [here, s.doneAt, review, advance]);

  // Keep pointing at the target, and outlining what the step is about, as the page changes.
  useEffect(() => {
    const target = s.target;
    const outline = s.highlight ?? s.target;
    let lit: HTMLElement | null = null;
    // Bring the step into view once: what to click if it's there, otherwise what the step is about,
    // and then what to click once it shows up (a run's last button, say).
    let shown: "none" | "outline" | "target" = "none";
    const started = Date.now();
    const tick = () => {
      const open = !!document.querySelector('[data-baseweb="drawer"]');
      setDrawer(open);
      const found = target ? find(target) : null;
      setEl((prev) => (prev === found ? prev : found));
      const toLight = outline ? find(outline) : null;
      if (toLight !== lit) {
        lit?.removeAttribute("data-tour");
        lit = toLight;
        toLight?.setAttribute("data-tour", "on");
      }
      // Something in the header is always in view.
      const clickable = s.click && !review && found && !found.closest("header") ? found : null;
      if (clickable && shown !== "target") {
        shown = "target";
        reveal(clickable);
      } else if (toLight && shown === "none") {
        shown = "outline";
        reveal(toLight);
      }
      // A click step whose target never shows up (already done, or you went elsewhere) offers Next
      // instead, so it can't strand you. One that waits on a run waits while the run is in view.
      setLost(!!s.click && !!target && !found && !(s.waiting && open) && Date.now() - started > 3000);
    };
    tick();
    const timer = setInterval(tick, 250);
    return () => {
      clearInterval(timer);
      lit?.removeAttribute("data-tour");
    };
  }, [step, review, s.target, s.highlight, s.click, s.waiting]);

  // A click on the target finishes a click step, after the app has done what the click does.
  useEffect(() => {
    if (!s.click || !s.target) return;
    const target = s.target;
    const onClick = (ev: MouseEvent) => {
      if ((ev.target as Element | null)?.closest(`[data-testid="${target}"]`)) advance(s.after ?? 150);
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [step, s.click, s.target, s.after, advance]);

  const backLink = step > 0 && (
    <Button kind={KIND.tertiary} size={SIZE.mini} onClick={back} data-testid="tutorial-back">
      {t.panel.back}
    </Button>
  );

  if (s.end)
    return (
      <Modal isOpen onClose={finish} closeable size="auto" overrides={{ Dialog: { style: { maxWidth: "560px", width: "calc(100vw - 32px)" } } }}>
        <ModalHeader>
          <span data-testid="tutorial-title">{s.title}</span>
        </ModalHeader>
        <ModalBody>
          <ParagraphSmall marginTop={0}>
            <Rich text={s.body} />
          </ParagraphSmall>
          <Finish local={local} done={finish} back={backLink} />
        </ModalBody>
      </Modal>
    );

  const n = step + 1;
  // Steps you've already done, and click steps with nothing to click, move on with Next.
  const needsClick = !!s.click && !review && !lost;
  const close = (
    <Button kind={KIND.tertiary} size={SIZE.mini} onClick={pause} aria-label={t.panel.close} data-testid="tutorial-close">
      <Delete size={18} />
    </Button>
  );
  const cta = s.click && !review && (
    <LabelMedium color={theme.colors.contentAccent} data-testid="tutorial-cta">
      {lost ? t.panel.lost : !el && s.waiting ? s.waiting : s.click.cta}
    </LabelMedium>
  );
  const next = !needsClick && (
    <Button size={drawer ? SIZE.mini : SIZE.compact} onClick={() => advance()} data-testid="tutorial-next">
      {t.panel.next}
    </Button>
  );
  const pointer = needsClick && el && s.click && <Pointer el={el} text={s.click.bubble} below={s.click.below} />;
  const shell = {
    position: "fixed" as const,
    zIndex: 20,
    background: theme.colors.backgroundPrimary,
    color: theme.colors.contentPrimary,
    borderRadius: theme.borders.radius400,
    boxShadow: theme.lighting.shadow700,
    border: `1px solid ${theme.colors.borderOpaque}`,
  };

  // With a drawer open the panel shrinks to one line, so it never covers what the drawer shows.
  if (drawer)
    return (
      <>
        {pointer}
        <aside
          aria-label={t.panel.label}
          data-testid="tutorial"
          className={css({
            ...shell,
            bottom: theme.sizing.scale400,
            left: theme.sizing.scale400,
            right: theme.sizing.scale400,
            maxWidth: "560px",
            padding: `${theme.sizing.scale300} ${theme.sizing.scale500}`,
            display: "flex",
            alignItems: "center",
            gap: theme.sizing.scale300,
          })}
        >
          <LabelXSmall color={theme.colors.contentTertiary} data-testid="tutorial-count" $style={{ whiteSpace: "nowrap" }}>
            {t.panel.shortCount(n, STEPS.length)}
          </LabelXSmall>
          <div className={css({ flex: "1 1 auto", minWidth: 0 })}>
            {cta || <LabelSmall data-testid="tutorial-title">{s.title}</LabelSmall>}
          </div>
          {backLink}
          {next}
          {close}
        </aside>
      </>
    );

  return (
    <>
      {pointer}
      <aside
        aria-label={t.panel.label}
        data-testid="tutorial"
        className={css({
          ...shell,
          bottom: theme.sizing.scale600,
          left: theme.sizing.scale600,
          right: theme.sizing.scale600,
          maxWidth: "380px",
          // At most half the window, so what it points at always has room above it; the text scrolls.
          maxHeight: "50vh",
          padding: theme.sizing.scale600,
          display: "flex",
          flexDirection: "column",
          gap: theme.sizing.scale300,
        })}
      >
        <div className={css({ display: "flex", alignItems: "center" })}>
          <LabelXSmall color={theme.colors.contentTertiary} data-testid="tutorial-count">
            {t.panel.count(n, STEPS.length)}
          </LabelXSmall>
          <span className={css({ marginLeft: "auto" })}>{close}</span>
        </div>
        <LabelLarge data-testid="tutorial-title">{s.title}</LabelLarge>
        <div className={css({ flex: "1 1 auto", minHeight: 0, overflowY: "auto" })}>
          <ParagraphSmall margin={0}>
            <Rich text={s.body} />
          </ParagraphSmall>
        </div>
        {cta}
        {(backLink || next) && (
          <div className={css({ display: "flex", alignItems: "center", justifyContent: "space-between" })}>
            <span>{backLink}</span>
            {next}
          </div>
        )}
      </aside>
    </>
  );
}

// The "click here" bubble beside the thing to click.
function Pointer({ el, text, below }: { el: HTMLElement; text: string; below?: boolean }) {
  const [css, theme] = useStyletron();
  const [rect, setRect] = useState(() => el.getBoundingClientRect());
  useEffect(() => {
    const update = () => setRect(el.getBoundingClientRect());
    update();
    const timer = setInterval(update, 150);
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      clearInterval(timer);
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [el]);
  if (!rect.width && !rect.height) return null;
  const above = !below && rect.top > 56;
  const left = Math.min(Math.max(8, rect.left + 8), window.innerWidth - 180);
  return (
    <div
      role="status"
      data-testid="tutorial-pointer"
      className={css({
        position: "fixed",
        zIndex: 30,
        pointerEvents: "none",
        top: above ? `${rect.top - 40}px` : `${rect.bottom + 10}px`,
        left: `${left}px`,
        background: theme.colors.backgroundInversePrimary,
        color: theme.colors.contentInversePrimary,
        borderRadius: theme.borders.radius300,
        padding: `${theme.sizing.scale200} ${theme.sizing.scale400}`,
        boxShadow: theme.lighting.shadow500,
        whiteSpace: "nowrap",
        ...theme.typography.LabelSmall,
        "::after": {
          content: '""',
          position: "absolute",
          left: "16px",
          [above ? "bottom" : "top"]: "-6px",
          borderLeft: "6px solid transparent",
          borderRight: "6px solid transparent",
          [above ? "borderTop" : "borderBottom"]: `6px solid ${theme.colors.backgroundInversePrimary}`,
        },
      })}
    >
      {text}
    </div>
  );
}

// The end of the tour: start a project of your own, or keep exploring the demo.
function Finish({ local, done, back }: { local: boolean; done: () => void; back: ReactNode }) {
  const [css, theme] = useStyletron();
  const navigate = useNavigate();
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale500 })} data-testid="tutorial-finish">
      <div className={css({ display: "flex", gap: theme.sizing.scale300, flexWrap: "wrap" })}>
        <Button
          onClick={() => {
            done();
            navigate("/projects/new");
          }}
          data-testid="tutorial-new-project"
        >
          {t.finish.newProject}
        </Button>
        <Button kind={KIND.secondary} onClick={done} data-testid="tutorial-done">
          {t.finish.explore}
        </Button>
      </div>
      <ParagraphSmall margin={0} color={theme.colors.contentSecondary}>
        <Rich text={local ? t.finish.localNote : t.finish.hostedNote} />
      </ParagraphSmall>
      {back && <div>{back}</div>}
    </div>
  );
}
