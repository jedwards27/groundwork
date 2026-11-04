// Small building blocks over Base Web, so every screen keeps the same density: a title, one line
// per row, secondary detail in the tertiary color, explanations behind an ⓘ.
import { Drawer as BaseDrawer } from "baseui/drawer";
import { useStyletron } from "baseui";
import { KIND, Tag } from "baseui/tag";
import { StatefulTooltip } from "baseui/tooltip";
import { LabelLarge, LabelMedium, LabelSmall, ParagraphSmall, ParagraphXSmall } from "baseui/typography";
import { Input } from "baseui/input";
import { Pagination } from "baseui/pagination";
import { useEffect, useState, type ReactNode } from "react";
import { DECISION_LABEL } from "@/lib/format";
import { app } from "@/copy/app";

export function Page({ children }: { children: ReactNode }) {
  const [css, theme] = useStyletron();
  return (
    <main
      className={css({
        maxWidth: "1040px",
        margin: "0 auto",
        padding: `${theme.sizing.scale800} ${theme.sizing.scale600} ${theme.sizing.scale1600}`,
      })}
    >
      {children}
    </main>
  );
}

export function Section({ title, hint, right, children, testId }: {
  title: ReactNode;
  hint?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  testId?: string;
}) {
  const [css, theme] = useStyletron();
  return (
    <section className={css({ marginTop: theme.sizing.scale900 })} data-testid={testId}>
      <div className={css({ display: "flex", alignItems: "center", gap: theme.sizing.scale300, marginBottom: theme.sizing.scale300 })}>
        <LabelLarge>{title}</LabelLarge>
        {hint && <Hint text={hint} />}
        <div className={css({ marginLeft: "auto", display: "flex", gap: theme.sizing.scale300, alignItems: "center" })}>{right}</div>
      </div>
      {children}
    </section>
  );
}

// A list row: one line, the whole row clickable when it opens something.
export function Row({ children, onClick, testId }: { children: ReactNode; onClick?: () => void; testId?: string }) {
  const [css, theme] = useStyletron();
  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => {
        if (onClick && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick();
        }
      }}
      data-testid={testId}
      className={css({
        display: "flex",
        alignItems: "center",
        gap: theme.sizing.scale500,
        minHeight: "48px",
        padding: `${theme.sizing.scale300} ${theme.sizing.scale300}`,
        borderBottom: `1px solid ${theme.colors.borderOpaque}`,
        cursor: onClick ? "pointer" : "default",
        ":hover": onClick ? { background: theme.colors.backgroundSecondary } : {},
        ":focus-visible": { outline: `2px solid ${theme.colors.borderSelected}`, outlineOffset: "-2px" },
      })}
    >
      {children}
    </div>
  );
}

export function Grow({ children }: { children: ReactNode }) {
  const [css] = useStyletron();
  return <div className={css({ flex: "1 1 auto", minWidth: 0 })}>{children}</div>;
}

