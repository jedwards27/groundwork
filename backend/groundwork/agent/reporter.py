"""The simulated reporter: derives the report from the ledger, truthfully, with no model."""

from __future__ import annotations

from groundwork.schemas.plan import Plan, Report


class SimulatedReporter:
    name = "simulated"

    def report(self, plan: Plan, entries: dict[str, list[str]]) -> tuple[Report, dict]:
        did, asked, refused, failed = [], [], [], []
        for a in plan.actions:
            e = entries.get(a.ref)
            if not e:
                continue
            if "execution_failed" in e:
                failed.append(a.ref)
            elif "executed" in e:
                did.append(a.ref)
            elif "decided:refuse" in e:
                refused.append(a.ref)
            elif "decided:ask" in e:
                asked.append(a.ref)
        summary = (
            f"Ran {len(did)} action(s) on my own in dry run, queued {len(asked)} for approval, and refused "
            f"{len(refused)}" + (f"; {len(failed)} failed" if failed else "") + ". "
            "Every decision, with its reason, is in the ledger."
        )
        return Report(did=did, asked=asked, refused=refused, failed=failed, summary=summary), {}
