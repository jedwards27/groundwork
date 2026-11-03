// Everything the tutorial says: the card on home, the start dialog, each step, and the end.
// Edit freely. **Like this** makes text bold. In each step, `cta` is the instruction in the panel
// and `bubble` is the short label that points at the thing to click.

export const tutorial = {
  card: {
    title: "New here? Take the two-minute tutorial",
    body: "See how Groundwork keeps a project's date on track, using the Lake Mariner demo.",
    start: "Start the tutorial",
    pausedTitle: "Pick up the tutorial",
    pausedBody: (step: number, total: number) => `You stopped at step ${step} of ${total}.`,
    resume: "Resume",
  },

  menu: {
    take: "Take the tutorial",
    resume: (step: number, total: number) => `Resume the tutorial (${step} of ${total})`,
    restart: "Start the tutorial over",
  },

  // The button beside the date on the Lake Mariner page.
  projectButton: "Tutorial",

  start: {
    title: "Lake Mariner, in two minutes",
    paragraphs: [
      "Anthropic is bringing a new data center online at Lake Mariner, in Barker, New York. TeraWulf owns the building, Fluidstack leases it and provides it to Anthropic, and NYSEG, the local utility, has to connect it to the grid.",
      "You're Jordan, Anthropic's project manager. Each of them has to deliver before the data center can open, and Groundwork's job is to keep that date on track.",
    ],
    cancel: "Not now",
    begin: "Start",
  },

  panel: {
    count: (step: number, total: number) => `Tutorial · ${step} of ${total}`,
    shortCount: (step: number, total: number) => `${step} of ${total}`,
    next: "Next",
    back: "Back",
    label: "Tutorial",
    close: "Close the tutorial",
    lost: "Can't find it on this page. Click Next to keep going.",
  },

  steps: {
    welcome: {
      title: "Welcome to Groundwork",
      body: "You're Jordan, Anthropic's project manager for Lake Mariner. Groundwork keeps track of everything the project is waiting on, and acts on it inside rules you set.",
      bubble: "Click Lake Mariner",
      cta: "Click Lake Mariner to open it.",
    },
    date: {
      title: "When it'll be ready",
      body: 'This is the date the data center should be ready, and how late that is. "Waiting on" is the step holding the date up right now.',
      bubble: "Click here",
      cta: 'Click "Waiting on" to see what the date depends on.',
    },
    path: {
      title: "The path to the date",
      body: "These steps have to happen, in this order, for the data center to be ready. Any delay to one of them moves the date. Everything else has some slack.",
    },
    graph: {
      title: "What depends on what",
      body: "Here is every step of the project on the calendar, with arrows for what waits on what. The blue ones decide the date; amber is the one it waits on now.",
    },
    inbox: {
      title: "The inbox",
      body: "Emails about the project land in its inbox. Next, see what Groundwork does when one comes in.",
      bubble: "Click Inbox",
      cta: "Click the Inbox tab.",
    },
    email: {
      title: "An email arrives",
      body: "Fluidstack, which leases the building, forwarded an email from TeraWulf, the landlord: the utility wants to review the power settings again, which could push the date out.",
      bubble: "Click Play",
      cta: "Click Play to have the email arrive, as if it just landed.",
    },
    run: {
      title: "Groundwork works through it",
      body: "Groundwork reads the email, moves the forecast, plans what to do next and checks each step against your rules.",
      waiting: "Groundwork is working through the email. Watch each step.",
      bubble: "Click here",
      cta: "Done. Click See the 3 next steps.",
    },
    plan: {
      title: "One email, three next steps",
      body: "From that one email, Groundwork planned three next steps: get this week's status from Fluidstack, have the landlord confirm the power-on date in writing, and sign the revised schedule the landlord asked for.",
    },
    rules: {
      title: "Your rules decided each one",
      body: "The AI proposes; your rules decide. They're called the mandate, and they're enforced outside the AI, so it can't talk its way past them. **Allow:** a routine status check with Fluidstack went ahead on its own. **Ask:** anything that goes to the landlord waits for you. **Deny:** signing could commit Anthropic to new dates, so Groundwork never signs. That one is yours.",
      bubble: "Click the Ask",
      cta: "Click the Ask to open it.",
    },
    approve: {
      title: "Approve it",
      body: "At the top is exactly what would go out, and below it, why it needs you. Your approval is recorded with your name.",
      bubble: "Click Approve",
      cta: "Read it, then click Approve.",
    },
    mandateTab: {
      title: "Where the rules live",
      body: "Approved. Next, the mandate itself.",
      bubble: "Click Mandate",
      cta: "Click the Mandate tab.",
    },
    mandate: {
      title: "Your rules, in plain words",
      body: "What Groundwork may do on its own, must ask you about, and may never do. Templates run from Supervised, which asks about almost everything, to Auto. Pick one to preview what it would change; nothing changes until you issue it.",
      bubble: "Then click Ledger",
      cta: "Try another template to preview it, then click the Ledger tab.",
    },
    ledger: {
      title: "Everything is recorded",
      body: "Every step, including your approval, is recorded here, and each record is sealed to the one before it. If anyone edits a past record later, even with access to the database, this check fails.",
      bubble: "Click Groundwork",
      cta: "Click Groundwork, top left, to go back home.",
    },
    home: {
      title: "Back home",
      body: "While you looked around, a second email came in: the building's main electrical equipment failed a factory test. Groundwork already did what your rules allow. What needs you waits here, and Activity, below, shows what it did.",
    },
    end: {
      title: "That's the whole tour!",
      body: "You've seen Groundwork read an email, plan what to do, check each step against your rules, wait for your approval and record it all.",
    },
  },

  finish: {
    newProject: "Start your own project",
    explore: "Keep exploring the demo",
    // Shown under the buttons: on your own computer (the plugin), or on the hosted demo.
    localNote: "Or, in Claude, run /groundwork:new-project and describe the project. Claude drafts it; you confirm it here.",
    hostedNote:
      "Want a project's data to stay on your own computer? Install the Groundwork plugin in the Claude app: it runs everything on your laptop. Then run /groundwork:new-project.",
  },
};
