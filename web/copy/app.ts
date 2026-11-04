// Words used across the app: the header and account menu, what shows when the app can't load,
// shared labels (allow / ask / deny, templates, dates), and the receipt check in a project's Settings.
// Edit freely. **Like this** makes text bold and `like this` shows as code.

export const app = {
  name: "Groundwork",

  // The hosted site is a demo; real projects run on your own computer.
  demo: {
    tag: "Demo",
    tagTip: "A demo with one made-up project. Real projects run on your own computer.",
    banner: `You're trying a demo with a made-up project, Lake Mariner. To use Groundwork on your own projects, [run it on your computer](https://github.com/jedwards27/groundwork#try-it-in-the-claude-app-the-plugin).`,
  },
  // On your own computer (the plugin): this copy is yours.
  yours: {
    tag: "On this computer",
    tagTip: "Your projects and their ledgers live on this computer. Lake Mariner is the demo.",
  },

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
    demo: "Demo",
    demoWithExpiry: (left: string) => `Demo (resets in ${left})`,
    // Your own Anthropic API key, for this browser tab only (the hosted demo and make dev).
    useKey: "Use your own API key",
    forgetKey: "Forget the API key",
    keyTitle: "Watch Claude plan, live",
    keyBody:
      "The demo plays a written plan, so no AI model runs. Add your own Anthropic API key and Claude plans the emails you play, billed to your key. The inbox then shows five more, including two with hidden instructions for AI. Claude also writes a second plan without the mandate, to measure what the mandate changes. That plan never runs. The tour's email keeps its written plan.",
    keyPrivacy: "The key stays in this tab's memory and goes with each Play. It's never saved; reloading the tab forgets it.",
    keyPlaceholder: "sk-ant-…",
    keyUse: "Use for this tab",
    keyCancel: "Cancel",
    keyOn: "Live",
    keyOnTip: "Claude plans the emails you play in this tab, with your API key.",
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
