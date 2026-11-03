// A project on the website: what finishing means and when, who you're waiting on, and what has to
// happen in what order. "Check the forecast" shows what Groundwork computes before anything is
// saved; "Create the project" makes it, as a project of its own with its own ledger.
import { useQueryClient } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Accordion, Panel } from "baseui/accordion";
import { Button, KIND, SIZE } from "baseui/button";
import { FormControl } from "baseui/form-control";
import { Delete } from "baseui/icon";
import { Input } from "baseui/input";
import { Select, type Value } from "baseui/select";
import { HeadingSmall, LabelMedium, ParagraphSmall } from "baseui/typography";
import { useState } from "react";
import { useNavigate } from "react-router";
import { ApiError, send } from "@/lib/client";
import { fmtLong, lateness, TEMPLATE_LABEL } from "@/lib/format";
import type { Session } from "@/lib/types";
import { Chip, Muted, Page, Section } from "./ui";

type Role = "contractor" | "designer" | "consultant" | "vendor" | "landlord" | "lender" | "ahj" | "agency" | "regulator" | "developer" | "operator" | "community";
type Status = "not_started" | "in_progress" | "done";

const ROLES: { id: Role; label: string }[] = [
  { id: "contractor", label: "Contractor" },
  { id: "vendor", label: "Vendor or supplier" },
  { id: "ahj", label: "Permit office" },
  { id: "agency", label: "Inspector or utility" },
  { id: "landlord", label: "Landlord" },
  { id: "designer", label: "Designer or architect" },
  { id: "consultant", label: "Consultant" },
  { id: "lender", label: "Lender" },
  { id: "regulator", label: "Regulator" },
  { id: "developer", label: "Developer" },
  { id: "operator", label: "Operator" },
  { id: "community", label: "Community group" },
];
const STATUSES: { id: Status; label: string }[] = [
  { id: "not_started", label: "Not started" },
  { id: "in_progress", label: "Under way" },
  { id: "done", label: "Done" },
];

interface PartyRow { name: string; role: Role; contact: string; email: string }
interface ItemRow { title: string; owner: string; status: Status; finish: string; after: string[] }
interface Form {
  name: string;
  location: string;
  finish_label: string;
  finish_target: string;
  finish_item: number;
  template: "supervised" | "standard" | "auto";
  as_of: string;
  your_name: string;
  parties: PartyRow[];
  items: ItemRow[];
}
interface Preview {
  project: string;
  forecast: string;
  days_late: number | null;
  sets_the_date: string | null;
  finish: string;
  target: string;
}

const today = () => new Date().toISOString().slice(0, 10);
const blank = (): Form => ({
  name: "",
  location: "",
  finish_label: "",
  finish_target: "",
  finish_item: -1,
  template: "supervised",
  as_of: today(),
  your_name: "",
  parties: [{ name: "", role: "contractor", contact: "", email: "" }],
  items: [{ title: "", owner: "", status: "not_started", finish: "", after: [] }],
});

function plus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

// A small example to start from: a kitchen remodel whose cabinets arrive weeks after they were
// meant to go in, so the forecast opens late, waiting on the supplier.
const example = (): Form => ({
  name: "Kitchen remodel",
  location: "Oakland, CA",
  finish_label: "Kitchen usable",
  finish_target: plus(85),
  finish_item: 4,
  template: "supervised",
  as_of: today(),
  your_name: "",
  parties: [
    { name: "Bayside Builders", role: "contractor", contact: "Bob Ruiz", email: "bob@bayside.example" },
    { name: "Oakland Planning & Building", role: "ahj", contact: "", email: "" },
    { name: "Cabinet supplier", role: "vendor", contact: "", email: "" },
  ],
  items: [
    { title: "Building permit issued", owner: "Oakland Planning & Building", status: "in_progress", finish: plus(28), after: [] },
    { title: "Cabinets delivered", owner: "Cabinet supplier", status: "not_started", finish: plus(92), after: [] },
    { title: "Cabinets installed", owner: "Bayside Builders", status: "not_started", finish: plus(70), after: ["Building permit issued", "Cabinets delivered"] },
    { title: "Countertops installed", owner: "Bayside Builders", status: "not_started", finish: plus(78), after: ["Cabinets installed"] },
    { title: "Final inspection passed", owner: "Oakland Planning & Building", status: "not_started", finish: plus(85), after: ["Countertops installed"] },
  ],
});

