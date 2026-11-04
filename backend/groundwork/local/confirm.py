"""Confirming or rejecting a draft: the only way a drafted project, mandate, set of date changes
and progress, links or people reaches a project. The named person at this computer does it on the
web app, never Claude; each confirmation is a ledger record.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from sqlalchemy import delete, select

from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session, owner_session
from groundwork.ingest import load_site
from groundwork.ledger import append
from groundwork.local import drafts, tools
from groundwork.local.home import me
from groundwork.policy import Mandate
from groundwork.service import edits, projects
from groundwork.service import mandates as mandates_svc


class ConfirmError(ValueError):
    """The person can't confirm this right now; the message says why."""


def decide(draft_id: str, verdict: Literal["confirm", "reject"], typed: str | None = None) -> str:
    """Confirm or reject a pending draft as the person set up on this computer. Returns what happened.
    Deleting a project also needs the person to type its key."""
    who = me()
    if who is None:
        raise ConfirmError("Run setup in Claude first, so drafts are confirmed by a named person.")
    try:
        d = drafts.get(draft_id)
    except (FileNotFoundError, KeyError) as exc:
        raise ConfirmError("No such draft.") from exc
    if d["status"] != "pending":
        return f"That draft is already {d['status']}."
    if verdict == "reject":
        drafts.resolve(draft_id, "rejected", who.name)
        return "Rejected; nothing changed."
    if d["kind"] == "delete" and (typed or "").strip() != d["project"]:
        raise ConfirmError(f"Type {d['project']} to delete it.")
    confirm = {
        "project": _confirm_project,
        "mandate": _confirm_mandate,
        "facts": _confirm_facts,
        "links": _confirm_links,
        "people": _confirm_people,
        "steps": _confirm_steps,
        "project_edit": _confirm_project_edit,
        "archive": _confirm_archive,
        "delete": _confirm_delete,
    }[d["kind"]]
    try:
        return confirm(d, who.name)
    except edits.EditProblem as exc:
        drafts.resolve(d["id"], "rejected", who.name, why=str(exc))
        return f"Not changed: {exc}. The project changed since this draft; ask Claude to draft it again."


def _confirm_project(d: dict[str, Any], by: str) -> str:
    bundle = load_site(d["payload"]["folder"])
    if projects.taken(bundle):
        drafts.resolve(d["id"], "rejected", by, why="a project with this name already exists")
        return f"Not created: {bundle.site_name} already exists. Nothing was changed."
    projects.create(bundle, by=by)
    drafts.resolve(d["id"], "confirmed", by)
    return f"Created {bundle.site_name}."


def _confirm_mandate(d: dict[str, Any], by: str) -> str:
    ref = tools._ref(d["project"])
    p = d["payload"]
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, ref.key)
        current = repo.active_mandate(s, ref.site_id)
        if current.version != p["base_version"]:
            drafts.resolve(d["id"], "rejected", by, why=f"the mandate changed to v{current.version} after this draft")
            return f"Not issued: the mandate is now v{current.version}, newer than this draft. Draft it again."
        person = s.execute(select(m.Person).where(m.Person.key == "me")).scalar_one_or_none()
        out = mandates_svc.issue(
            s,
            state,
            Mandate.model_validate(p["doc"]),
            person.id if person else None,
            "me" if person else f"local person: {by}",
            words=p["words"],
        )
    drafts.resolve(d["id"], "confirmed", by)
    return f"Issued mandate v{out['version']}; {len(out['redecided'])} open action(s) decided again."


def _confirm_facts(d: dict[str, Any], by: str) -> str:
    ref = tools._ref(d["project"])
    p = d["payload"]
    changes, steps = p.get("changes", []), p.get("progress", [])
    with org_session(ref.org_id) as s:
        if changes:
            row = s.execute(select(m.Event).where(m.Event.site_id == ref.site_id, m.Event.key == p["message"])).scalar_one()
            row.impacts = list(row.impacts) + [
                {"item": c["item"], "low": c["low_days"], "high": c["high_days"], "calendar": "calendar", "leg": c["why"], "owner": ""}
                for c in changes
            ]
            if row.kind in ("evidence", "acknowledgment"):
                row.kind = "schedule_change"
        append(s, "facts_confirmed", {"message": p["message"], "changes": changes, "progress": steps, "by": by})
    if steps:
        # Item rows belong to the owner role (the app role only reads the schedule).
        with owner_session() as s:
            for g in steps:
                item = s.execute(select(m.Item).where(m.Item.site_id == ref.site_id, m.Item.key == g["item"])).scalar_one()
                when = date.fromisoformat(g["date"])
                if g["status"] == "done":
                    item.status, item.actual_finish = "done", when
                else:
                    item.status = "in_progress"
                    item.planned_start = min(when, item.planned_start or when)
    drafts.resolve(d["id"], "confirmed", by)
    return f"Confirmed {len(changes)} date change(s) and {len(steps)} progress update(s)."


