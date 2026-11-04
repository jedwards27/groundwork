"""Creating a project on the website: the person fills in a form, checks the forecast it gives,
then creates it. The same service builds and checks it as the plugin's drafts (`service/projects`).

On a person's computer the project belongs to them ("me", set up through the plugin). The hosted
demo refuses to create projects (403), so real data stays on people's own computers (ADR 0010).
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from groundwork.api.viewer import Viewer, person_cookie, viewer
from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import owner_session
from groundwork.service import overview
from groundwork.service import projects as svc

router = APIRouter()


class NewProject(BaseModel):
    draft: svc.ProjectDraft
    your_name: str = Field(default="You", max_length=80, description="Who the project belongs to (the demo only).")


def _local(v: Viewer) -> bool:
    return v.local and get_settings().groundwork_local


def _owner(v: Viewer, body: NewProject) -> tuple[svc.Owner, str]:
    """The project's person and its org's name."""
    if _local(v):
        from groundwork.local.home import me

        who = me()
        if who is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Run /groundwork:setup in Claude first, so your projects have a named approver.")
        return svc.Owner(who.name, who.email, who.organization), f"Groundwork project: {body.draft.name}"
    if not get_settings().groundwork_demo_login:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "creating projects on this server needs the plugin")
    # Visitors' projects can share a name, so each org gets a suffix of its own.
    name = body.your_name.strip() or "You"
    return svc.Owner(name), f"Groundwork project: {body.draft.name} · {secrets.token_hex(4)}"


def _bundle(v: Viewer, body: NewProject, *, keep: bool = False) -> svc.SiteBundle:
    key = svc.slug(body.draft.name)
    if key in overview.index(v.orgs, archived=None):
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already have a project called {body.draft.name!r}; pick another name.")
    owner, org_name = _owner(v, body)
    folder = None
    if keep and _local(v):
        from groundwork.local.home import home

        folder = home() / "projects" / key
    try:
        return svc.load(body.draft, key, owner, org_name, folder)
    except svc.ProjectProblem as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.problems) from exc


class Archive(BaseModel):
    why: str = Field(default="", max_length=500)


class Delete(BaseModel):
    typed: str = Field(description="The project's key, typed by the person.")
    why: str = Field(default="", max_length=500)


def _mine(v: Viewer, key: str) -> overview.ProjectRef:
    """A project on this computer. Archiving and deleting are local only: in the hosted demo a
    visitor's copy is deleted when it expires."""
    if not _local(v):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not available in the demo")
    ref = overview.index(v.orgs, archived=None).get(key)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such project")
    return ref


def _by() -> str:
    from groundwork.local.home import me

    who = me()
    if who is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Run setup in Claude first, so changes are made by a named person.")
    return who.name


@router.post("/projects/{key}/archive")
def archive(key: str, body: Archive, v: Viewer = Depends(viewer)) -> dict[str, str]:
    """Archive a project: it leaves home and mail routing. A ledger record says who and why."""
    ref = _mine(v, key)
    if ref.archived_at:
        return {"message": f"{ref.name} is already archived."}
    svc.archive(ref.org_id, ref.site_id, by=_by(), why=body.why)
    return {"message": f"Archived {ref.name}."}


class Details(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    location: str = Field(default="", max_length=200)


@router.post("/projects/{key}/details")
def details(key: str, body: Details, v: Viewer = Depends(viewer)) -> dict[str, str]:
    """Rename a project (its key stays the same). A ledger record says who changed it."""
    from groundwork.db.session import org_session
    from groundwork.service import edits

    ref = _mine(v, key)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, key)
    change = {k: val for k, val in {"name": body.name.strip(), "location": body.location.strip()}.items() if val != getattr(state, k)}
    if not change:
        return {"message": "Nothing changed."}
    try:
        edits.apply_project(ref.org_id, ref.site_id, state, {"why": "Changed in the app", "change": change}, _by(), set(overview.index(v.orgs, archived=None)))
    except edits.EditProblem as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"message": "Saved."}


