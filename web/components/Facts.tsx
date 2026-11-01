"use client";
import type { SiteView } from "@/lib/types";
import { Prov } from "./Tip";

export function Facts({ site }: { site: SiteView }) {
  return (
    <section className="panel" aria-label="Site facts">
      <h2>
        {site.name} <span className="hint">{site.location}</span>
      </h2>
      <div className="facts">
        {site.facts.map((f) => (
          <div className="fact" key={f.label}>
            <div className="l">
              {f.label} <Prov provenance={f.provenance} source={f.source} />
            </div>
            <div className="v">{f.value}</div>
          </div>
        ))}
      </div>
      <p className="note">
        Working for <b>{site.parties.find((p) => p.key === site.principal)?.name}</b> as end user. Requests to the
        landlord go through the lessee; the utility is reached only through the landlord. Every number carries its
        source; assumptions are listed in docs/PRACTITIONER-QUESTIONS.md.
      </p>
    </section>
  );
}
