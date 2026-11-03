// Everything the home page says: Needs you, Projects and Activity, and the drawers they open.
// The tutorial card at the top is in tutorial.ts; the approve drawer's words are in project.ts.
// Edit freely. **Like this** makes text bold.

export const home = {
  needsYou: {
    title: "Needs you",
    titleWithCount: (n: number) => `Needs you · ${n}`,
    hint: "Asks wait for your approval; drafts are what Claude prepared and only you can make real.",
    empty: "Nothing needs you right now.",
    ask: "Ask",
    row: (project: string, when: string) => `${project} · ${when}`,
  },

  // What a draft from Claude is about, on its tag.
  draftKinds: { project: "New project", mandate: "Mandate", facts: "Dates", links: "Links", people: "People" } as Record<string, string>,

  projects: {
    title: "Projects",
    newProject: "New project",
    empty: "No projects yet. Ask Claude to start one from your email or a few sentences.",
    waitingOn: (what: string) => ` · waiting on ${what}`,
    tutorial: "Tutorial",
  },

  activity: {
    title: "Activity",
    hint: "When a message comes in, Groundwork plans what to do next. It does what your mandate allows, asks you about the rest, and refuses what's never allowed.",
    empty: "Nothing yet. When a message comes in, what Groundwork did about it shows here.",
    showAll: "Show all",
    showFewer: "Show fewer",
    // "Did 1 on its own, asked you about 1, refused 1", leaving out what's zero.
    did: (n: number) => `did ${n} on its own`,
    asked: (n: number) => `asked you about ${n}`,
    refused: (n: number) => `refused ${n}`,
    nothing: "nothing to do",
    row: (did: string, project: string, when: string) => `${did} · ${project} · ${when}`,
    mismatch: "Doesn't add up",
    mismatchTip: "Groundwork's own account of what it did doesn't match the ledger.",
  },

  ask: {
    details: "Details",
    route: "Route",
    project: "Project",
  },

  draft: {
    prepared: (kind: string, project: string, when: string) => `${kind} · ${project} · prepared by Claude ${when}`,
    confirm: "Confirm",
    reject: "Reject",
    footer: "Nothing changes until you confirm. Your confirmation is a record on the project's ledger.",
  },
};
