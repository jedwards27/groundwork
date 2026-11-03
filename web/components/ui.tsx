// Small building blocks over Base Web, so every screen keeps the same density: a title, one line
// per row, secondary detail in the tertiary color, explanations behind an ⓘ.
import { Drawer as BaseDrawer } from "baseui/drawer";
import { useStyletron } from "baseui";
import { KIND, Tag } from "baseui/tag";
import { StatefulTooltip } from "baseui/tooltip";
import { LabelLarge, LabelSmall, ParagraphSmall, ParagraphXSmall } from "baseui/typography";
import type { ReactNode } from "react";
import { DECISION_LABEL } from "@/lib/format";

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
export function Hint({ text, label = "More" }: { text: ReactNode; label?: string }) {
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

export function Mono({ children }: { children: ReactNode }) {
  const [css, theme] = useStyletron();
  return <span className={css({ ...theme.typography.MonoParagraphXSmall })}>{children}</span>;
}
