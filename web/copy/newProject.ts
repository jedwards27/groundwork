// Everything the New project form says, including the example it can fill in.
// Edit freely. **Like this** makes text bold.

export const newProject = {
  title: "New project",
  fillExample: "Fill in an example",
  intro: "Anything that waits on other organizations: a remodel, a store opening, a grid connection.",
  whereItLives: {
    local: "It's yours, on this computer.",
    hosted:
      "In this demo it lives in your private copy and is deleted with it. For a real project, run Groundwork on your own computer, so its data stays there.",
  },

  project: {
    title: "Project",
    name: "Name",
    namePlaceholder: "Kitchen remodel",
    where: "Where (optional)",
    wherePlaceholder: "Oakland, CA",
    finishedMeans: "Finished means",
    finishedMeansCaption: "The moment that matters, in your words.",
    finishedMeansPlaceholder: "Kitchen usable",
    date: "Promised or hoped-for date",
  },

  parties: {
    title: "Organizations",
    hint: "Each organization that owes you something. A contact's email routes their mail here.",
    organization: "Organization",
    role: "Role",
    contact: "Contact (optional)",
    email: "Email (optional)",
    remove: "Remove",
    add: "Add an organization",
    roles: {
      contractor: "Contractor",
      vendor: "Vendor or supplier",
      ahj: "Permit office",
      agency: "Inspector or utility",
      landlord: "Landlord",
      designer: "Designer or architect",
      consultant: "Consultant",
      lender: "Lender",
      regulator: "Regulator",
      developer: "Developer",
      operator: "Operator",
      community: "Community group",
    },
  },

  steps: {
    title: "Steps",
    hint: "Each step, who owes it, when it's due and what it waits on. Groundwork works out what sets the date.",
    step: "Step",
    stepPlaceholder: "Building permit issued",
    owner: "Who owes it",
    you: "You",
    status: "Status",
    due: "Due",
    waitsOn: "Waits on (optional)",
    add: "Add a step",
    finishing: "Which step means it's finished?",
    finishingLabel: "Finishing step",
    numbered: (n: number) => `Step ${n}`,
    statuses: { not_started: "Not started", in_progress: "Under way", done: "Done", cancelled: "Cancelled" },
    paste: {
      title: "Paste steps from a spreadsheet",
      hint: "One step per row. Columns: step, who owes it, status, due date, and the steps it waits on (separated by ;). A header row is skipped; new owners become organizations.",
      placeholder: "Building permit issued\tCity permits\tunder way\t2026-12-01\nCabinets installed\tBayside Builders\tnot started\t2027-01-20\tBuilding permit issued",
      add: "Add these steps",
      added: (n: number, skipped: number) => `Added ${n} ${n === 1 ? "step" : "steps"}${skipped ? `; skipped ${skipped} ${skipped === 1 ? "row" : "rows"} missing a step name or a readable date` : ""}.`,
    },
  },

  more: {
    title: "Options",
    template: "Mandate template",
    templateCaption: "Supervised asks you before anything goes out. You can widen it later.",
    asOf: "The project's date",
    asOfCaption: "Today, or an earlier date to replay a past project.",
    yourName: "Your name",
    yourNameCaption: "Shown as the project's approver.",
    yourNamePlaceholder: "You",
  },

  errors: {
    name: "Give the project a name.",
    date: "Say when it's meant to finish.",
    steps: "Every step needs a description and a date.",
  },

  preview: {
    forecast: (finish: string) => `Forecast: ${finish}`,
    waitingOn: (what: string) => `Waiting on: ${what}`,
  },

  check: "Check the forecast",
  create: "Create the project",
  cancel: "Cancel",
  defaults: { yourName: "You", finished: "Finished" },

  // "Fill in an example": a kitchen remodel whose cabinets arrive weeks after they were meant to go
  // in, so the forecast opens late, waiting on the supplier. Dates are days from today.
  example: {
    name: "Kitchen remodel",
    location: "Oakland, CA",
    finishLabel: "Kitchen usable",
    contractor: "Bayside Builders",
    contractorContact: "Bob Ruiz",
    contractorEmail: "bob@bayside.example",
    permitOffice: "Oakland Planning & Building",
    supplier: "Cabinet supplier",
    permit: "Building permit issued",
    delivered: "Cabinets delivered",
    installed: "Cabinets installed",
    countertops: "Countertops installed",
    inspection: "Final inspection passed",
  },
};
