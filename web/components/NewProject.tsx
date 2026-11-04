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
import { Textarea } from "baseui/textarea";
import { Select, type Value } from "baseui/select";
import { HeadingSmall, LabelMedium, ParagraphSmall } from "baseui/typography";
import { useState } from "react";
import { useNavigate } from "react-router";
import { ApiError, send } from "@/lib/client";
import { fmtLong, lateness, TEMPLATE_LABEL } from "@/lib/format";
import type { Session } from "@/lib/types";
import { newProject as say } from "@/copy/newProject";
import { Chip, Muted, Page, Section } from "./ui";

type Role = "contractor" | "designer" | "consultant" | "vendor" | "landlord" | "lender" | "ahj" | "agency" | "regulator" | "developer" | "operator" | "community";
type Status = "not_started" | "in_progress" | "done" | "cancelled";

const ROLES = (Object.keys(say.parties.roles) as Role[]).map((id) => ({ id, label: say.parties.roles[id] }));
const STATUSES = (Object.keys(say.steps.statuses) as Status[]).map((id) => ({ id, label: say.steps.statuses[id] }));

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

// A small example to start from (its words are in web/copy/newProject.ts): a kitchen remodel whose
// cabinets arrive weeks after they were meant to go in, so the forecast opens late, waiting on the supplier.
const example = (): Form => {
  const x = say.example;
  return {
    name: x.name,
    location: x.location,
    finish_label: x.finishLabel,
    finish_target: plus(85),
    finish_item: 4,
    template: "supervised",
    as_of: today(),
    your_name: "",
    parties: [
      { name: x.contractor, role: "contractor", contact: x.contractorContact, email: x.contractorEmail },
      { name: x.permitOffice, role: "ahj", contact: "", email: "" },
      { name: x.supplier, role: "vendor", contact: "", email: "" },
    ],
    items: [
      { title: x.permit, owner: x.permitOffice, status: "in_progress", finish: plus(28), after: [] },
      { title: x.delivered, owner: x.supplier, status: "not_started", finish: plus(92), after: [] },
      { title: x.installed, owner: x.contractor, status: "not_started", finish: plus(70), after: [x.permit, x.delivered] },
      { title: x.countertops, owner: x.contractor, status: "not_started", finish: plus(78), after: [x.installed] },
      { title: x.inspection, owner: x.permitOffice, status: "not_started", finish: plus(85), after: [x.countertops] },
    ],
  };
};