def _confirm_links(d: dict[str, Any], by: str) -> str:
    ref = tools._ref(d["project"])
    p = d["payload"]
    with owner_session() as s:
        site = s.get(m.Site, ref.site_id)
        assert site is not None
        ids = {i.key: i.id for i in s.execute(select(m.Item).where(m.Item.site_id == ref.site_id)).scalars()}
        for ln in p["remove"]:
            s.execute(
                delete(m.Dependency).where(
                    m.Dependency.site_id == ref.site_id,
                    m.Dependency.pred_item_id == ids[ln["before"]],
                    m.Dependency.succ_item_id == ids[ln["after"]],
                )
            )
        for ln in p["add"]:
            s.add(
                m.Dependency(
                    org_id=ref.org_id,
                    site_id=ref.site_id,
                    pred_item_id=ids[ln["before"]],
                    succ_item_id=ids[ln["after"]],
                    kind="FS",
                    lag_days=0,
                    lag_calendar="calendar",
                )
            )
        settled = {f"{x['before']}>{x['after']}" for x in p["remove"] + p["confirm"]}
        assumed = [x for x in (site.attrs or {}).get("assumed_links", "").split(";") if x and x not in settled]
        site.attrs = {**(site.attrs or {}), "assumed_links": ";".join(assumed)}
        append(s, "links_changed", {"add": p["add"], "remove": p["remove"], "confirm": p["confirm"], "why": p["why"], "by": by}, org_id=ref.org_id)
    drafts.resolve(d["id"], "confirmed", by)
    return f"Links changed: {len(p['add'])} added, {len(p['remove'])} removed, {len(p['confirm'])} confirmed."


def _confirm_people(d: dict[str, Any], by: str) -> str:
    ref = tools._ref(d["project"])
    p = d["payload"]
    with owner_session() as s:
        party = s.execute(select(m.Party).where(m.Party.org_id == ref.org_id, m.Party.key == p["party"])).scalar_one()
        taken = {x.key for x in s.execute(select(m.Person).where(m.Person.org_id == ref.org_id)).scalars()}
        n = 1
        for x in p["people"]:
            while f"{p['party']}-{n}" in taken:
                n += 1
            taken.add(f"{p['party']}-{n}")
            s.add(
                m.Person(
                    org_id=ref.org_id,
                    party_id=party.id,
                    key=f"{p['party']}-{n}",
                    name=x["name"],
                    title=x.get("title", ""),
                    email=x.get("email", "").lower(),
                    approver=False,
                )
            )
        append(s, "people_added", {"party": p["party"], "people": [x["name"] for x in p["people"]], "why": p["why"], "by": by}, org_id=ref.org_id)
    drafts.resolve(d["id"], "confirmed", by)
    return f"Added {len(p['people'])} person(s)."


def _confirm_steps(d: dict[str, Any], by: str) -> str:
    ref = tools._ref(d["project"])
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, ref.key)
    out = edits.apply_steps(ref.org_id, ref.site_id, state, d["payload"], by)
    drafts.resolve(d["id"], "confirmed", by)
    return out


def _confirm_project_edit(d: dict[str, Any], by: str) -> str:
    ref = tools._ref(d["project"])
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, ref.key)
    out = edits.apply_project(ref.org_id, ref.site_id, state, d["payload"], by, set(tools._index(archived=None)))
    drafts.resolve(d["id"], "confirmed", by)
    return out


def _confirm_archive(d: dict[str, Any], by: str) -> str:
    ref = tools._ref(d["project"])
    if d["payload"].get("restore"):
        projects.restore(ref.org_id, ref.site_id, by=by)
        out = f"Restored {ref.name}."
    else:
        projects.archive(ref.org_id, ref.site_id, by=by, why=d["payload"].get("why", ""))
        out = f"Archived {ref.name}. Restore it any time from Archived on the home page."
    drafts.resolve(d["id"], "confirmed", by)
    return out


def _confirm_delete(d: dict[str, Any], by: str) -> str:
    ref = tools._ref(d["project"])
    if ref.key == "lake-mariner":
        drafts.resolve(d["id"], "rejected", by, why="the demo project can't be deleted")
        return "Not deleted: the demo project stays. Archive it to hide it."
    delete_project(ref, by, d["payload"].get("why", ""), keep=d["id"])
    drafts.resolve(d["id"], "confirmed", by)
    return f"Deleted {ref.name} and its ledger. A line in deleted.jsonl keeps its last hash."


def delete_project(ref: Any, by: str, why: str, keep: str | None = None) -> dict[str, Any]:
    """Delete a project, its ledger and its working folder; log the deletion and drop its drafts."""
    import shutil

    from groundwork.local.home import home

    entry = projects.delete(ref.org_id, by=by, why=why, log=home() / "deleted.jsonl")
    folder = home() / "projects" / ref.key
    if folder.is_dir():
        shutil.rmtree(folder)
    for other in drafts.pending(ref.key):
        if other["id"] == keep:
            continue
        drafts.resolve(other["id"], "superseded", by, why="the project was deleted")
    return entry
