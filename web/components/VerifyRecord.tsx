import { useQuery } from "@tanstack/react-query";
import { useStyletron } from "baseui";
import { Button, KIND } from "baseui/button";
import { FormControl } from "baseui/form-control";
import { Select } from "baseui/select";
import { Textarea } from "baseui/textarea";
import { HeadingSmall, ParagraphSmall } from "baseui/typography";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { get, send } from "@/lib/client";
import type { HomeView, LedgerEntry, VerifyEntry } from "@/lib/types";
import { app } from "@/copy/app";
import { Field, Mono, Muted, Page } from "./ui";

const c = app.verify;

// Anyone holding a copy of a record (from a receipt, an export, a screenshot typed back in) can check
// it against the ledger: the record's hash is recomputed, the chain up to it is walked, and the copy
// must hash to exactly what the ledger holds.
export function VerifyRecord() {
  const [css, theme] = useStyletron();
  const [params] = useSearchParams();
  const home = useQuery({ queryKey: ["home"], queryFn: () => get<HomeView>("home") });
  const [project, setProject] = useState(params.get("project") || "");
  const [seq, setSeq] = useState<number | null>(/^\d+$/.test(params.get("record") ?? "") ? Number(params.get("record")) : null);
  const [copy, setCopy] = useState("");
  const [result, setResult] = useState<VerifyEntry | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!project && home.data?.projects.length) setProject(home.data.projects[0].project);
  }, [home.data, project]);
  const ledger = useQuery({
    queryKey: ["ledger", project, "all"],
    queryFn: () => get<{ entries: LedgerEntry[] }>(`sites/${project}/ledger?arm=`),
    enabled: !!project,
  });
  const entries = [...(ledger.data?.entries ?? [])].reverse();
  useEffect(() => {
    if (seq === null && entries.length) setSeq(entries[0].seq);
  }, [entries, seq]);
  const label = (e: LedgerEntry) => {
    const p = e.payload as { ref?: string; title?: string };
    return c.recordOption(e.seq, e.type.replace(/_/g, " "), p.ref, p.title);
  };
  const selected = entries.find((e) => e.seq === seq);
  const verify = async () => {
    setErr("");
    setResult(null);
    let entry: Record<string, unknown> | undefined;
    let target = seq;
    if (copy.trim()) {
      try {
        entry = JSON.parse(copy) as Record<string, unknown>;
      } catch {
        setErr(c.notJson);
        return;
      }
      if (typeof entry.seq === "number") target = entry.seq;
    }
    if (target === null) {
      setErr(c.chooseRecord);
      return;
    }
    setBusy(true);
    try {
      setResult(await send<VerifyEntry>("POST", `sites/${project}/ledger/verify-entry`, { seq: target, entry }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const projects = home.data?.projects ?? [];
  return (
    <Page>
      <HeadingSmall marginTop={0} marginBottom={theme.sizing.scale300}>
        {c.title}
      </HeadingSmall>
      <Muted>{c.intro}</Muted>
      <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale200, marginTop: theme.sizing.scale700, maxWidth: "640px" })}>
        {projects.length > 1 && (
          <FormControl label={c.project}>
            <Select
              options={projects.map((p) => ({ id: p.project, label: p.name }))}
              value={project ? [{ id: project, label: projects.find((p) => p.project === project)?.name ?? project }] : []}
              onChange={({ value }) => {
                setProject(String(value[0]?.id ?? ""));
                setSeq(null);
                setResult(null);
              }}
              clearable={false}
              searchable={false}
            />
          </FormControl>
        )}
        <FormControl label={c.record}>
          <Select
            options={entries.map((e) => ({ id: e.seq, label: label(e) }))}
            value={selected ? [{ id: selected.seq, label: label(selected) }] : []}
            onChange={({ value }) => setSeq(Number(value[0]?.id))}
            clearable={false}
            overrides={{ Root: { props: { "data-testid": "verify-select" } } }}
          />
        </FormControl>
        <FormControl label={c.paste} caption={c.pasteCaption}>
          <Textarea value={copy} onChange={(e) => setCopy((e.target as HTMLTextAreaElement).value)} rows={6} overrides={{ Input: { props: { "data-testid": "verify-copy" }, style: { fontFamily: theme.typography.MonoParagraphSmall.fontFamily } } }} />
        </FormControl>
        {err && <ParagraphSmall color={theme.colors.contentNegative}>{err}</ParagraphSmall>}
        <div className={css({ display: "flex", gap: theme.sizing.scale300, flexWrap: "wrap" })}>
          <Button onClick={verify} isLoading={busy} data-testid="verify-run">
            {c.run}
          </Button>
          <Button kind={KIND.secondary} onClick={() => selected && setCopy(JSON.stringify(selected, null, 2))} disabled={!selected}>
            {c.pasteStored}
          </Button>
          {copy && (
            <Button kind={KIND.tertiary} onClick={() => setCopy("")}>
              {c.clear}
            </Button>
          )}
        </div>
      </div>
      {result && (
        <section
          data-testid="verify-result"
          className={css({
            marginTop: theme.sizing.scale800,
            maxWidth: "640px",
            padding: theme.sizing.scale600,
            borderRadius: theme.borders.radius300,
            background: result.match ? theme.colors.backgroundPositiveLight : theme.colors.backgroundNegativeLight,
            display: "grid",
            gap: theme.sizing.scale400,
          })}
        >
          <HeadingSmall margin={0} data-testid="verify-verdict">
            {result.match ? c.match : c.mismatch}
          </HeadingSmall>
          <ParagraphSmall margin={0}>
            {result.match ? c.matchBody : c.mismatchBody}
          </ParagraphSmall>
          {result.problems.map((p) => (
            <ParagraphSmall key={p} margin={0} color={theme.colors.contentNegative}>
              {p}
            </ParagraphSmall>
          ))}
          {result.found && (
            <>
              <Field label={c.record}>{c.recordLine(result.seq, result.type, result.mandate_version)}</Field>
              <Field label={c.storedHash}>
                <Mono>{result.stored_hash}</Mono>
              </Field>
              {result.copy_hash && (
                <Field label={c.yourCopy}>
                  <Mono>{result.copy_hash}</Mono>
                </Field>
              )}
            </>
          )}
        </section>
      )}
    </Page>
  );
}
