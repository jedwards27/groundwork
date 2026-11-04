"""The plugin's tools, as plain functions over the existing services.

Claude in the app calls these through the MCP server. None of them can approve an action, confirm
a draft or issue a mandate: those happen only in the Groundwork app, as a typed action by the named
person. Outputs use the product's words: project, message, allow / ask / deny, record, receipt.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import re
import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from groundwork.agent import prompt
from groundwork.agent.wire import WirePlan, to_plan
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session, owner_session
from groundwork.ingest.site_loader import CLOSED, ImpactRow
from groundwork.ledger import append, verify_entry
from groundwork.local import drafts
from groundwork.local.home import me, page_url, set_me, slug
from groundwork.policy.terms import TEMPLATE_LABEL, MandateTerms, build_from_terms, diff_lines
from groundwork.schemas.plan import Arm, Report
from groundwork.service import actions as actions_svc
from groundwork.service import edits, overview, pipeline, planctx, runs, views
from groundwork.service import mandates as mandates_svc
from groundwork.service import projects as projects_svc

DECISION_WORD = overview.DECISION_WORD
SURFACE = "the Claude app"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
DRY_RUN_NOTE = "would have run; nothing was sent (dry run)"


class ToolError(ValueError):
    """A problem the person or Claude can fix; the message says how."""


# --- projects ----------------------------------------------------------------------------------
ProjectRef = overview.ProjectRef
_index = overview.index
_pending_asks = overview.pending_asks


def _ref(project: str) -> ProjectRef:
    idx = _index(archived=None)
    if project not in idx:
        known = ", ".join(sorted(idx)) or "none yet"
        raise ToolError(f"no project {project!r}; known projects: {known}")
    return idx[project]


def _party_name(state: Any, key: str | None) -> str | None:
    if not key:
        return None
    return next((p.name for p in state.parties if p.key == key), key)


def projects() -> dict[str, Any]:
    """Every project Groundwork tracks here, with its finish date and what waits on a person."""
    out = [overview.project_row(ref) for ref in _index().values()]
    who = me()
    return {
        "you": asdict(who) if who else None,
        "projects": out,
        "archived": [{"project": r.key, "name": r.name, "archived_at": r.archived_at} for r in _index(archived=True).values()],
        "drafts_waiting": len(drafts.pending()),
        "page": page_url(),
    }


# --- pending drafts as a forecast --------------------------------------------------------------
def _with_pending(state: Any, project: str) -> tuple[Any, list[str], int]:
    """The project as it would be if every pending draft of date changes and progress were confirmed."""
    pending = drafts.pending(project, "facts")
    if not pending:
        return state, [], 0
    impacts: dict[str, list[ImpactRow]] = {}
    progress: dict[str, dict[str, Any]] = {}
    for d in pending:
        p = d["payload"]
        for c in p.get("changes", []):
            impacts.setdefault(p["message"], []).append(
                ImpactRow(c["item"], c["low_days"], c["high_days"], "calendar", c["why"], "")
            )
        for g in p.get("progress", []):
            progress[g["item"]] = g
    events = [
        dataclasses.replace(e, impacts=tuple(e.impacts) + tuple(impacts[e.key])) if e.key in impacts else e
        for e in state.events
    ]
    items = []
    for i in state.items:
        g = progress.get(i.key)
        if g is None:
            items.append(i)
        elif g["status"] == "done":
            items.append(dataclasses.replace(i, status="done", actual_finish=date.fromisoformat(g["date"])))
        else:
            start = date.fromisoformat(g["date"])
            items.append(dataclasses.replace(i, status="in_progress", planned_start=min(start, i.planned_start or start)))
    scenario = [k for k in impacts if state.event_status.get(k) != "applied"]
    return dataclasses.replace(state, events=events, items=items), scenario, len(pending)


def _assumed_links(state: Any) -> list[tuple[str, str]]:
    raw = state.attrs.get("assumed_links", "")
    return [tuple(x.split(">", 1)) for x in raw.split(";") if ">" in x]  # type: ignore[misc]


def status(project: str) -> dict[str, Any]:
    """What one project is waiting on, what sets its finish date, the slack left and the forecast."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, project)
        chain = views.chain_view(state)
        mandate = repo.active_mandate(s, ref.site_id)
        asks = _pending_asks(s, state)
    ms = chain.milestone
    titles = {i.key: i.title for i in chain.items}
    gate = next((i for i in chain.items if i.key == chain.gate), None)
    open_items = sorted(
        (i for i in chain.items if i.status not in CLOSED),
        key=lambda i: (i.total_float if i.total_float is not None else 10_000, i.early_finish),
    )
    played = {k for k, v in state.event_status.items() if v != "available"}
    critical = set(chain.critical_path)
    pending_state, scenario, n_pending = _with_pending(state, project)
    if_confirmed = None
    if n_pending:
        pm = views.chain_view(pending_state, scenario=scenario).milestone
        if_confirmed = {
            "forecast": str(pm.forecast_finish),
            "range": [str(pm.forecast_low), str(pm.forecast_high)],
            "drafts": n_pending,
            "note": "What the forecast would be if you confirm the pending date changes and progress.",
        }
    return {
        "project": project,
        "name": state.name,
        "as_of": str(state.as_of),
        "finish": {
            "label": ms.label,
            "target": str(ms.target_date),
            "forecast": str(ms.forecast_finish),
            "range": [str(ms.forecast_low), str(ms.forecast_high)],
            "days_late": ms.delta_days,
        },
        "if_pending_confirmed": if_confirmed,
        "sets_the_date": None
        if gate is None
        else {
            "item": gate.key,
            "title": gate.title,
            "owner": _party_name(state, gate.owner),
            "due": str(gate.early_finish),
            "slack_days": gate.total_float,
        },
        "critical_path": [titles[k] for k in chain.critical_path],
        "waiting_on": [
            {
                "item": i.key,
                "title": i.title,
                "owner": _party_name(state, i.owner),
                "status": i.status,
                "due": str(i.early_finish),
                "planned": str(i.planned_finish),
                "slack_days": i.total_float,
                "critical": i.critical,
            }
            for i in open_items[:12]
        ],
        "more_open_steps": max(0, len(open_items) - 12),
        "steps_total": len(chain.items),
        "every_step": "Call steps() for every step, including done and cancelled ones.",
        "past_plan_no_word": [
            {"item": k, "title": titles.get(k, k), "days_past": d, "on_the_finish_path": k in critical or next((i.on_target_path for i in chain.items if i.key == k), False)}
            for k, d in sorted(chain.stale.items(), key=lambda kv: -kv[1])
        ],
        "archived": ref.archived_at,
        "assumed_links": [
            {
                "before": titles.get(a, a),
                "after": titles.get(b, b),
                "keys": [a, b],
                "on_critical_path": a in critical and b in critical,
            }
            for a, b in _assumed_links(state)
        ],
        "messages_not_played": [
            {
                "message": e.key,
                "title": e.title,
                "from": _party_name(state, e.from_party) or e.from_party,
                "received": e.received_at.isoformat(),
                "scripted_demo": e.scripted,
            }
            for e in sorted(state.events, key=lambda e: e.received_at)
            if e.key not in played and state.event_status.get(e.key) != "moved"
        ],
        "mandate": {
            "template": TEMPLATE_LABEL.get(mandate.preset, mandate.preset),
            "version": mandate.version,
            "valid_until": str(mandate.valid_until) if mandate.valid_until else None,
            "lines": mandate.plain_lines(),
            "dry_run": mandate.dry_run,
        },
        "asks_waiting": len(asks),
        "page": page_url(f"projects/{project}"),
        "clock_note": "The project's date (as_of) moves forward to each recorded message's date, and with check_overdue.",
    }


