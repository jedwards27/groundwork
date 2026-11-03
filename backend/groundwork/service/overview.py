"""Across projects: which ones exist, what waits on a person, and the latest runs.

The plugin's tools and the web app's home view both read these. A caller passes the orgs it may
see; the plugin, which runs for the one person at this computer, passes none and sees every
project. Each project is read in its own org's session.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session, owner_session
from groundwork.policy.terms import TEMPLATE_LABEL
from groundwork.service import actions as actions_svc
from groundwork.service import views

DECISION_WORD = {"auto": "allow", "ask": "ask", "refuse": "deny"}


@dataclass(frozen=True)
class ProjectRef:
    key: str
    name: str
    org_id: uuid.UUID
    site_id: uuid.UUID


def index(orgs: set[uuid.UUID] | None = None) -> dict[str, ProjectRef]:
    """Projects by key. Sandboxes (hosted visitors' copies) are left out unless asked for by org."""
    with owner_session() as s:
        q = select(m.Site).join(m.Org, m.Org.id == m.Site.org_id)
        q = q.where(m.Site.org_id.in_(orgs)) if orgs is not None else q.where(m.Org.expires_at.is_(None))
        return {r.key: ProjectRef(r.key, r.name, r.org_id, r.id) for r in s.execute(q.order_by(m.Site.name)).scalars()}


def ref_for_action(action_id: uuid.UUID) -> ProjectRef | None:
    with owner_session() as s:
        action = s.get(m.Action, action_id)
        run = s.get(m.Run, action.run_id) if action is not None else None
        site = s.get(m.Site, run.site_id) if run is not None else None
        return ProjectRef(site.key, site.name, site.org_id, site.id) if site is not None else None


def pending_asks(s: Any, state: Any) -> list[dict[str, Any]]:
    """Every action waiting for a named person's approval, across the project's runs."""
    out: list[dict[str, Any]] = []
    for r in s.execute(select(m.Run).where(m.Run.site_id == state.site_id).order_by(m.Run.created_at)).scalars():
        p = actions_svc.primary_plan(s, r.id)
        if p is not None:
            out += [
                a | {"run_id": str(r.id), "run_at": r.created_at.isoformat()}
                for a in actions_svc.plan_view(s, state, p)["actions"]
                if a["state"] == "pending"
            ]
    return out


def text_of(params: dict[str, Any] | None) -> tuple[str, str]:
    """(subject, text) of an action as it would go out."""
    params = params or {}
    subject = params.get("subject") or params.get("document_title") or params.get("package_title") or ""
    text = params.get("body") or params.get("agenda") or params.get("summary") or params.get("decision") or params.get("scope") or ""
    return str(subject), str(text)


def project_row(ref: ProjectRef) -> dict[str, Any]:
    """One project's finish forecast, what sets the date, its mandate and the asks waiting."""
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, ref.key)
        summary = views.site_summary(state)
        mandate = repo.active_mandate(s, ref.site_id)
        asks = len(pending_asks(s, state))
    ms = summary.milestone
    return {
        "project": ref.key,
        "name": ref.name,
        "location": state.location,
        "as_of": str(state.as_of),
        "finish": ms.label,
        "target": str(ms.target_date),
        "forecast": str(ms.forecast_finish),
        "days_late": ms.delta_days,
        "sets_the_date": summary.gate_title,
        "asks_waiting": asks,
        "mandate": f"{TEMPLATE_LABEL.get(mandate.preset, mandate.preset)} v{mandate.version}",
        "dry_run": mandate.dry_run,
    }


def recent_runs(refs: Iterable[ProjectRef], limit: int = 8) -> list[dict[str, Any]]:
    """The latest runs across projects, newest first, with their allow / ask / deny counts."""
    out = []
    for ref in refs:
        with org_session(ref.org_id) as s:
            rows = list(
                s.execute(select(m.Run).where(m.Run.site_id == ref.site_id).order_by(m.Run.created_at.desc()).limit(limit)).scalars()
            )
            for r in rows:
                event = s.get(m.Event, r.event_id)
                counts = {"allow": 0, "ask": 0, "deny": 0}
                decided = s.execute(
                    select(m.Decision)
                    .join(m.Action, m.Action.id == m.Decision.action_id)
                    .where(m.Action.run_id == r.id, m.Action.arm == "informed")
                ).scalars()
                for d in decided:
                    word = DECISION_WORD.get(d.decision, d.decision)
                    counts[word] = counts.get(word, 0) + 1
                check = (r.summary or {}).get("report_check") or {}
                out.append(
                    {
                        "project": ref.key,
                        "project_name": ref.name,
                        "run": str(r.id),
                        "message": event.title if event else "",
                        "at": r.created_at.isoformat(),
                        "status": r.status,
                        "counts": counts,
                        "report_ok": check.get("ok"),
                    }
                )
    return sorted(out, key=lambda x: x["at"], reverse=True)[:limit]