function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "x";
}

function unique(texts: string[]): string[] {
  const seen = new Map<string, number>();
  return texts.map((t) => {
    const base = slug(t);
    const n = (seen.get(base) ?? 0) + 1;
    seen.set(base, n);
    return n === 1 ? base : `${base}-${n}`;
  });
}

// The form in the shape the API takes (the same draft the plugin's Claude writes).
function draft(f: Form) {
  const partyKeys = unique(f.parties.map((p) => p.name)).map((k) => (k === "you" || k === "me" ? `${k}-2` : k));
  const partyKey = Object.fromEntries(f.parties.map((p, i) => [p.name, partyKeys[i]]));
  const itemKeys = unique(f.items.map((i) => i.title));
  const itemKey = Object.fromEntries(f.items.map((it, i) => [it.title, itemKeys[i]]));
  const finish = f.finish_item >= 0 && f.finish_item < f.items.length ? f.finish_item : f.items.length - 1;
  return {
    your_name: f.your_name || "You",
    draft: {
      name: f.name.trim(),
      location: f.location.trim(),
      as_of: f.as_of || null,
      finish_label: f.finish_label.trim() || "Finished",
      finish_item: itemKeys[finish],
      finish_target: f.finish_target,
      template: f.template,
      parties: f.parties
        .filter((p) => p.name.trim())
        .map((p, i) => ({
          key: partyKeys[i],
          name: p.name.trim(),
          role: p.role,
          people: p.contact.trim() || p.email.trim() ? [{ name: p.contact.trim() || p.name.trim(), email: p.email.trim() }] : [],
        })),
      items: f.items.map((it, i) => ({
        key: itemKeys[i],
        title: it.title.trim(),
        kind: "milestone",
        owner: it.owner && it.owner !== "you" ? (partyKey[it.owner] ?? "you") : "you",
        status: it.status,
        finish: it.finish,
        depends_on: it.after.map((t) => itemKey[t]).filter(Boolean),
      })),
    },
  };
}

function problems(e: unknown): string[] {
  if (e instanceof ApiError) {
    try {
      const parsed = JSON.parse(e.message) as unknown;
      if (Array.isArray(parsed)) return parsed.map((x) => (typeof x === "string" ? x : (x as { msg?: string }).msg ?? JSON.stringify(x)));
    } catch {
      // A plain message.
    }
    return [e.message];
  }
  return [(e as Error).message];
}

