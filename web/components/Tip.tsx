"use client";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

export function Tip({ text, children }: { text: ReactNode; children: ReactNode }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tip" sideOffset={6}>
          {text}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function Prov({ provenance, source }: { provenance: string; source?: string }) {
  const label = provenance === "assumption_to_verify" ? "assumption" : provenance;
  const tip =
    provenance === "public"
      ? "Public source"
      : provenance === "synthetic"
        ? "Written for the demo"
        : "Our best understanding; check with a practitioner (docs/PRACTITIONER-QUESTIONS.md)";
  if (source?.startsWith("http"))
    return (
      <Tip text={`${tip}: ${source}`}>
        <a className={`prov ${provenance}`} href={source} target="_blank" rel="noreferrer">
          {label}
        </a>
      </Tip>
    );
  return (
    <Tip text={source ? `${tip}. Source: ${source}` : tip}>
      <span className={`prov ${provenance}`} tabIndex={0}>
        {label}
      </span>
    </Tip>
  );
}
