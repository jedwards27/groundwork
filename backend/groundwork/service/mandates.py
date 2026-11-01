"""Mandate versions: read, change the preset (a new version), re-decide what is still open, and
preview a plan under every preset without writing anything."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundwork.db import models as m
from groundwork.db import repo
from groundwork.ledger import append
from groundwork.policy import PRESETS, Mandate, build_preset
from groundwork.schemas.action import Autonomy, ProposedAction
from groundwork.schemas.plan import Intent, Plan
from groundwork.service import actions as actions_svc
from groundwork.service.decisions import decide_plan
from groundwork.service.differential import EffectInput, compute
from groundwork.service.state import SiteState

OPEN_STATES = ("pending", "proposed", "executing")


def mandate_view(s: Session, site_id: uuid.UUID) -> dict[str, Any]:
    rows = list(
        s.execute(
            select(m.MandateVersion)
            .where(m.MandateVersion.site_id == site_id)
            .order_by(m.MandateVersion.version)
        ).scalars()
    )
    current = Mandate.model_validate(rows[-1].doc)
    return {
        "version": current.version,
        "preset": current.preset,
        "doc": current.model_dump(mode="json"),
        "plain_lines": current.plain_lines(),
        "presets": list(PRESETS),
        "history": [{"version": r.version, "preset": r.preset, "at": r.created_at.isoformat()} for r in rows],
    }


def _proposed(row: m.Action) -> ProposedAction:
    return actions_svc.proposed_from_row(row)


def latest_primary_plan(s: Session, site_id: uuid.UUID) -> m.Plan | None:
    runs = list(
        s.execute(select(m.Run).where(m.Run.site_id == site_id).order_by(m.Run.created_at.desc())).scalars()
    )
    for run in runs:
        p = actions_svc.primary_plan(s, run.id)
        if p is not None:
            return p
    return None


def set_preset(
    s: Session, state: SiteState, preset: str, person_id: uuid.UUID | None, person_key: str | None
) -> dict[str, Any]:
    """Issue a new mandate version and re-decide open actions of the latest plan. Never re-plans;
    executed, approved, declined and refused actions keep their record."""
    from groundwork.service.pipeline import execute_actions, spent_today

    site_id = state.require_site_id()
    current = repo.active_mandate(s, site_id)
    new = build_preset(
        preset,
        issuer=current.issuer,
        subject=current.subject,
        approvers=current.ask.approvers,
        legal_approvers=current.ask.legal_approvers,
        sla_hours=current.ask.sla_hours,
        owner_goals=current.owner_goals,
        valid_from=state.as_of,
        version=current.version + 1,
        dry_run=current.dry_run,
    )
    s.add(
        m.MandateVersion(
            org_id=state.org_id,
            site_id=site_id,
            version=new.version,
            preset=new.preset,
            doc=new.model_dump(mode="json"),
            created_by_person_id=person_id,
        )
    )
    s.flush()
    append(
        s,
        "mandate_issued",
        {
            "site": state.key,
            "version": new.version,
            "preset": new.preset,
            "previous_version": current.version,
            "previous_preset": current.preset,
            "by": person_key,
            "summary": new.plain_lines(),
        },
    )
    plan_row = latest_primary_plan(s, site_id)
    changes: list[dict[str, Any]] = []
    executed: list[str] = []
    if plan_row is not None:
        view = actions_svc.plan_view(s, state, plan_row)
        open_refs = {a["ref"]: a for a in view["actions"] if a["state"] in OPEN_STATES}
        rows = {
            r.ref: r for r in s.execute(select(m.Action).where(m.Action.plan_id == plan_row.id)).scalars()
        }
        to_decide = [_proposed(rows[ref]) for ref in open_refs]
        decided = decide_plan(
            state,
            new,
            Plan(assessment="re-decision", actions=to_decide, intent=Intent()),
            spent_today_cents=spent_today(s, state.timezone),
        )
        newly_auto = []
        for d in decided:
            row = rows[d.action.ref]
            prev = open_refs[d.action.ref]["decision"]
            dec = d.decision
            approvers = new.approvers_for(dec.kind) if dec.decision == Autonomy.ask else []
            context = {
                **d.resolved.details,
                "approvers": approvers,
                "missing_params": list(d.resolved.ctx.missing_params),
            }
            s.add(
                m.Decision(
                    org_id=state.org_id,
                    action_id=row.id,
                    mandate_version=new.version,
                    decision=dec.decision.value,
                    reason=dec.reason,
                    rule=dec.rule,
                    delta=dec.delta,
                    kind=dec.kind.value,
                    effect_class=dec.effect_class.value,
                    channel=dec.channel.value,
                    record_bearing=dec.record_bearing,
                    content_class=d.resolved.details["content_class"],
                    classifier=d.resolved.ctx.classifier,
                    amount_cents=dec.amount_cents,
                    context=context,
                )
            )
            append(
                s,
                "decided",
                {
                    "ref": row.ref,
                    "title": row.title,
                    "decision": dec.decision.value,
                    "reason": dec.reason,
                    "rule": dec.rule,
                    "delta": dec.delta,
                    "kind": dec.kind.value,
                    "record_bearing": dec.record_bearing,
                    "amount_cents": dec.amount_cents,
                    "mandate_version": new.version,
                    "redecided": True,
                    "previous_decision": prev,
                    "approvers": approvers,
                },
                run_id=row.run_id,
                action_id=row.id,
                arm=row.arm,
            )
            changes.append({"ref": row.ref, "from": prev, "to": dec.decision.value, "reason": dec.reason})
            if dec.decision == Autonomy.auto:
                newly_auto.append(row)
        s.flush()
        executed = execute_actions(s, newly_auto, plan_row.run_id)
    return {"version": new.version, "preset": new.preset, "redecided": changes, "executed": executed}


def compare_presets(s: Session, state: SiteState, plan_row: m.Plan) -> list[dict[str, Any]]:
    """The same stored plan under each preset: counts and the differential. Writes nothing."""
    base = repo.active_mandate(s, state.require_site_id())
    rows = list(
        s.execute(
            select(m.Action).where(m.Action.plan_id == plan_row.id).order_by(m.Action.created_at)
        ).scalars()
    )
    plan = Plan(assessment="preview", actions=[_proposed(r) for r in rows], intent=Intent())
    out = []
    for preset in PRESETS:
        mandate = build_preset(
            preset,
            issuer=base.issuer,
            approvers=base.ask.approvers,
            legal_approvers=base.ask.legal_approvers,
            valid_from=state.as_of,
        )
        decided = decide_plan(state, mandate, plan)
        states = {"auto": "executed", "ask": "pending", "refuse": "refused"}
        diff = compute(
            state,
            [
                EffectInput(
                    d.action.ref,
                    d.action.effect,
                    d.resolved.ctx.effect_allowed,
                    d.resolved.lag_bd,
                    states[d.decision.decision.value],
                )
                for d in decided
            ],
        )
        counts = {
            k: sum(1 for d in decided if d.decision.decision.value == k) for k in ("auto", "ask", "refuse")
        }
        out.append(
            {
                "preset": preset,
                "current": preset == base.preset,
                **counts,
                "held": sum(1 for d in decided if d.decision.held),
                "decisions": {d.action.ref: d.decision.decision.value for d in decided},
                "recovered_now": diff.recovered_now,
                "recovered_if_approved": diff.recovered_if_approved,
                "recovered_if_they_agree": diff.recovered_if_they_agree,
            }
        )
    return out