def steps(project: str, status: Literal["all", "open", "done", "cancelled", "past_due"] = "all") -> dict[str, Any]:
    """Every step in a project, done and cancelled ones included, with its owner, kind, status,
    dates, source and the steps it waits on. Use this, not status(), to list or check all steps."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, project)
    chain = views.chain_view(state)
    preds: dict[str, list[str]] = {}
    for ln in state.links:
        preds.setdefault(ln.succ, []).append(ln.pred)
    rows = []
    for i in sorted(chain.items, key=lambda i: (i.actual_finish or i.early_finish, i.key)):
        past_due = i.status not in CLOSED and i.planned_finish < state.as_of
        if status == "open" and i.status in CLOSED:
            continue
        if status in ("done", "cancelled") and i.status != status:
            continue
        if status == "past_due" and not past_due:
            continue
        rows.append(
            {
                "item": i.key,
                "title": i.title,
                "kind": i.kind,
                "owner": _party_name(state, i.owner),
                "status": i.status,
                "start": str(i.planned_start) if i.planned_start else None,
                "planned": str(i.planned_finish),
                "finished": str(i.actual_finish) if i.actual_finish else None,
                "forecast": None if i.status in CLOSED else str(i.early_finish),
                "estimated": i.estimated,
                "past_due_no_word": chain.stale.get(i.key),
                "waits_on": preds.get(i.key, []),
                "source": i.source,
                "notes": i.notes,
            }
        )
    counts: dict[str, int] = {}
    for i in chain.items:
        counts[i.status] = counts.get(i.status, 0) + 1
    return {"project": project, "total": len(chain.items), "by_status": counts, "shown": len(rows), "steps": rows, "page": page_url(f"projects/{project}/steps")}


# --- playing a message ---------------------------------------------------------------------------
def _run_result(org_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Any]:
    with org_session(org_id) as s:
        run = s.get(m.Run, run_id)
        assert run is not None
        site = s.get(m.Site, run.site_id)
        assert site is not None
        state = repo.load_state(s, site.key)
        plan_row = actions_svc.primary_plan(s, run_id)
        actions = actions_svc.plan_view(s, state, plan_row)["actions"] if plan_row else []
        summary = dict(run.summary or {})
        status_ = run.status
    names = {p.key: p.name for p in state.parties} | {p.key: p.name for p in state.people}
    before, after = summary.get("milestone_before") or {}, summary.get("milestone_after") or {}
    return {
        "run": str(run_id),
        "status": status_,
        "forecast": {
            "before": before.get("forecast_finish"),
            "after": after.get("forecast_finish"),
            "sets_the_date": after.get("gate_title"),
        },
        "actions": [
            {
                "ref": a["ref"],
                "title": a["title"],
                "decision": DECISION_WORD.get(a["decision"] or "", a["decision"]),
                "clause": a["clause"],
                "route": [state.party(state.principal).name] + [names.get(k) or k for k in a["path"]],
                "approvers": [names.get(k) or k for k in a["approvers"]],
                "state": a["state"],
                "outcome": DRY_RUN_NOTE if a["state"] == "executed" else a["state"],
                "proposed": DECISION_WORD.get(a["proposed_autonomy"], a["proposed_autonomy"]),
            }
            for a in actions
        ],
        "report_check": summary.get("report_check"),
        "approve_on": page_url() if any(a["state"] == "pending" for a in actions) else None,
        "dry_run_note": "Dry run: allowed actions are recorded as would-have-sent; nothing left this computer.",
    }


def play_message(project: str, message: str) -> dict[str, Any]:
    """Play a message that is already in a project's inbox. The scripted demo message plays its
    hand-written plan end to end. Any other message returns what Claude needs to write a plan."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, project)
        if message not in state.event_status:
            raise ToolError(
                f"no message {message!r} in {project}. Record new mail with record_message first; "
                "status() lists the messages not yet played."
            )
        if state.event_status[message] != "available":
            raise ToolError(f"message {message!r} has already been played")
        event = state.event(message)
        if event.scripted or event.kind == "acknowledgment":
            run_id = runs.start_run(s, project, message, person_id=None)
        else:
            mandate = repo.active_mandate(s, ref.site_id)
            ctx = planctx.build(state, mandate, event, Arm.informed, pipeline.ledger_tail(s))
            return {
                "needs_plan": True,
                "instructions": prompt.system_text(ctx),
                "executors": prompt.EXECUTORS_DOC,
                "site_state": ctx.site_state,
                "message": ctx.event,
                "recent_records": ctx.ledger_tail,
                "next": f"Write a plan for this message and call propose_plan(project={project!r}, "
                f"message={message!r}, plan=..., model=<your model id>). Propose; the gateway decides."
                + (" A completion is a cue for next steps: close-out, final invoice, the next inspection." if event.kind == "progress" else ""),
            }
    pipeline.execute_run(ref.org_id, run_id, force_simulated=True)
    out = _run_result(ref.org_id, run_id)
    if event.kind == "acknowledgment":
        out["note"] = (
            "An acknowledgment (an 'approved, please proceed' reply) changes nothing and has no plan. "
            "If this message reports work finished or started, record it again as kind 'progress'."
        )
    return out | ({"scripted": True} if event.scripted else {})


