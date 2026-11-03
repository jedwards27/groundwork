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
import { DEMO_PROJECT } from "@/lib/format";
import type { EventView, Session } from "@/lib/types";

const STORE = "gw-tutorial";
// Remembered for good once someone finishes, so home stops offering it.
const DONE = "gw-tutorial-done";
const P = `/projects/${DEMO_PROJECT}`;

interface Step {
  title: string;
  body: ReactNode;
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
  end?: boolean;
}

export const STEPS: Step[] = [
  {
    title: "Welcome to Groundwork",
    body: "You're Jordan, Anthropic's project manager for Lake Mariner. Groundwork keeps track of everything the project is waiting on, and acts on it inside rules you set.",
    route: "/",
    target: `project-${DEMO_PROJECT}`,
    click: { bubble: "Click Lake Mariner", cta: "Click Lake Mariner to open it." },
    doneAt: P,
  },
  {
    title: "When it'll be ready",
    body: "This is the date the data hall should be ready, and how late that is. \"Waiting on\" is the step holding the date up right now.",
    route: P,
    highlight: "summary",
    target: "gate",
    click: { bubble: "Click here", cta: "Click \"Waiting on\" to see what the date depends on.", below: true },
  },
  {
    title: "The path to the date",
    body: "These steps have to happen, in this order, for the data hall to be ready. Any delay to one of them moves the date. Everything else has some slack.",
    route: P,
    target: "path",
    inDrawer: true,
  },
  {
    title: "What depends on what",
    body: "Here is every step of the project on the calendar, with arrows for what waits on what. The blue ones decide the date. Next, see what happens when an email comes in.",
    route: P,
    highlight: "graph",
    target: "tab-inbox",
    click: { bubble: "Click Inbox", cta: "Click the Inbox tab." },
    doneAt: `${P}/inbox`,
  },
  {
    title: "An email arrives",
    body: "Fluidstack, which leases the building, forwarded an email from TeraWulf, the landlord: the utility wants to review the power settings again, which could push the date out.",
    route: `${P}/inbox`,
    target: "play-demo-monday",
    click: { bubble: "Click Play", cta: "Click Play to have the email arrive, as if it just landed." },
  },
  {
    title: "Groundwork works through it",
    body: "Groundwork reads the email, moves the forecast, plans what to do next and checks each step against your rules.",
    route: `${P}/inbox`,
    target: "see-actions",
    waiting: "Groundwork is working through the email. Watch the steps.",
    click: { bubble: "Click here", cta: "Done. Click See the 3 next steps." },
    doneAt: `${P}/actions`,
    inDrawer: true,
  },
  {
    title: "One email, three next steps",
    body: "From that one email, Groundwork planned three next steps: get this week's status from Fluidstack, have the landlord confirm the power-on date in writing, and sign the revised schedule the landlord asked for.",
    route: `${P}/actions`,
    target: "actions-list",
  },
  {
    title: "Your rules decided each one",
    body: (
      <>
        The AI proposed them; your rules, applied by plain code outside the AI, decided each one. <b>Allow:</b> a routine status check
        with Fluidstack went ahead on its own (in this demo it's recorded, not sent). <b>Ask:</b> anything that goes to the landlord waits
        for you. <b>Deny:</b> signing could commit Anthropic to new dates, so Groundwork never signs. That one is yours.
      </>
    ),
    route: `${P}/actions`,
    highlight: "actions-list",
    target: "action-a2",
    click: { bubble: "Click the Ask", cta: "Click the Ask to open it." },
  },
  {
    title: "Approve it",
    body: "This is exactly what would be sent, and the rule that says it needs you. Your approval is recorded with your name.",
    route: `${P}/actions`,
    target: "approve",
    click: { bubble: "Click Approve", cta: "Read it, then click Approve." },
    after: 800,
    inDrawer: true,
  },
  {
    title: "Where the rules live",
    body: "Approved. The rules that sent it to you are the project's mandate.",
    route: `${P}/actions`,
    target: "tab-mandate",
    click: { bubble: "Click Mandate", cta: "Click the Mandate tab to see them." },
    doneAt: `${P}/mandate`,
  },
  {
    title: "Your rules, in plain words",
    body: "What Groundwork may do on its own, must ask you about, and may never do. Templates run from Supervised, which asks about almost everything, to Auto. A preview changes nothing until you issue it.",
    route: `${P}/mandate`,
    highlight: "template",
    target: "tab-ledger",
    click: { bubble: "Then click Ledger", cta: "Try another template to preview it, then click the Ledger tab." },
    doneAt: `${P}/ledger`,
  },
  {
    title: "Everything is recorded",
    body: "Every step, including your approval, is recorded here, and each record is sealed to the one before it. If anyone edits a past record later, even with access to the database, this check fails.",
    route: `${P}/ledger`,
    highlight: "chain-ok",
    target: "home-link",
    click: { bubble: "Click Groundwork", cta: "Click Groundwork, top left, to go back home." },
    doneAt: "/",
    plays: "event-b",
  },
  {
    title: "Back home",
    body: "While you looked around, a second email came in: the building's main electrical equipment failed a factory test. Groundwork already did what your rules allow. What needs you waits here, and what it did is below.",
    route: "/",
    highlight: "needs-you",
  },
  {
    title: "Start your own project",
    body: "Groundwork works for anything that waits on other people: a remodel, a store opening, a grid connection.",
    route: "/",
    end: true,
  },
];

interface Saved {
  step: number;
  open: boolean;
  // The furthest step reached; going Back below it shows steps already done, with Next.
  max: number;
}

const Ctx = createContext<{ start: () => void; open: boolean; paused: number | null; done: boolean }>({
  start: () => undefined,
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
// there already. Something taller than that space starts just under the header.
function reveal(el: HTMLElement) {
  if (el.closest('[data-baseweb="drawer"]')) {
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    return;
  }
  const top = (document.querySelector("header")?.getBoundingClientRect().bottom ?? 0) + 16;
  const bottom = Math.max(top + 1, (find("tutorial")?.getBoundingClientRect().top ?? window.innerHeight) - 16);
  const r = el.getBoundingClientRect();
  if (r.top >= top && r.bottom <= bottom) return;
  const want = r.height > bottom - top || r.top < top ? top : bottom - r.height;
  window.scrollBy({ top: r.top - want, behavior: "smooth" });
}

function closeDrawers() {
  // Press each open drawer's own Close button, as you would.
  document.querySelectorAll<HTMLButtonElement>('[data-baseweb="drawer"] button[aria-label="Close"]').forEach((b) => b.click());
}

export function TutorialProvider({ session, children }: { session: Session; children: ReactNode }) {
  const [, theme] = useStyletron();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [state, setState] = useState<Saved | null>(load);
  const [done, setDone] = useState(loadDone);
  const [asking, setAsking] = useState(false);
  const [starting, setStarting] = useState(false);
  const fresh = !!session.health.sandboxes && !session.local;

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

  // Opening it again resumes a paused tutorial; otherwise it asks before starting the demo over.
  const start = useCallback(() => {
    if (state && !state.open) set({ ...state, open: true });
    else setAsking(true);
  }, [state, set]);

  const begin = async () => {
    setStarting(true);
    try {
      await send("POST", "demo/reset");
      await qc.invalidateQueries();
      setAsking(false);
      set({ step: 0, open: true, max: 0 });
      navigate("/");
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
        es.addEventListener("end", () => {
          es.close();
          void qc.invalidateQueries();
        });
      } catch {
        // The tour goes on without it; home just has less to show.
      }
    },
    [qc],
  );

  return (
    <Ctx.Provider value={{ start, open: !!state?.open, paused: state && !state.open ? state.step : null, done }}>
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
        <ModalHeader>Lake Mariner, in two minutes</ModalHeader>
        <ModalBody>
          <ParagraphSmall marginTop={0}>
            Anthropic is bringing a new data center online at Lake Mariner, in Barker, New York. TeraWulf owns the building, Fluidstack
            leases it and provides it to Anthropic, and NYSEG, the local utility, has to connect it to the grid.
          </ParagraphSmall>
          <ParagraphSmall>
            You're Jordan, Anthropic's project manager. When the data hall is ready depends on all of them, and Groundwork's job is to keep
            that date on track.
          </ParagraphSmall>
          <ParagraphSmall marginBottom={0} color={theme.colors.contentTertiary}>
            {fresh ? "You'll get a fresh copy of the demo." : "The demo starts over."} Your own projects stay as they are.
          </ParagraphSmall>
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
  // this step lives in it, then go to the step's page. A step seen before shows its own page.
  useEffect(() => {
    moved.current = false;
    setLost(false);
    if (!s.inDrawer) closeDrawers();
    if (here !== s.route && (review || !(s.doneAt && here === s.doneAt))) navigate(s.route);
    if (s.plays && !review) play(s.plays);
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reaching the step's goal page some other way also finishes it.
  useEffect(() => {
    if (!review && s.doneAt && here === s.doneAt) advance();
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
      Back
    </Button>
  );

  if (s.end)
    return (
      <Modal isOpen onClose={finish} closeable size="auto" overrides={{ Dialog: { style: { maxWidth: "720px", width: "calc(100vw - 32px)" } } }}>
        <ModalHeader>
          <span data-testid="tutorial-title">{s.title}</span>
        </ModalHeader>
        <ModalBody>
          <ParagraphSmall marginTop={0}>{s.body}</ParagraphSmall>
          <Finish local={local} done={finish} back={backLink} />
        </ModalBody>
      </Modal>
    );

  const count = `${step + 1} of ${STEPS.length}`;
  // Steps you've already done, and click steps with nothing to click, move on with Next.
  const needsClick = !!s.click && !review && !lost;
  const close = (
    <Button kind={KIND.tertiary} size={SIZE.mini} onClick={pause} aria-label="Close the tutorial" data-testid="tutorial-close">
      <Delete size={18} />
    </Button>
  );
  const cta = s.click && !review && (
    <LabelMedium color={theme.colors.contentAccent} data-testid="tutorial-cta">
      {lost ? "Can't find it on this page. Click Next to keep going." : !el && s.waiting ? s.waiting : s.click.cta}
    </LabelMedium>
  );
  const next = !needsClick && (
    <Button size={drawer ? SIZE.mini : SIZE.compact} onClick={() => advance()} data-testid="tutorial-next">
      Next
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
          aria-label="Tutorial"
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
            {count}
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
        aria-label="Tutorial"
        data-testid="tutorial"
        className={css({
          ...shell,
          bottom: theme.sizing.scale600,
          left: theme.sizing.scale600,
          right: theme.sizing.scale600,
          maxWidth: "380px",
          padding: theme.sizing.scale600,
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr)",
          gap: theme.sizing.scale300,
        })}
      >
        <div className={css({ display: "flex", alignItems: "center" })}>
          <LabelXSmall color={theme.colors.contentTertiary} data-testid="tutorial-count">
            Tutorial · {count}
          </LabelXSmall>
          <span className={css({ marginLeft: "auto" })}>{close}</span>
        </div>
        <LabelLarge data-testid="tutorial-title">{s.title}</LabelLarge>
        <ParagraphSmall margin={0}>{s.body}</ParagraphSmall>
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

function Finish({ local, done, back }: { local: boolean; done: () => void; back: ReactNode }) {
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
      <div className={css({ display: "flex", justifyContent: "space-between", "@media (min-width: 640px)": { gridColumn: "1 / span 2" } })}>
        {back}
        <Button kind={KIND.tertiary} size={SIZE.compact} onClick={done} data-testid="tutorial-done">
          Done
        </Button>
      </div>
    </div>
  );
}
