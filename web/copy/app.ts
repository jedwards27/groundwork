// Words used across the app: the header and account menu, what shows when the app can't load,
// shared labels (allow / ask / deny, templates, dates), and the receipt check in a project's Settings.
// Edit freely. **Like this** makes text bold and `like this` shows as code.

export const app = {
  name: "Groundwork",

  shell: {
    unreachableTitle: "Groundwork isn't reachable",
    unreachableBody: "Start it with `make api` (or open it from Claude), then reload.",
    openFromClaudeTitle: "Open Groundwork from Claude",
    notSignedInTitle: "Not signed in",
    notSignedInBody:
      "Ask Claude for your Groundwork link (the pending tool gives it). The link opens this app signed in as you, on this computer only.",
    notFound: "Nothing here.",
  },

  account: {
    fallbackName: "You",
    onThisComputer: "On this computer",
    demo: "Demo account",
    demoWithExpiry: (left: string) => `Demo account (deleted in ${left})`,
    underAnHour: "under an hour",
    hours: (h: number) => `${h} hours`,
  },

  // The gateway's three decisions, in the product's words.
  decision: { auto: "allow", ask: "ask", refuse: "deny" } as Record<string, string>,
  template: { supervised: "Supervised", standard: "Standard", autonomous: "Auto" } as Record<string, string>,
  provenance: { public: "public", synthetic: "synthetic", assumption_to_verify: "assumption to verify" } as Record<string, string>,

  time: {
    justNow: "just now",
    minutesAgo: (m: number) => `${m} min ago`,
    hoursAgo: (h: number) => `${h} h ago`,
  },
  lateness: {
    late: (d: number) => `${d} days late`,
    early: (d: number) => `${d} days early`,
    onTime: "on time",
  },

  common: {
    more: "More",
    less: "Less",
    showAll: (n: number) => `Show all ${n}`,
    showFewer: "Show fewer",
    loading: "Loading…",
    previous: "Previous",
    next: "Next",
    of: "of",
    showing: (from: number, to: number, total: number) => `${from} to ${to} of ${total}`,
    nothingHere: "Nothing here.",
  },

  verify: {
    title: "Verify a receipt",
    intro: "Every proposal, decision, approval and outcome is a hash-chained record. Check one, or a copy someone sent you.",
    project: "Project",
    record: "Record",
    recordOption: (seq: number, type: string, ref?: string, title?: string) =>
      `#${seq} ${type}${ref ? ` (${ref})` : ""}${title ? `: ${title}` : ""}`,
    paste: "Or paste a copy of a record (JSON)",
    pasteCaption: "For example from a receipt someone sent you. Leave it empty to recompute the stored record.",
    notJson: "The pasted copy is not valid JSON.",
    chooseRecord: "Choose a record first.",
    run: "Verify",
    pasteStored: "Paste the stored record",
    clear: "Clear",
    match: "Match",
    mismatch: "Mismatch",
    matchBody: "The record hashes to what the ledger holds, and every record before it links to the one after.",
    mismatchBody:
      "Something differs from what was recorded. The ledger is append-only, so a mismatch means the copy or the stored record was changed.",
    recordLine: (seq: number | undefined, type: string | undefined, version: number | null | undefined) =>
      `#${seq} ${type}, ${version ? `issued under mandate v${version}` : "not tied to a mandate decision"}`,
    storedHash: "Stored hash",
    yourCopy: "Your copy",
  },
};