def propose_plan(project: str, message: str, plan: WirePlan, model: str) -> dict[str, Any]:
    """Run the gateway on Claude's plan for one message: each action is allowed, asked or denied
    under the project's mandate, allowed actions run in dry run, and every step is recorded."""
    ref = _ref(project)
    domain_plan = to_plan(plan)
    with org_session(ref.org_id) as s:
        try:
            run_id = runs.start_run(s, project, message, person_id=None)
        except KeyError as exc:
            raise ToolError(
                f"no message {message!r} in {project}. A plan needs a recorded message: call "
                "record_message (or check_overdue) first, then play_message, then propose_plan."
            ) from exc
        except runs.RunConflict as exc:
            raise ToolError(f"{exc}. Each message is planned once.") from exc
    pipeline.play_external_plan(
        ref.org_id, run_id, domain_plan, planner=SURFACE, model_id=f"{model or 'unknown model'} (self-reported)"
    )
    return _run_result(ref.org_id, run_id) | {
        "next": "Tell the person each decision with its clause, then call submit_report with what "
        "you did, asked and were denied, using only what this result shows."
    }


def submit_report(run: str, report: Report) -> dict[str, Any]:
    """Record your own report of a run you planned. It is checked against the ledger line by line."""
    try:
        run_id = uuid.UUID(run)
    except ValueError as exc:
        raise ToolError(f"{run!r} is not a run id; use the run id propose_plan returned") from exc
    with owner_session() as s:
        row = s.get(m.Run, run_id)
        if row is None:
            raise ToolError(f"no run {run}")
        org_id, run_status = row.org_id, row.status
        has_plan = actions_svc.primary_plan(s, run_id) is not None
    if not has_plan:
        return {
            "report_matches_ledger": None,
            "note": "This run had no plan (an acknowledgment changes nothing), so there is nothing to report.",
        }
    if run_status != "waiting_model":
        raise ToolError(f"run {run} is {run_status}; its report is already recorded, or it was not planned in the app")
    check = pipeline.submit_external_report(org_id, run_id, report, reporter=SURFACE)
    return {"report_matches_ledger": check.ok, "check": check.as_dict()}


