// Everything the home page says: Needs you, Projects and Activity, and the drawers they open.
// The tutorial card at the top is in tutorial.ts; the approve drawer's words are in project.ts.
// Edit freely. **Like this** makes text bold. House style is at the top of project.ts.

export const home = {
  needsYou: {
    title: "Needs you",
    titleWithCount: (n: number) => `Needs you (${n})`,
    hint: "Asks wait for your approval. Drafts are changes Claude prepared; only you can confirm them.",
    empty: "Nothing needs you.",
    ask: "Ask",
    row: (project: string, when: string) => `${project}, ${when}`,
    demo: "Demo",
    demoTip: "From the Lake Mariner demo, not one of your projects.",
  },

  // What a draft from Claude is about, on its tag.
  draftKinds: {
    project: "New project",
    mandate: "Mandate",
    facts: "Dates",
    links: "Links",
    people: "People",
    steps: "Steps",
    project_edit: "Project details",
    archive: "Archive",
    delete: "Delete",
  } as Record<string, string>,

  projects: {
    title: "Projects",
    newProject: "New project",
    empty: "No projects yet. Ask Claude to start one.",
    waitingOn: (what: string) => `, waiting on ${what}`,
    tutorial: "Tutorial",
  },

  archived: {
    title: (n: number) => `Archived (${n})`,
    hint: "Off home and out of mail routing. Nothing is deleted.",
    row: (when: string) => `Archived ${when}`,
  },

  activity: {
    title: "Activity",
    hint: "What Groundwork did with each message: allowed, asked or denied under your mandate.",
    empty: "No activity yet.",
    showAll: "Show all",
    showFewer: "Show fewer",
    // "Did 1 on its own, asked you about 1, refused 1", leaving out what's zero.
    did: (n: number) => `did ${n} on its own`,
    asked: (n: number) => `asked you about ${n}`,
    refused: (n: number) => `denied ${n}`,
    nothing: "nothing to do",
    row: (did: string, project: string, when: string) => `${project}, ${when}. ${did}.`,
    mismatch: "Report doesn't match",
    mismatchTip: "Groundwork's account of what it did doesn't match the ledger.",
  },

  ask: {
    details: "Details",
    route: "Route",
    project: "Project",
  },

  draft: {
    prepared: (kind: string, project: string, when: string) => `${kind} for ${project}, prepared by Claude ${when}`,
    confirm: "Confirm",
    deleteForGood: "Delete for good",
    reject: "Reject",
    typeToConfirm: (key: string) => `Type ${key} to delete it`,
    footer: "Nothing changes until you confirm. Your confirmation is recorded on the project's ledger.",
    footerDelete: "Nothing changes until you confirm.",
  },
};