export function Line({ children, testId }: { children: ReactNode; testId?: string }) {
  const [css] = useStyletron();
  return (
    <ParagraphSmall margin={0} className={css({ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" })} data-testid={testId}>
      {children}
    </ParagraphSmall>
  );
}

export function Muted({ children, testId, nowrap }: { children: ReactNode; testId?: string; nowrap?: boolean }) {
  const [css, theme] = useStyletron();
  return (
    <ParagraphXSmall
      margin={0}
      color={theme.colors.contentTertiary}
      className={css({ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: nowrap ? "nowrap" : "normal", flexShrink: nowrap ? 0 : 1 })}
      data-testid={testId}
    >
      {children}
    </ParagraphXSmall>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  const [, theme] = useStyletron();
  return (
    <ParagraphSmall margin={0} color={theme.colors.contentTertiary} padding={`${theme.sizing.scale300} ${theme.sizing.scale300}`}>
      {children}
    </ParagraphSmall>
  );
}

// ⓘ with an explanation on hover or focus.
export function Hint({ text, label = app.common.more }: { text: ReactNode; label?: string }) {
  const [css, theme] = useStyletron();
  return (
    <StatefulTooltip content={<div className={css({ maxWidth: "320px" })}>{text}</div>} showArrow returnFocus autoFocus={false} placement="top">
      <span
        tabIndex={0}
        aria-label={label}
        className={css({
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: "16px",
          height: "16px",
          borderRadius: "50%",
          border: `1px solid ${theme.colors.contentTertiary}`,
          color: theme.colors.contentTertiary,
          fontSize: "10px",
          fontWeight: 600,
          cursor: "help",
          flex: "0 0 auto",
        })}
      >
        i
      </span>
    </StatefulTooltip>
  );
}

// The gateway's three decisions, in the product's words.
export function DecisionTag({ decision, testId }: { decision: string | null; testId?: string }) {
  if (!decision) return null;
  const kind = decision === "auto" ? KIND.green : decision === "ask" ? KIND.yellow : KIND.red;
  return (
    <span data-testid={testId}>
      <Tag closeable={false} kind={kind} size="small" contentMaxWidth={null} overrides={{ Root: { style: { margin: 0, minWidth: "52px", justifyContent: "center" } } }}>
        {(DECISION_LABEL[decision] ?? decision).replace(/^./, (c) => c.toUpperCase())}
      </Tag>
    </span>
  );
}

export function Chip({ children, kind = "gray", tip, testId }: {
  children: ReactNode;
  kind?: "gray" | "green" | "red" | "yellow" | "blue";
  tip?: ReactNode;
  testId?: string;
}) {
  const tag = (
    <span data-testid={testId}>
      <Tag closeable={false} kind={KIND[kind]} size="small" contentMaxWidth={null} overrides={{ Root: { style: { margin: 0 } } }}>
        {children}
      </Tag>
    </span>
  );
  return tip ? (
    <StatefulTooltip content={tip} showArrow placement="bottom">
      {tag}
    </StatefulTooltip>
  ) : (
    tag
  );
}

// Details open in a panel from the right, the full width of a phone.
export function Drawer({ open, onClose, title, children, footer, testId }: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  testId?: string;
}) {
  const [css, theme] = useStyletron();
  return (
    <BaseDrawer
      isOpen={open}
      onClose={onClose}
      autoFocus
      size="min(560px, 100vw)"
      overrides={{ DrawerBody: { style: { marginTop: theme.sizing.scale800, marginLeft: theme.sizing.scale700, marginRight: theme.sizing.scale700 } } }}
    >
      <div data-testid={testId} className={css({ display: "flex", flexDirection: "column", gap: theme.sizing.scale500, paddingBottom: "120px" })}>
        <LabelLarge>{title}</LabelLarge>
        {children}
        {footer && <div className={css({ display: "flex", gap: theme.sizing.scale300, flexWrap: "wrap", marginTop: theme.sizing.scale300 })}>{footer}</div>}
      </div>
    </BaseDrawer>
  );
}

// A labeled field in a drawer.
export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  const [css, theme] = useStyletron();
  return (
    <div className={css({ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: theme.sizing.scale100 })}>
      <LabelSmall color={theme.colors.contentTertiary}>{label}</LabelSmall>
      <div className={css({ ...theme.typography.ParagraphSmall })}>{children}</div>
    </div>
  );
}

// Text as it would go out: kept as written, scrollable when long.
export function Quote({ children, testId }: { children: ReactNode; testId?: string }) {
  const [css, theme] = useStyletron();
  return (
    <div
      data-testid={testId}
      className={css({
        ...theme.typography.ParagraphSmall,
        whiteSpace: "pre-wrap",
        background: theme.colors.backgroundSecondary,
        borderRadius: theme.borders.radius300,
        padding: theme.sizing.scale500,
        maxHeight: "320px",
        overflowY: "auto",
      })}
    >
      {children}
    </div>
  );
}

// What an action would send, laid out like the message itself: who it's to, the subject, the text.
// It leads the drawer, since it's the thing being approved.
export function Outgoing({ label, to, subject, text, testId }: {
  label: string;
  to?: string | null;
  subject?: string | null;
  text?: string | null;
  testId?: string;
}) {
  const [css, theme] = useStyletron();
  return (
    <div
      data-testid={testId}
      className={css({
        border: `1px solid ${theme.colors.borderOpaque}`,
        borderRadius: theme.borders.radius300,
        padding: theme.sizing.scale500,
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr)",
        gap: theme.sizing.scale300,
      })}
    >
      <LabelSmall color={theme.colors.contentTertiary}>{label}</LabelSmall>
      {to && <ParagraphSmall margin={0} color={theme.colors.contentSecondary}>{to}</ParagraphSmall>}
      {subject && <LabelMedium>{subject}</LabelMedium>}
      {text && (
        <div className={css({ ...theme.typography.ParagraphSmall, whiteSpace: "pre-wrap", maxHeight: "320px", overflowY: "auto" })}>{text}</div>
      )}
    </div>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  const [css, theme] = useStyletron();
  return <span className={css({ ...theme.typography.MonoParagraphXSmall })}>{children}</span>;
}

// Text from the copy files (web/copy), where **this** is bold, `this` is code and [this](https://…) is a link.
export function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/).map((part, i) => {
        const link = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(part);
        if (link)
          return (
            <a key={i} href={link[2]} target="_blank" rel="noreferrer">
              {link[1]}
            </a>
          );
        if (part.startsWith("**") && part.endsWith("**")) return <b key={i}>{part.slice(2, -2)}</b>;
        if (part.startsWith("`") && part.endsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
        return part;
      })}
    </>
  );
}