# --- messages from the person's own inbox, and the clock ----------------------------------------
class DateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(description="The schedule item the message delays (its key from status()).")
    low_days: int = Field(ge=0, description="Shortest likely delay, in calendar days.")
    high_days: int = Field(ge=0, description="Longest likely delay, in calendar days.")
    why: str = Field(description="The sentence in the message that says so, quoted or closely paraphrased.")


class Progress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(description="The schedule item (its key from status()).")
    status: Literal["done", "in_progress"]
    date: _dt.date = Field(description="When it finished (done) or started (in_progress).")
    why: str = Field(description="The sentence in the message that says so.")


def _route(emails: set[str], thread: str | None, text: str = "") -> tuple[set[str], str]:
    """Projects a message belongs to, and how that was decided. Archived projects never match.

    1. Same email thread as a message already on a project.
    2. The sender or a recipient is a person on the project.
    3. If people match more than one project, the one whose name the subject or body mentions.
    Otherwise every match comes back, and the person is asked."""
    who = me()
    mine = {who.email} if who else set()
    active = _index()
    with owner_session() as s:
        if thread:
            hits = {
                site.key
                for site, _ev in s.execute(
                    select(m.Site, m.Event).join(m.Event, m.Event.site_id == m.Site.id).where(m.Event.message_ref == f"thread:{thread}")
                ).all()
                if site.key in active
            }
            if hits:
                return hits, "same email thread as an earlier message"
        people = s.execute(select(m.Person).where(m.Person.email.in_(emails - mine))).scalars().all()
        sites = {
            site.key
            for p in people
            for site in s.execute(
                select(m.Site)
                .join(m.SiteParty, m.SiteParty.site_id == m.Site.id)
                .where(m.SiteParty.party_id == p.party_id)
            ).scalars()
            if site.key in active
        }
    if len(sites) > 1 and text:
        low = text.lower()
        named = {k for k in sites if active[k].name.lower() in low}
        if len(named) == 1:
            return named, "people are on more than one project; the message names this one"
    return sites, "the sender or a recipient is a person on the project"


def _advance(ref: ProjectRef, state: Any, to: date, why: str) -> bool:
    """Move a live project's date forward (never back). Returns True if it moved."""
    if state.attrs.get("live") != "true" or to <= state.as_of:
        return False
    with owner_session() as s:
        site = s.get(m.Site, ref.site_id)
        assert site is not None
        site.as_of = to
        append(s, "clock_advanced", {"from": str(state.as_of), "to": str(to), "why": why}, org_id=ref.org_id)
    return True


