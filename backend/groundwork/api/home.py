"""The web app's home view: what needs you across your projects, the projects, the latest runs;
and, in the plugin's local runtime, deciding the drafts Claude prepared."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from groundwork.api.viewer import Viewer, viewer
from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session
from groundwork.service import overview

router = APIRouter()
DRAFT_ID = re.compile(r"^[0-9a-f]{6,40}$")


def _local(v: Viewer) -> bool:
    return v.local and get_settings().groundwork_local


def _named(text: str, names: dict[str, str]) -> str:
    """The gateway writes its reasons over keys (it is generic); swap in the names people know."""
    if not names:
        return text
    keys = sorted(names, key=len, reverse=True)
    return re.sub(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", lambda mt: names[mt.group(1)], text)


def _asks(v: Viewer, refs: list[overview.ProjectRef]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ref in refs:
        you_id = v.in_org(ref.org_id).person_id
        with org_session(ref.org_id) as s:
            state = repo.load_state(s, ref.key)
            names = {p.key: p.name for p in state.parties} | {p.key: p.name for p in state.people}
            you = s.get(m.Person, you_id)
            for a in overview.pending_asks(s, state):
                subject, text = overview.text_of(a["params"])
                out.append(
                    {
                        "id": a["id"],
                        "project": ref.key,
                        "project_name": ref.name,
                        "ref": a["ref"],
                        "title": a["title"],
                        "kind": a["kind"],
                        "clause": a["clause"],
                        "reason": _named(a["reason"], names),
                        "mandate_version": a["mandate_version"],
                        "route": [names.get(state.principal) or state.principal] + [names.get(k) or k for k in a["path"]],
                        "recipient": a.get("recipient_name") or a.get("recipient"),
                        "subject": subject,
                        "text": text,
                        "approvers": [names.get(k) or k for k in a["approvers"]],
                        "can_approve": bool(you and you.approver and you.key in a["approvers"]),
                        "action_hash": a["action_hash"],
                        "at": a["run_at"],
                    }
                )
    return sorted(out, key=lambda x: x["at"], reverse=True)


def _links(rows: list[dict[str, str]], verb: str, change: str | None) -> list[dict[str, Any]]:
    return [{"text": f"{verb}: {x['before']} before {x['after']}", "change": change} for x in rows]


def draft_view(d: dict[str, Any]) -> dict[str, Any]:
    """A draft as the person reads it before confirming: a few lines, each an addition, a removal
    or a plain fact, and a note."""
    p = d["payload"]
    lines: list[dict[str, Any]] = []
    note = ""
    if d["kind"] == "mandate":
        lines = [{"text": x, "change": "add"} for x in p["diff"]["added"]] + [
            {"text": x, "change": "remove"} for x in p["diff"]["removed"]
        ]
        note = f"In your words: “{p['words']}”" + "".join(f" {n}" for n in p["notes"])
    elif d["kind"] == "project":
        lines = [
            {"text": f"{p['finish']}: target {p['target']}, forecast {p['forecast']}", "change": None},
            {"text": f"Sets the date: {p['sets_the_date'] or 'none'}", "change": None},
            {"text": f"{p['items']} steps, with {', '.join(p['parties'])}", "change": None},
            {"text": f"Mandate template: {str(p['template']).capitalize()}", "change": None},
        ] + [{"text": f"Inferred link, not stated in a source: {x}", "change": "assumed"} for x in p.get("assumed_links") or []]
        note = f"As of {p.get('as_of', '')}."
    elif d["kind"] == "facts":
        lines = [
            {"text": f"{c['item']}: {c['low_days']} to {c['high_days']} days later. “{c['why']}”", "change": "add"}
            for c in p.get("changes", [])
        ] + [
            {"text": f"{g['item']}: {'done' if g['status'] == 'done' else 'started'} on {g['date']}. “{g['why']}”", "change": "add"}
            for g in p.get("progress", [])
        ]
    elif d["kind"] == "links":
        lines = _links(p["add"], "Add", "add") + _links(p["remove"], "Remove", "remove") + _links(p["confirm"], "Confirm", None)
        note = p["why"]
    elif d["kind"] == "steps":
        titles = p.get("titles", {})
        lines = [{"text": f"Add: {x['title']} ({x['status'].replace('_', ' ')}, {x.get('finish') or 'date not known'})", "change": "add"} for x in p["add"]]
        for c in p["change"]:
            fields = ", ".join(f"{STEP_FIELD.get(k, k)} {_val(v)}" for k, v in c.items() if k != "key")
            lines.append({"text": f"Change {titles.get(c['key'], c['key'])}: {fields}", "change": "cancel" if c.get("status") == "cancelled" else None})
        lines += [{"text": f"Remove: {titles.get(k, k)}", "change": "remove"} for k in p["remove"]]
        lines += _forecast_lines(p)
        note = p["why"]
    elif d["kind"] == "project_edit":
        cur = p.get("current", {})
        c = p["change"]
        labels = {"name": "Name", "location": "Location", "finish_label": "Finish", "finish_target": "Target date", "finish_step": "Finish step", "follows": "Follows on from"}
        lines = [
            {"text": f"{labels[k]}: {cur.get(k, '') + ' → ' if cur.get(k) else ''}{v or '(none)'}", "change": None}
            for k, v in c.items()
            if k in labels
        ]
        lines += [{"text": f"Add party: {x['name']} ({x['role']})", "change": "add"} for x in c.get("add_parties", [])]
        lines += [{"text": f"Rename party {x['key']} to {x['name']}", "change": None} for x in c.get("rename_parties", [])]
        lines += _forecast_lines(p)
        note = p["why"]
    elif d["kind"] == "archive":
        restore = p.get("restore")
        lines = [
            {
                "text": "Back on home and in mail routing." if restore else "Leaves home and mail routing. Nothing is deleted; restore it any time.",
                "change": None,
            }
        ]
        note = p["why"]
    elif d["kind"] == "delete":
        lines = [
            {"text": "Deletes the project, its messages, runs and ledger from this computer.", "change": None},
            {"text": "This can't be undone. A line in deleted.jsonl keeps the ledger's last hash.", "change": None},
        ]
        note = p["why"]
    else:
        lines = [{"text": f"{x['name']} {('<' + x['email'] + '>') if x.get('email') else ''}".strip(), "change": "add"} for x in p["people"]]
        note = p["why"]
    if d["kind"] == "project" and p.get("overlaps"):
        lines += [
            {"text": f"Also on {o['name']}: {', '.join(o['people'] + o['parties'])}", "change": "assumed"} for o in p["overlaps"]
        ]
    return {
        "id": d["id"],
        "kind": d["kind"],
        "project": d["project"],
        "title": d["title"],
        "at": d["created_at"],
        "lines": lines,
        "note": note,
        "type_to_confirm": d["project"] if d["kind"] == "delete" else None,
    }


STEP_FIELD = {"depends_on": "waits on", "approximate": "estimated", "start": "start", "finish": "finish", "status": "status"}


def _val(v: Any) -> str:
    if isinstance(v, list):
        return ", ".join(v) or "nothing"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v).replace("_", " ")


def _forecast_lines(p: dict[str, Any]) -> list[dict[str, Any]]:
    b, a = p.get("before"), p.get("after")
    if not b or not a or (b["forecast"], b["sets_the_date"]) == (a["forecast"], a["sets_the_date"]):
        return []
    return [{"text": f"Forecast: {b['forecast']} → {a['forecast']}; sets the date: {a['sets_the_date'] or 'none'}", "change": None}]


@router.get("/home")
def home(v: Viewer = Depends(viewer)) -> dict[str, Any]:
    refs = list(overview.index(v.orgs).values())
    if _local(v):
        from groundwork.local import drafts

        pending = [draft_view(d) for d in drafts.pending()]
        archived = [{"project": r.key, "name": r.name, "archived_at": r.archived_at} for r in overview.index(v.orgs, archived=True).values()]
    else:
        pending, archived = [], []
    return {
        "asks": _asks(v, refs),
        "drafts": pending,
        "projects": [overview.project_row(r) for r in refs],
        "runs": overview.recent_runs(refs, 8),
        "archived": archived,
    }


class DraftVerdict(BaseModel):
    verdict: Literal["confirm", "reject"]
    typed: str | None = None


@router.post("/drafts/{draft_id}")
def decide_draft(draft_id: str, body: DraftVerdict, v: Viewer = Depends(viewer)) -> dict[str, str]:
    """Confirm or reject a draft. Only in the local runtime, where the person at this computer is
    the named person Claude drafted for."""
    if not _local(v) or not DRAFT_ID.match(draft_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such draft")
    from groundwork.local.confirm import ConfirmError, decide

    try:
        return {"message": decide(draft_id, body.verdict, body.typed)}
    except ConfirmError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
