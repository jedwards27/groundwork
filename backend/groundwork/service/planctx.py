"""Render what a planner may see. Byte-stable for a given site state so the prompt prefix caches.
People's email addresses, approvals and credentials are never included (docs/DATA-BOUNDARY.md)."""

from __future__ import annotations

import re
from typing import Any

from groundwork.agent.base import PlanContext
from groundwork.domain import get_profile
from groundwork.ingest.site_loader import EventRow
from groundwork.policy import Mandate
from groundwork.schemas.plan import Arm
from groundwork.service import views
from groundwork.service.state import SiteState

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def redact(text: str) -> str:
    """Email addresses never reach a model; messages keep their names and content."""
    return EMAIL.sub("[address withheld]", text)


EVIDENCE_FIELDS = ("amount_cents", "currency", "scope", "cancellation_terms", "payer", "valid_until")


def site_state_doc(state: SiteState) -> dict[str, Any]:
    profile = get_profile(state.profile)
    c = views.chain_view(state)
    by_item = {i.key: i for i in c.items}
    return {
        "site": {
            "key": state.key,
            "name": state.name,
            "location": state.location,
            "asset": state.asset_name,
            "principal": state.principal,
        },
        "milestone": {
            "label": c.milestone.label,
            "item": c.milestone.item,
            "target_date": c.milestone.target_date.isoformat(),
            "forecast_finish": c.milestone.forecast_finish.isoformat()
            if c.milestone.forecast_finish
            else None,
            "days_late": c.milestone.delta_days,
        },
        "gate": c.gate,
        "critical_path": c.critical_path,
        "near_critical": c.near_critical,
        "parties": [
            {
                "key": p.key,
                "name": p.name,
                "roles": list(p.roles),
                "role_class": views.role_class(profile, p),
                "path_from_principal": views.path_from_principal(state, p.key),
            }
            for p in state.parties
        ],
        "people": [{"key": x.key, "party": x.party, "name": x.name, "title": x.title} for x in state.people],
        "items": [
            {
                "key": i.key,
                "title": i.title,
                "kind": i.kind,
                "owner": i.owner,
                "performer": i.performer,
                "status": i.status,
                "planned_start": i.planned_start.isoformat() if i.planned_start else None,
                "planned_finish": i.planned_finish.isoformat(),
                "forecast_finish": by_item[i.key].early_finish.isoformat(),
                "total_float_bd": by_item[i.key].total_float,
                "critical": by_item[i.key].critical,
                "provenance": i.provenance,
            }
            for i in state.items
        ],
        "links": [
            {
                "pred": ln.pred,
                "succ": ln.succ,
                "kind": ln.kind,
                "lag": ln.lag,
                "lag_calendar": ln.lag_calendar,
            }
            for ln in state.links
        ],
        "evidence_on_file": [
            {
                "key": e.key,
                "kind": e.kind,
                "title": e.title,
                "party": e.party,
                **{k: e.data[k] for k in EVIDENCE_FIELDS if k in e.data},
            }
            for e in state.evidence
            if e.kind != "status_report"
        ],
        "calendar_losses": [x.sentence for x in c.calendar_losses],
        "events_on_file": [
            {
                "key": e.key,
                "kind": e.kind,
                "title": e.title,
                "from": e.from_party,
                "status": state.event_status.get(e.key),
            }
            for e in state.events
        ],
    }


def event_doc(state: SiteState, e: EventRow) -> dict[str, Any]:
    return {
        "key": e.key,
        "kind": e.kind,
        "title": e.title,
        "from": e.from_party,
        "forwarded_from": e.forwarded_from,
        "received_at": e.received_at.isoformat(),
        "body": redact(e.body),
        "impacts": [
            {"item": i.item, "low_days": i.low, "high_days": i.high, "leg": i.leg} for i in e.impacts
        ],
    }


def build(
    state: SiteState, mandate: Mandate, event: EventRow, arm: Arm, ledger_tail: list[dict[str, Any]]
) -> PlanContext:
    profile = get_profile(state.profile)
    principal = state.party(state.principal)
    return PlanContext(
        principal_key=principal.key,
        principal_name=principal.name,
        as_of=state.as_of.isoformat(),
        site_state=site_state_doc(state),
        ledger_tail=ledger_tail,
        never_kinds=[k.value for k in mandate.never],
        owner_goals=list(mandate.owner_goals),
        glossary=dict(profile.glossary),
        event=event_doc(state, event),
        arm=arm,
        mandate_lines=mandate.plain_lines() if arm == Arm.informed else None,
    )