def record_message(
    subject: str,
    body: str,
    received_at: str,
    from_email: str = "",
    to_emails: list[str] | None = None,
    cc_emails: list[str] | None = None,
    thread_id: str | None = None,
    link: str | None = None,
    project: str | None = None,
    kind: Literal["schedule_change", "progress", "evidence", "acknowledgment"] = "evidence",
    source: Literal["email", "portal", "call", "note"] = "email",
    date_changes: list[DateChange] | None = None,
    progress: list[Progress] | None = None,
) -> dict[str, Any]:
    """Add a message to the right project: an email from the person's own inbox (read-only), a
    result from a public portal, a call or a note. Routing goes by email thread, then by who sent
    or received it; for portal results, calls, notes or unclear mail, pass `project`. Date changes
    and progress are drafts until the person confirms them in the Groundwork app."""
    try:
        when = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError("received_at must be an ISO date and time, for example 2023-03-27T10:00:00-08:00") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    emails = {e.lower() for e in EMAIL.findall(" ".join([from_email, *(to_emails or []), *(cc_emails or [])]))}
    if project:
        targets, how = {project}, "chosen by the person"
    elif source != "email":
        raise ToolError(f"a {source} has no email addresses to route by; pass project=...")
    else:
        targets, how = _route(emails, thread_id, f"{subject}\n{body}")
    if len(targets) != 1:
        return {
            "recorded": False,
            "candidates": sorted(targets),
            "reason": "the people on it are on more than one project, and the thread and subject don't say which"
            if targets
            else "no active project knows these addresses",
            "next": "Ask the person which project this belongs to (or whether to ignore it), then call "
            "record_message again with project=...",
        }
    key = targets.pop()
    ref = _ref(key)
    changes, steps = list(date_changes or []), list(progress or [])
    if steps and kind in ("acknowledgment", "evidence"):
        kind = "progress"  # a completion or a start is progress, and it gets a plan
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, key)
        sender = next((p for p in state.people if p.email and p.email.lower() == from_email.lower()), None) if from_email else None
        item_keys = {i.key for i in state.items}
        for c in [*changes, *steps]:
            if c.item not in item_keys:
                raise ToolError(f"{c.item!r} is not an item in {key}; status() lists the item keys")
        base = f"msg-{when.date().isoformat()}-{slug(subject)[:32]}"
        event_key, n = base, 2
        while event_key in state.event_status:
            event_key, n = f"{base}-{n}", n + 1
        s.add(
            m.Event(
                org_id=ref.org_id,
                site_id=ref.site_id,
                key=event_key,
                kind=kind,
                title=subject[:200],
                from_party=sender.party if sender else "public",
                forwarded_from=None,
                received_at=when,
                body=body,
                message_ref=f"thread:{thread_id}" if thread_id else None,
                evidence_key=None,
                links=sorted({c.item for c in [*changes, *steps]}),
                impacts=[],
                provenance="public" if source == "portal" else "message",
                source=link or source,
                note="" if source == "email" else f"source: {source}",
                status="available",
                scripted=False,
            )
        )
        s.flush()
        append(
            s,
            "message_recorded",
            {"message": event_key, "subject": subject, "from": from_email or source, "routed": how, "thread": thread_id, "source": source},
        )
    moved = _advance(ref, state, when.date(), f"message {event_key}")
    draft = None
    if changes or steps:
        draft = drafts.create(
            "facts",
            key,
            f"From “{subject}”",
            {
                "message": event_key,
                "changes": [c.model_dump() for c in changes],
                "progress": [g.model_dump(mode="json") for g in steps],
            },
        )
    return {
        "recorded": True,
        "project": key,
        "message": event_key,
        "kind": kind,
        "routed": how,
        "project_date": str(when.date()) if moved else str(state.as_of),
        "to_confirm": None
        if draft is None
        else {"draft": draft["id"], "confirm_on": page_url(), "note": "Dates and progress change only after the person confirms."},
        "next": f"Call play_message(project={key!r}, message={event_key!r}) to plan any follow-ups.",
    }


def check_overdue(project: str, as_of: date | None = None) -> dict[str, Any]:
    """The clock: move the project's date forward (for a backtest, or to today) and list what is
    past due with no word. When something is overdue, a message is recorded so you can plan chases."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, project)
    today = as_of or date.today()
    moved = _advance(ref, state, today, "check_overdue")
    if moved:
        with org_session(ref.org_id) as s:
            state = repo.load_state(s, project)
    names = {p.key: p.name for p in state.parties}
    overdue = sorted(
        (i for i in state.items if i.status not in CLOSED and i.planned_finish < state.as_of),
        key=lambda i: i.planned_finish,
    )
    if not overdue:
        return {"project": project, "project_date": str(state.as_of), "overdue": [], "next": "Nothing is past due."}
    lines = [f"- {i.title} (owner: {names.get(i.owner, i.owner)}), due {i.planned_finish}, no update since" for i in overdue]
    message_key = f"clock-{state.as_of.isoformat()}"
    if message_key not in state.event_status:
        with org_session(ref.org_id) as s:
            s.add(
                m.Event(
                    org_id=ref.org_id,
                    site_id=ref.site_id,
                    key=message_key,
                    kind="evidence",
                    title=f"Past due on {state.as_of}: {', '.join(i.title for i in overdue[:3])}" + ("…" if len(overdue) > 3 else ""),
                    from_party="public",
                    forwarded_from=None,
                    received_at=datetime.combine(state.as_of, datetime.min.time(), tzinfo=UTC),
                    body="These items are past their planned date with no update:\n" + "\n".join(lines),
                    message_ref=None,
                    evidence_key=None,
                    links=[i.key for i in overdue],
                    impacts=[],
                    provenance="clock",
                    source="check_overdue",
                    note="",
                    status="available",
                    scripted=False,
                )
            )
            append(s, "overdue_found", {"as_of": str(state.as_of), "items": [i.key for i in overdue]})
    return {
        "project": project,
        "project_date": str(state.as_of),
        "overdue": [
            {"item": i.key, "title": i.title, "owner": names.get(i.owner, i.owner), "due": str(i.planned_finish)} for i in overdue
        ],
        "message": message_key,
        "next": f"Call play_message(project={project!r}, message={message_key!r}) to plan chases for these.",
    }


def move_message(project: str, message: str, to_project: str) -> dict[str, Any]:
    """Correct a misrouted message: it moves to another project, and both ledgers record the move."""
    src, dst = _ref(project), _ref(to_project)
    with org_session(src.org_id) as s:
        state = repo.load_state(s, project)
        if state.event_status.get(message) != "available":
            raise ToolError(f"{message!r} is not an unplayed message in {project}")
        row = s.execute(
            select(m.Event).where(m.Event.site_id == src.site_id, m.Event.key == message)
        ).scalar_one()
        copy = {c: getattr(row, c) for c in ("kind", "title", "received_at", "body", "message_ref", "source")}
        row.status = "moved"
        append(s, "message_moved", {"message": message, "to": to_project})
    with org_session(dst.org_id) as s:
        s.add(
            m.Event(
                org_id=dst.org_id,
                site_id=dst.site_id,
                key=message,
                from_party="public",
                forwarded_from=None,
                evidence_key=None,
                links=[],
                impacts=[],
                provenance="message",
                note=f"moved from {project}",
                status="available",
                scripted=False,
                **copy,
            )
        )
        append(s, "message_moved_in", {"message": message, "from": project})
    return {"moved": True, "message": message, "to": to_project}


# --- links and people ----------------------------------------------------------------------------
class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before: str = Field(description="Item key that must finish first.")
    after: str = Field(description="Item key that waits for it.")


def change_links(
    project: str, why: str, add: list[Link] | None = None, remove: list[Link] | None = None, confirm: list[Link] | None = None
) -> dict[str, Any]:
    """Draft changes to what waits on what: add or remove a dependency, or confirm one that was
    inferred during setup. Nothing changes until the person confirms in the Groundwork app."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, project)
    keys = {i.key for i in state.items}
    existing = {(ln.pred, ln.succ) for ln in state.links}
    for ln in [*(add or []), *(remove or []), *(confirm or [])]:
        for k in (ln.before, ln.after):
            if k not in keys:
                raise ToolError(f"{k!r} is not an item in {project}")
    for ln in [*(remove or []), *(confirm or [])]:
        if (ln.before, ln.after) not in existing:
            raise ToolError(f"there is no link from {ln.before} to {ln.after} in {project}")
    if not (add or remove or confirm):
        raise ToolError("nothing to change: pass add, remove or confirm")
    d = drafts.create(
        "links",
        project,
        f"Change links in {state.name}",
        {
            "why": why,
            "add": [ln.model_dump() for ln in add or []],
            "remove": [ln.model_dump() for ln in remove or []],
            "confirm": [ln.model_dump() for ln in confirm or []],
        },
    )
    return {"draft": d["id"], "confirm_on": page_url(), "next": "Ask the person to confirm in the Groundwork app."}