export function NewProject({ session }: { session: Session }) {
  const [css, theme] = useStyletron();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [f, setF] = useState<Form>(blank);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<Form>) => {
    setF((x) => ({ ...x, ...patch }));
    setPreview(null);
  };
  const setParty = (i: number, patch: Partial<PartyRow>) => set({ parties: f.parties.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const setItem = (i: number, patch: Partial<ItemRow>) => set({ items: f.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });
  const owners = [{ id: "you", label: "You" }, ...f.parties.filter((p) => p.name.trim()).map((p) => ({ id: p.name, label: p.name }))];
  const titles = f.items.map((it) => it.title).filter((t) => t.trim());
  const finishIndex = f.finish_item >= 0 && f.finish_item < f.items.length ? f.finish_item : f.items.length - 1;

  const check = (): string[] => {
    const out: string[] = [];
    if (!f.name.trim()) out.push("Give the project a name.");
    if (!f.finish_target) out.push("Say when it's meant to finish.");
    if (f.items.some((it) => !it.title.trim() || !it.finish)) out.push("Every step needs a description and a date.");
    return out;
  };

  const run = async (create: boolean) => {
    const missing = check();
    setErrors(missing);
    if (missing.length) return;
    setBusy(true);
    try {
      const body = draft(f);
      setPreview(await send<Preview>("POST", "projects/preview", body));
      if (create) {
        const r = await send<{ project: string }>("POST", "projects", body);
        await qc.invalidateQueries();
        navigate(`/projects/${r.project}`);
      }
    } catch (e) {
      setErrors(problems(e));
      setPreview(null);
    } finally {
      setBusy(false);
    }
  };

  const row = css({ display: "grid", gap: theme.sizing.scale300, gridTemplateColumns: "minmax(0, 1fr)", "@media (min-width: 720px)": { gridTemplateColumns: "2fr 1.4fr 1.2fr 1fr auto" } });
  const select = (options: { id: string; label: string }[], value: string, onChange: (v: string) => void, label: string, testId?: string) => (
    <Select
      size="compact"
      options={options}
      value={options.filter((o) => o.id === value) as Value}
      onChange={({ value: v }) => onChange(String(v[0]?.id ?? ""))}
      clearable={false}
      searchable={false}
      aria-label={label}
      placeholder={label}
      overrides={testId ? { Root: { props: { "data-testid": testId } } } : undefined}
    />
  );

  return (
    <Page>
      <div className={css({ display: "flex", alignItems: "center", gap: theme.sizing.scale400, flexWrap: "wrap" })}>
        <HeadingSmall margin={0}>New project</HeadingSmall>
        <span className={css({ marginLeft: "auto" })}>
          <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => { setF(example()); setPreview(null); setErrors([]); }} data-testid="use-example">
            Fill in an example
          </Button>
        </span>
      </div>
      <Muted>
        Anything that waits on other organizations: a remodel, a store opening, a grid connection.{" "}
        {session.local ? "It's yours, on this computer." : "In this demo it lives in your private copy and is deleted with it."}
      </Muted>

      <Section title="The project">
        <div className={css({ display: "grid", gap: theme.sizing.scale300, gridTemplateColumns: "minmax(0, 1fr)", "@media (min-width: 720px)": { gridTemplateColumns: "1fr 1fr" } })}>
          <FormControl label="Name">
            <Input size="compact" value={f.name} onChange={(e) => set({ name: e.currentTarget.value })} placeholder="Kitchen remodel" overrides={{ Input: { props: { "data-testid": "project-name" } } }} />
          </FormControl>
          <FormControl label="Where (optional)">
            <Input size="compact" value={f.location} onChange={(e) => set({ location: e.currentTarget.value })} placeholder="Oakland, CA" />
          </FormControl>
          <FormControl label="Finished means" caption="The moment that matters, in your words.">
            <Input size="compact" value={f.finish_label} onChange={(e) => set({ finish_label: e.currentTarget.value })} placeholder="Kitchen usable" />
          </FormControl>
          <FormControl label="Promised or hoped-for date">
            <Input size="compact" type="date" value={f.finish_target} onChange={(e) => set({ finish_target: e.currentTarget.value })} />
          </FormControl>
        </div>
      </Section>

      <Section title="Who you're waiting on" hint="Each organization that owes you something. A contact's email lets the plugin file their mail to this project.">
        <div className={css({ display: "grid", gap: theme.sizing.scale300 })}>
          {f.parties.map((p, i) => (
            <div key={i} className={row}>
              <Input size="compact" value={p.name} onChange={(e) => setParty(i, { name: e.currentTarget.value })} placeholder="Organization" aria-label="Organization" />
              {select(ROLES, p.role, (v) => setParty(i, { role: v as Role }), "Role")}
              <Input size="compact" value={p.contact} onChange={(e) => setParty(i, { contact: e.currentTarget.value })} placeholder="Contact (optional)" aria-label="Contact" />
              <Input size="compact" value={p.email} onChange={(e) => setParty(i, { email: e.currentTarget.value })} placeholder="Email (optional)" aria-label="Email" />
              <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => set({ parties: f.parties.filter((_, j) => j !== i) })} aria-label="Remove">
                <Delete size={18} />
              </Button>
            </div>
          ))}
          <div>
            <Button kind={KIND.secondary} size={SIZE.mini} onClick={() => set({ parties: [...f.parties, { name: "", role: "contractor", contact: "", email: "" }] })}>
              Add an organization
            </Button>
          </div>
        </div>
      </Section>

      <Section title="What has to happen" hint="Each step, who owes it, when it's due, and which steps must finish first. Groundwork works out what sets the finish date.">
        <div className={css({ display: "grid", gap: theme.sizing.scale500 })}>
          {f.items.map((it, i) => (
            <div key={i} className={css({ display: "grid", gap: theme.sizing.scale200 })}>
              <div className={row}>
                <Input size="compact" value={it.title} onChange={(e) => setItem(i, { title: e.currentTarget.value })} placeholder="Building permit issued" aria-label="Step" />
                {select(owners, it.owner || "you", (v) => setItem(i, { owner: v }), "Who owes it")}
                {select(STATUSES, it.status, (v) => setItem(i, { status: v as Status }), "Status")}
                <Input size="compact" type="date" value={it.finish} onChange={(e) => setItem(i, { finish: e.currentTarget.value })} aria-label="Due" />
                <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => set({ items: f.items.filter((_, j) => j !== i) })} aria-label="Remove" disabled={f.items.length === 1}>
                  <Delete size={18} />
                </Button>
              </div>
              {titles.filter((t) => t !== it.title).length > 0 && (
                <Select
                  size="compact"
                  multi
                  options={titles.filter((t) => t !== it.title).map((t) => ({ id: t, label: t }))}
                  value={it.after.map((t) => ({ id: t, label: t }))}
                  onChange={({ value }) => setItem(i, { after: value.map((v) => String(v.id)) })}
                  placeholder="Waits on (optional)"
                  aria-label="Waits on"
                />
              )}
            </div>
          ))}
          <div>
            <Button kind={KIND.secondary} size={SIZE.mini} onClick={() => set({ items: [...f.items, { title: "", owner: "", status: "not_started", finish: "", after: [] }] })}>
              Add a step
            </Button>
          </div>
          {titles.length > 1 && (
            <FormControl label="Which step means it's finished?">
              {select(f.items.map((it, i) => ({ id: String(i), label: it.title || `Step ${i + 1}` })), String(finishIndex), (v) => set({ finish_item: Number(v) }), "Finishing step")}
            </FormControl>
          )}
        </div>
      </Section>

      <div className={css({ marginTop: theme.sizing.scale800 })}>
        <Accordion>
          <Panel title="More options">
            <div className={css({ display: "grid", gap: theme.sizing.scale300, gridTemplateColumns: "minmax(0, 1fr)", "@media (min-width: 720px)": { gridTemplateColumns: "1fr 1fr 1fr" } })}>
              <FormControl label="Mandate template" caption="Supervised asks you before anything goes out. You can widen it later.">
                {select(
                  (["supervised", "standard", "auto"] as const).map((t) => ({ id: t, label: TEMPLATE_LABEL[t === "auto" ? "autonomous" : t] })),
                  f.template,
                  (v) => set({ template: v as Form["template"] }),
                  "Mandate template",
                )}
              </FormControl>
              <FormControl label="The project's date" caption="Today, or an earlier date to replay a past project.">
                <Input size="compact" type="date" value={f.as_of} onChange={(e) => set({ as_of: e.currentTarget.value })} />
              </FormControl>
              {!session.local && (
                <FormControl label="Your name" caption="Shown as the project's approver.">
                  <Input size="compact" value={f.your_name} onChange={(e) => set({ your_name: e.currentTarget.value })} placeholder="You" />
                </FormControl>
              )}
            </div>
          </Panel>
        </Accordion>
      </div>

      {errors.length > 0 && (
        <div data-testid="project-errors" className={css({ marginTop: theme.sizing.scale600 })}>
          {errors.map((e) => (
            <ParagraphSmall key={e} margin={0} color={theme.colors.contentNegative}>
              {e}
            </ParagraphSmall>
          ))}
        </div>
      )}

      {preview && (
        <div
          data-testid="project-preview"
          className={css({ marginTop: theme.sizing.scale600, padding: theme.sizing.scale600, borderRadius: theme.borders.radius300, background: theme.colors.backgroundSecondary, display: "grid", gap: theme.sizing.scale200 })}
        >
          <Muted>Forecast · {preview.finish}</Muted>
          <div className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", flexWrap: "wrap" })}>
            <LabelMedium>{fmtLong(preview.forecast)}</LabelMedium>
            <Chip kind={lateness(preview.days_late).late ? "red" : "green"}>{lateness(preview.days_late).text}</Chip>
          </div>
          {preview.sets_the_date && <Muted>Waiting on: {preview.sets_the_date}</Muted>}
        </div>
      )}

      <div className={css({ display: "flex", gap: theme.sizing.scale300, marginTop: theme.sizing.scale600, flexWrap: "wrap" })}>
        <Button kind={KIND.secondary} onClick={() => run(false)} isLoading={busy && !preview} data-testid="check-forecast">
          Check the forecast
        </Button>
        <Button onClick={() => run(true)} isLoading={busy && !!preview} disabled={!preview} data-testid="create-project">
          Create the project
        </Button>
        <Button kind={KIND.tertiary} onClick={() => navigate("/")}>
          Cancel
        </Button>
      </div>
    </Page>
  );
}