// Long lists come a page at a time. The page goes back to the first whenever `reset` changes (a new
// filter or search), so a narrowed list never opens on an empty page.
export function usePages<T>(items: T[], size: number, reset: string): { rows: T[]; pager: ReactNode } {
  const [n, setN] = useState(1);
  useEffect(() => setN(1), [reset]);
  const pages = Math.max(1, Math.ceil(items.length / size));
  const page = Math.min(n, pages);
  const from = (page - 1) * size;
  return {
    rows: items.slice(from, from + size),
    pager:
      pages > 1 ? (
        <Pager page={page} pages={pages} onChange={setN} label={app.common.showing(from + 1, Math.min(from + size, items.length), items.length)} />
      ) : null,
  };
}

function Pager({ page, pages, onChange, label }: { page: number; pages: number; onChange: (n: number) => void; label: string }) {
  const [css, theme] = useStyletron();
  return (
    <div className={css({ display: "flex", alignItems: "center", gap: theme.sizing.scale400, flexWrap: "wrap", marginTop: theme.sizing.scale300 })} data-testid="pager">
      <Pagination
        size="compact"
        numPages={pages}
        currentPage={page}
        onPageChange={({ nextPage }) => onChange(Math.min(Math.max(nextPage, 1), pages))}
        labels={{ prevButton: app.common.previous, nextButton: app.common.next, preposition: app.common.of }}
      />
      <Muted>{label}</Muted>
    </div>
  );
}

// A search box for a list.
export function Search({ value, onChange, placeholder, testId }: { value: string; onChange: (v: string) => void; placeholder: string; testId?: string }) {
  const [css] = useStyletron();
  return (
    <div className={css({ flex: "1 1 200px", maxWidth: "320px" })}>
      <Input
        value={value}
        onChange={(e) => onChange((e.target as HTMLInputElement).value)}
        placeholder={placeholder}
        size="compact"
        clearable
        overrides={{ Input: { props: { "data-testid": testId, "aria-label": placeholder } } }}
      />
    </div>
  );
}

// Whether any of these texts contains what was typed (ignoring case).
export function matches(q: string, ...texts: (string | null | undefined)[]): boolean {
  const needle = q.trim().toLowerCase();
  return !needle || texts.some((t) => t?.toLowerCase().includes(needle));
}