PersonIn = projects_svc.PersonIn


def add_people(project: str, party: str, people: list[PersonIn], why: str) -> dict[str, Any]:
    """Draft new people on a party, including your own side (party 'you'), so their mail routes to
    the project. They never become approvers. Confirmed in the Groundwork app."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, project)
    if party not in {p.key for p in state.parties}:
        raise ToolError(f"{party!r} is not a party in {project}; parties: {', '.join(p.key for p in state.parties)}")
    d = drafts.create(
        "people",
        project,
        f"Add {', '.join(p.name for p in people)} to {_party_name(state, party)}",
        {"party": party, "people": [p.model_dump() for p in people], "why": why},
    )
    return {"draft": d["id"], "confirm_on": page_url(), "next": "Ask the person to confirm in the Groundwork app."}


# --- mandates ----------------------------------------------------------------------------------
def draft_mandate(project: str, words: str, terms: MandateTerms) -> dict[str, Any]:
    """Draft a new mandate version from the person's own words. It changes nothing until the
    person confirms it in the Groundwork app; you can never confirm or widen a mandate yourself."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, project)
        current = repo.active_mandate(s, ref.site_id)
    people = {p.key for p in state.people}
    for who in (terms.approvers or []) + (terms.legal_approvers or []):
        if who not in people:
            raise ToolError(f"{who!r} is not a person on {project}; people: {', '.join(sorted(people))}")
    new, notes = build_from_terms(current, terms, valid_from=state.as_of)
    draft = drafts.create(
        "mandate",
        project,
        f"Mandate v{new.version} for {state.name}",
        {
            "words": words,
            "terms": terms.model_dump(mode="json"),
            "base_version": current.version,
            "doc": new.model_dump(mode="json"),
            "lines": new.plain_lines(),
            "diff": diff_lines(current, new),
            "notes": notes,
        },
    )
    return {
        "draft": draft["id"],
        "version": new.version,
        "template": TEMPLATE_LABEL.get(new.preset, new.preset),
        "lines": new.plain_lines(),
        "changes": diff_lines(current, new),
        "notes": notes,
        "confirm_on": page_url(),
        "next": "Show the person the changes and ask them to confirm in the Groundwork app.",
    }


# --- new projects ------------------------------------------------------------------------------
PartyIn = projects_svc.PartyIn
ItemIn = projects_svc.ItemIn
ProjectDraft = projects_svc.ProjectDraft


def _project_folder(d: ProjectDraft, key: str) -> Any:
    from groundwork.local.home import home

    who = me()
    if who is None:
        raise ToolError("run setup first, so Groundwork knows who approves on your projects")
    owner = projects_svc.Owner(who.name, who.email, who.organization)
    return projects_svc.write_folder(d, key, home() / "projects" / key, owner, f"Groundwork project: {d.name}")