@router.post("/projects/{key}/restore")
def restore(key: str, v: Viewer = Depends(viewer)) -> dict[str, str]:
    ref = _mine(v, key)
    if not ref.archived_at:
        return {"message": f"{ref.name} is already active."}
    svc.restore(ref.org_id, ref.site_id, by=_by())
    return {"message": f"Restored {ref.name}."}


@router.post("/projects/{key}/delete")
def delete(key: str, body: Delete, v: Viewer = Depends(viewer)) -> dict[str, str]:
    """Delete a project for good. The person types its key; the demo project can't be deleted."""
    ref = _mine(v, key)
    if key == "lake-mariner":
        raise HTTPException(status.HTTP_409_CONFLICT, "The demo project can't be deleted. Archive it to hide it.")
    if body.typed.strip() != key:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Type {key} to delete it.")
    from groundwork.local.confirm import delete_project

    delete_project(ref, _by(), body.why)
    return {"message": f"Deleted {ref.name}."}


DEMO_ONLY = "The hosted site is a demo of one made-up project. To track a project of your own, run Groundwork on your computer."


def _not_on_the_demo() -> None:
    """The public demo shows Lake Mariner only. Real projects live on the person's own computer."""
    if get_settings().groundwork_hosted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, DEMO_ONLY)


class StepStatus(BaseModel):
    status: str = Field(pattern="^(cancelled|not_started|in_progress)$")


@router.post("/projects/{key}/steps/{item}")
def step_status(key: str, item: str, body: StepStatus, v: Viewer = Depends(viewer)) -> dict[str, str]:
    """Cancel a step (descoped: kept on record, ignored by the forecast) or bring it back. The person
    acting in the app; a ledger record says who."""
    from groundwork.db.session import org_session
    from groundwork.service import edits

    ref = _mine(v, key)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, key)
    payload = {"why": "Changed in the app", "add": [], "change": [{"key": item, "status": body.status}], "remove": []}
    try:
        edits.apply_steps(ref.org_id, ref.site_id, state, payload, _by())
    except edits.EditProblem as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"message": "Cancelled." if body.status == "cancelled" else "Restored."}


@router.post("/projects/preview")
def preview(body: NewProject, v: Viewer = Depends(viewer)) -> dict[str, Any]:
    """What the project would look like: its forecast and what sets the date. Nothing is saved."""
    _not_on_the_demo()
    return svc.summary(_bundle(v, body), body.draft)


@router.post("/projects")
def create(body: NewProject, request: Request, response: Response, v: Viewer = Depends(viewer)) -> dict[str, Any]:
    """Create the project the person checked. A ledger record says who created it."""
    _not_on_the_demo()
    cfg = get_settings()
    bundle = _bundle(v, body, keep=True)
    if svc.taken(bundle) and _local(v):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A project called {bundle.site_name!r} already exists on this computer.")
    expires_at = None
    if not _local(v):
        # In the hosted demo a visitor's project lives exactly as long as their copy of the demo.
        with owner_session() as s:
            ends = [o.expires_at for o in s.execute(select(m.Org).where(m.Org.id.in_(v.orgs))).scalars() if o.expires_at]
        expires_at = min(ends) if ends else None
        if cfg.groundwork_sandboxes and not repo.claim_daily("sandboxes", cfg.groundwork_sandbox_daily_cap):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "this demo's projects for today are used up; try again tomorrow")
    owner, _ = _owner(v, body)
    org_id = svc.create(bundle, by=owner.name, expires_at=expires_at)
    if not _local(v):
        pairs = [(i.person_id, i.org_id) for i in v.identities] + [(svc.me_in(org_id), org_id)]
        person_cookie(request, response, pairs)
    return {"project": bundle.site_key, "name": bundle.site_name}