// A date as a spreadsheet writes it: 2026-12-01, 12/1/2026 or "Dec 1, 2026".
function isoDate(text: string): string | null {
  const t = text.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return t;
  const us = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (us) {
    const y = us[3].length === 2 ? 2000 + Number(us[3]) : Number(us[3]);
    return `${y}-${pad(Number(us[1]))}-${pad(Number(us[2]))}`;
  }
  const d = new Date(t);
  return t && !Number.isNaN(d.getTime()) ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` : null;
}

function statusOf(text: string): Status {
  const t = text.trim().toLowerCase();
  if (/^(done|complete|completed|finished|closed|yes)$/.test(t)) return "done";
  if (/cancel|descoped|dropped/.test(t)) return "cancelled";
  if (/progress|under way|underway|started|ongoing|in work/.test(t)) return "in_progress";
  return "not_started";
}

// Rows pasted from a spreadsheet (tabs) or typed (commas), as steps.
function parsePasted(text: string): { items: ItemRow[]; skipped: number } {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const items: ItemRow[] = [];
  let skipped = 0;
  lines.forEach((line, n) => {
    const cells = (line.includes("\t") ? line.split("\t") : line.split(",")).map((c) => c.trim());
    if (n === 0 && /^(step|task|title|item|name)s?$/i.test(cells[0])) return;
    const [title = "", owner = "", status = "", due = "", after = ""] = cells;
    const finish = isoDate(due);
    if (!title || !finish) {
      skipped += 1;
      return;
    }
    items.push({ title, owner: /^(you|me|us|owner|client)$/i.test(owner) ? "you" : owner, status: statusOf(status), finish, after: after.split(";").map((a) => a.trim()).filter(Boolean) });
  });
  return { items, skipped };
}

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
    your_name: f.your_name || say.defaults.yourName,
    draft: {
      name: f.name.trim(),
      location: f.location.trim(),
      as_of: f.as_of || null,
      finish_label: f.finish_label.trim() || say.defaults.finished,
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
  const [pasted, setPasted] = useState("");
  const [pasteNote, setPasteNote] = useState("");
  const set = (patch: Partial<Form>) => {
    setF((x) => ({ ...x, ...patch }));
    setPreview(null);
  };
  const setParty = (i: number, patch: Partial<PartyRow>) => set({ parties: f.parties.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const setItem = (i: number, patch: Partial<ItemRow>) => set({ items: f.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });
  const addPasted = () => {
    const { items, skipped } = parsePasted(pasted);
    const kept = f.items.filter((it) => it.title.trim() || it.finish);
    const known = new Set(["you", ...f.parties.map((p) => p.name.trim())]);
    const newOwners = [...new Set(items.map((it) => it.owner).filter((o) => o && !known.has(o)))];
    set({
      items: [...kept, ...items],
      parties: [...f.parties.filter((p) => p.name.trim()), ...newOwners.map((name) => ({ name, role: "contractor" as Role, contact: "", email: "" }))],
    });
    setPasteNote(say.steps.paste.added(items.length, skipped));
    if (items.length) setPasted("");
  };
  const owners = [{ id: "you", label: say.steps.you }, ...f.parties.filter((p) => p.name.trim()).map((p) => ({ id: p.name, label: p.name }))];
  const titles = f.items.map((it) => it.title).filter((t) => t.trim());
  const finishIndex = f.finish_item >= 0 && f.finish_item < f.items.length ? f.finish_item : f.items.length - 1;

  const check = (): string[] => {
    const out: string[] = [];
    if (!f.name.trim()) out.push(say.errors.name);
    if (!f.finish_target) out.push(say.errors.date);
    if (f.items.some((it) => !it.title.trim() || !it.finish)) out.push(say.errors.steps);
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
        <HeadingSmall margin={0}>{say.title}</HeadingSmall>
        <span className={css({ marginLeft: "auto" })}>
          <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => { setF(example()); setPreview(null); setErrors([]); }} data-testid="use-example">
            {say.fillExample}
          </Button>
        </span>
      </div>
      <Muted>
        {say.intro} {session.local ? say.whereItLives.local : say.whereItLives.hosted}
      </Muted>

      <Section title={say.project.title}>
        <div className={css({ display: "grid", gap: theme.sizing.scale300, gridTemplateColumns: "minmax(0, 1fr)", "@media (min-width: 720px)": { gridTemplateColumns: "1fr 1fr" } })}>
          <FormControl label={say.project.name}>
            <Input size="compact" value={f.name} onChange={(e) => set({ name: e.currentTarget.value })} placeholder={say.project.namePlaceholder} overrides={{ Input: { props: { "data-testid": "project-name" } } }} />
          </FormControl>
          <FormControl label={say.project.where}>
            <Input size="compact" value={f.location} onChange={(e) => set({ location: e.currentTarget.value })} placeholder={say.project.wherePlaceholder} />
          </FormControl>
          <FormControl label={say.project.finishedMeans} caption={say.project.finishedMeansCaption}>
            <Input size="compact" value={f.finish_label} onChange={(e) => set({ finish_label: e.currentTarget.value })} placeholder={say.project.finishedMeansPlaceholder} />
          </FormControl>
          <FormControl label={say.project.date}>
            <Input size="compact" type="date" value={f.finish_target} onChange={(e) => set({ finish_target: e.currentTarget.value })} />
          </FormControl>
        </div>
      </Section>

      <Section title={say.parties.title} hint={say.parties.hint}>
        <div className={css({ display: "grid", gap: theme.sizing.scale300 })}>
          {f.parties.map((p, i) => (
            <div key={i} className={row}>
              <Input size="compact" value={p.name} onChange={(e) => setParty(i, { name: e.currentTarget.value })} placeholder={say.parties.organization} aria-label={say.parties.organization} />
              {select(ROLES, p.role, (v) => setParty(i, { role: v as Role }), say.parties.role)}
              <Input size="compact" value={p.contact} onChange={(e) => setParty(i, { contact: e.currentTarget.value })} placeholder={say.parties.contact} aria-label={say.parties.contact} />
              <Input size="compact" value={p.email} onChange={(e) => setParty(i, { email: e.currentTarget.value })} placeholder={say.parties.email} aria-label={say.parties.email} />
              <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => set({ parties: f.parties.filter((_, j) => j !== i) })} aria-label={say.parties.remove}>
                <Delete size={18} />
              </Button>
            </div>
          ))}
          <div>
            <Button kind={KIND.secondary} size={SIZE.mini} onClick={() => set({ parties: [...f.parties, { name: "", role: "contractor", contact: "", email: "" }] })}>
              {say.parties.add}
            </Button>
          </div>
        </div>
      </Section>

      <Section title={say.steps.title} hint={say.steps.hint}>
        <div className={css({ display: "grid", gap: theme.sizing.scale500 })}>
          {f.items.map((it, i) => (
            <div key={i} className={css({ display: "grid", gap: theme.sizing.scale200 })}>
              <div className={row}>
                <Input size="compact" value={it.title} onChange={(e) => setItem(i, { title: e.currentTarget.value })} placeholder={say.steps.stepPlaceholder} aria-label={say.steps.step} />
                {select(owners, it.owner || "you", (v) => setItem(i, { owner: v }), say.steps.owner)}
                {select(STATUSES, it.status, (v) => setItem(i, { status: v as Status }), say.steps.status)}
                <Input size="compact" type="date" value={it.finish} onChange={(e) => setItem(i, { finish: e.currentTarget.value })} aria-label={say.steps.due} />
                <Button kind={KIND.tertiary} size={SIZE.compact} onClick={() => set({ items: f.items.filter((_, j) => j !== i) })} aria-label={say.parties.remove} disabled={f.items.length === 1}>
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
                  placeholder={say.steps.waitsOn}
                  aria-label={say.steps.waitsOn}
                />
              )}
            </div>
          ))}
          <div>
            <Button kind={KIND.secondary} size={SIZE.mini} onClick={() => set({ items: [...f.items, { title: "", owner: "", status: "not_started", finish: "", after: [] }] })}>
              {say.steps.add}
            </Button>
          </div>
          <Accordion overrides={{ Content: { style: { paddingLeft: 0, paddingRight: 0 } }, Header: { style: { paddingLeft: 0, paddingRight: 0 } } }}>
            <Panel title={say.steps.paste.title}>
              <div className={css({ display: "grid", gap: theme.sizing.scale300 })}>
                <Muted>{say.steps.paste.hint}</Muted>
                <Textarea value={pasted} onChange={(e) => setPasted((e.target as HTMLTextAreaElement).value)} placeholder={say.steps.paste.placeholder} rows={6} overrides={{ Input: { props: { "data-testid": "paste-steps" } } }} />
                <div>
                  <Button kind={KIND.secondary} size={SIZE.mini} onClick={addPasted} disabled={!pasted.trim()} data-testid="paste-add">
                    {say.steps.paste.add}
                  </Button>
                </div>
                {pasteNote && <Muted testId="paste-note">{pasteNote}</Muted>}
              </div>
            </Panel>
          </Accordion>
          {titles.length > 1 && (
            <FormControl label={say.steps.finishing}>
              {select(f.items.map((it, i) => ({ id: String(i), label: it.title || say.steps.numbered(i + 1) })), String(finishIndex), (v) => set({ finish_item: Number(v) }), say.steps.finishingLabel)}
            </FormControl>
          )}
        </div>
      </Section>

      <div className={css({ marginTop: theme.sizing.scale800 })}>
        <Accordion>
          <Panel title={say.more.title}>
            <div className={css({ display: "grid", gap: theme.sizing.scale300, gridTemplateColumns: "minmax(0, 1fr)", "@media (min-width: 720px)": { gridTemplateColumns: "1fr 1fr 1fr" } })}>
              <FormControl label={say.more.template} caption={say.more.templateCaption}>
                {select(
                  (["supervised", "standard", "auto"] as const).map((t) => ({ id: t, label: TEMPLATE_LABEL[t === "auto" ? "autonomous" : t] })),
                  f.template,
                  (v) => set({ template: v as Form["template"] }),
                  say.more.template,
                )}
              </FormControl>
              <FormControl label={say.more.asOf} caption={say.more.asOfCaption}>
                <Input size="compact" type="date" value={f.as_of} onChange={(e) => set({ as_of: e.currentTarget.value })} />
              </FormControl>
              {!session.local && (
                <FormControl label={say.more.yourName} caption={say.more.yourNameCaption}>
                  <Input size="compact" value={f.your_name} onChange={(e) => set({ your_name: e.currentTarget.value })} placeholder={say.more.yourNamePlaceholder} />
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
          <Muted>{say.preview.forecast(preview.finish)}</Muted>
          <div className={css({ display: "flex", gap: theme.sizing.scale300, alignItems: "center", flexWrap: "wrap" })}>
            <LabelMedium>{fmtLong(preview.forecast)}</LabelMedium>
            <Chip kind={lateness(preview.days_late).late ? "red" : "green"}>{lateness(preview.days_late).text}</Chip>
          </div>
          {preview.sets_the_date && <Muted>{say.preview.waitingOn(preview.sets_the_date)}</Muted>}
        </div>
      )}

      <div className={css({ display: "flex", gap: theme.sizing.scale300, marginTop: theme.sizing.scale600, flexWrap: "wrap" })}>
        <Button kind={KIND.secondary} onClick={() => run(false)} isLoading={busy && !preview} data-testid="check-forecast">
          {say.check}
        </Button>
        <Button onClick={() => run(true)} isLoading={busy && !!preview} disabled={!preview} data-testid="create-project">
          {say.create}
        </Button>
        <Button kind={KIND.tertiary} onClick={() => navigate("/")}>
          {say.cancel}
        </Button>
      </div>
    </Page>
  );
}