def start_project(draft: ProjectDraft) -> dict[str, Any]:
    """Draft a new project from what the person told you, their tracker or their email. It is
    checked here and created only when the person confirms it in the Groundwork app. Calling it again
    for the same project replaces the earlier draft."""
    from groundwork.ingest import load_site
    from groundwork.ingest.site_loader import LoadError

    key = slug(draft.name)
    if key in _index(archived=None):
        raise ToolError(
            f"a project called {key!r} already exists. To change it, use edit_steps (add, change, cancel or remove "
            "steps), edit_project (name, finish, parties) or add_people; to start over, archive_project or "
            "delete_project it first, or pick another name."
        )
    folder = _project_folder(draft, key)
    try:
        bundle = load_site(folder)
    except LoadError as exc:
        return {"created": False, "problems": list(exc.problems), "next": "Fix these and call start_project again."}
    state = views.chain_view(_state_from_bundle(bundle))
    replaced = [d["id"] for d in drafts.pending(key, "project")]
    for old in replaced:
        drafts.resolve(old, "superseded", "groundwork")
    titles = {i.key: i.title for i in state.items}
    assumed = [f"{titles[b]} before {titles[it.key]}" for it in draft.items for b in it.assumed_depends_on]
    shared = projects_svc.overlaps(
        {x.email for p in draft.parties for x in p.people} | {x.email for x in draft.your_side},
        {p.name for p in draft.parties},
    )
    d = drafts.create(
        "project",
        key,
        f"New project: {draft.name}",
        {
            "folder": str(folder),
            "items": len(bundle.items),
            "parties": [p.name for p in bundle.parties],
            "finish": draft.finish_label,
            "target": draft.finish_target.isoformat(),
            "as_of": str(bundle.as_of),
            "forecast": str(state.milestone.forecast_finish),
            "sets_the_date": titles.get(state.gate or ""),
            "assumed_links": assumed,
            "template": draft.template,
            "overlaps": shared,
        },
    )
    return {
        "draft": d["id"],
        "replaced_drafts": replaced,
        "overlaps": shared,
        "overlap_note": "These people or parties are also on other projects. Mail from them goes to the project "
        "whose email thread it continues, or whose name it mentions; otherwise you'll be asked. If this is the "
        "same project as one of these, change that one instead."
        if shared
        else None,
        "project": key,
        "forecast": str(state.milestone.forecast_finish),
        "sets_the_date": d["payload"]["sets_the_date"],
        "assumed_links": assumed,
        "confirm_on": page_url(),
        "next": "Show the person the draft, including the links you inferred, and ask them to confirm it in the Groundwork app.",
    }


def _state_from_bundle(bundle: Any) -> Any:
    from groundwork.service.state import SiteState

    return SiteState.from_bundle(bundle)


# --- changing a project after it exists --------------------------------------------------------
StepChange = edits.StepChange
ProjectChange = edits.ProjectChange


def _forecast_line(state: Any) -> dict[str, Any]:
    chain = views.chain_view(state)
    ms = chain.milestone
    gate = next((i.title for i in chain.items if i.key == chain.gate), None)
    return {"forecast": str(ms.forecast_finish), "range": [str(ms.forecast_low), str(ms.forecast_high)], "sets_the_date": gate}


def edit_steps(
    project: str,
    why: str,
    add: list[ItemIn] | None = None,
    change: list[StepChange] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    """Draft changes to a project's steps: add new ones, change any field (title, kind, owner,
    status, dates, estimated, what it waits on, notes), mark one cancelled (descoped: kept on record,
    ignored by the forecast) or remove one entered by mistake. Nothing changes until the person
    confirms in the Groundwork app. Prefer cancelled over remove for anything that really happened."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, project)
    payload = {
        "why": why,
        "add": [x.model_dump(mode="json") for x in add or []],
        "change": [x.model_dump(mode="json", exclude_none=True) for x in change or []],
        "remove": list(remove or []),
    }
    if not (payload["add"] or payload["change"] or payload["remove"]):
        raise ToolError("nothing to change: pass add, change or remove")
    try:
        after = edits.apply_steps_to_state(state, payload)
    except edits.EditProblem as exc:
        raise ToolError(str(exc)) from exc
    payload["before"], payload["after"] = _forecast_line(state), _forecast_line(after)
    titles = {i.key: i.title for i in state.items}
    payload["titles"] = {k: titles.get(k, k) for k in [*payload["remove"], *(c["key"] for c in payload["change"])]}
    n = len(payload["add"]) + len(payload["change"]) + len(payload["remove"])
    d = drafts.create("steps", project, f"Change {n} {'step' if n == 1 else 'steps'} in {state.name}", payload)
    return {
        "draft": d["id"],
        "forecast_now": payload["before"],
        "forecast_if_confirmed": payload["after"],
        "confirm_on": page_url(),
        "next": "Ask the person to confirm in the Groundwork app.",
    }


def edit_project(project: str, why: str, change: ProjectChange) -> dict[str, Any]:
    """Draft changes to a project's details: its name, location, finish (label, target date or the
    step that marks it), parties (add or rename) or the earlier project it follows on from. The
    project's key stays the same. Confirmed in the Groundwork app."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, project)
    payload = {"why": why, "change": change.model_dump(mode="json", exclude_defaults=True)}
    if not payload["change"]:
        raise ToolError("nothing to change")
    try:
        after = edits.apply_project_to_state(state, payload, set(_index(archived=None)))
    except edits.EditProblem as exc:
        raise ToolError(str(exc)) from exc
    payload["before"], payload["after"] = _forecast_line(state), _forecast_line(after)
    payload["current"] = {"name": state.name, "finish_label": state.milestones[0].label, "finish_target": str(state.milestones[0].target_date)}
    d = drafts.create("project_edit", project, f"Change {state.name}", payload)
    return {"draft": d["id"], "forecast_if_confirmed": payload["after"], "confirm_on": page_url(), "next": "Ask the person to confirm in the Groundwork app."}


def archive_project(project: str, why: str, restore: bool = False) -> dict[str, Any]:
    """Draft archiving a project (or restoring an archived one). Archiving hides it from home and
    from mail routing; nothing is deleted. Use it for a duplicate, a finished project or one to park.
    Confirmed in the Groundwork app."""
    ref = _ref(project)
    if restore != bool(ref.archived_at):
        raise ToolError(f"{project} is {'already active' if restore else 'already archived'}")
    verb = "Restore" if restore else "Archive"
    d = drafts.create("archive", project, f"{verb} {ref.name}", {"why": why, "restore": restore})
    return {"draft": d["id"], "confirm_on": page_url(), "next": "Ask the person to confirm in the Groundwork app."}


def delete_project(project: str, why: str) -> dict[str, Any]:
    """Draft deleting a project for good, with its messages and ledger. The person confirms in the
    Groundwork app by typing the project's key. Suggest archive_project first unless they're sure."""
    ref = _ref(project)
    d = drafts.create("delete", project, f"Delete {ref.name} for good", {"why": why})
    return {"draft": d["id"], "confirm_on": page_url(), "next": "Ask the person to confirm in the Groundwork app; they type the project's key to delete it."}


# --- pending work, activity, the ledger and receipts ---------------------------------------------
def pending() -> dict[str, Any]:
    """Every ask waiting for a named person, and every draft waiting for confirmation."""
    asks = []
    for ref in _index().values():
        with org_session(ref.org_id) as s:
            state = repo.load_state(s, ref.key)
            names = {p.key: p.name for p in state.people}
            for a in _pending_asks(s, state):
                asks.append(
                    {
                        "project": ref.key,
                        "ref": a["ref"],
                        "title": a["title"],
                        "clause": a["clause"],
                        "approvers": [names.get(k) or k for k in a["approvers"]],
                    }
                )
    return {
        "asks": asks,
        "drafts": [{"draft": d["id"], "kind": d["kind"], "project": d["project"], "title": d["title"]} for d in drafts.pending()],
        "page": page_url(),
    }


def recent_runs(limit: int = 8) -> list[dict[str, Any]]:
    """The latest runs across projects, newest first, with their allow / ask / deny counts."""
    return overview.recent_runs(_index().values(), limit)


def ledger(project: str, last: int = 15) -> dict[str, Any]:
    """The latest records in a project's ledger: every proposal, decision, approval and outcome."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        rows = list(s.execute(select(m.LedgerEntry).order_by(m.LedgerEntry.seq.desc()).limit(max(1, min(last, 100)))).scalars())
    return {
        "project": project,
        "records": [
            {
                "record": r.seq,
                "type": r.entry_type,
                "at": r.recorded_at,
                "summary": r.payload.get("title") or r.payload.get("subject") or r.payload.get("reason") or "",
                "decision": DECISION_WORD.get(r.payload.get("decision", ""), r.payload.get("decision")),
                **({"note": DRY_RUN_NOTE} if r.entry_type == "executed" and r.payload.get("dry_run") else {}),
            }
            for r in reversed(rows)
        ],
        "page": page_url(f"projects/{project}/ledger"),
    }


def verify_record(project: str, record: int, copy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check one ledger record (a receipt): its hash is recomputed, and a copy, if given, is compared."""
    ref = _ref(project)
    with org_session(ref.org_id) as s:
        return verify_entry(s, record, copy)


def setup(name: str, email: str, organization: str = "") -> dict[str, Any]:
    """Say who you are, once: the named person who approves and confirms on this computer."""
    try:
        who = set_me(name, email, organization)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return {"you": asdict(who), "page": page_url(), "demo_project": "lake-mariner"}


# Re-exported for the page.
issue_mandate = mandates_svc.issue
