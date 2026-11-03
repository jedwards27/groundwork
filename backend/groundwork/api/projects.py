"""Creating a project on the website: the person fills in a form, checks the forecast it gives,
then creates it. The same service builds and checks it as the plugin's drafts (`service/projects`).

On a person's computer the project belongs to them ("me", set up through the plugin). In the demo,
a visitor's project is its own org next to their copy of the demo: it lasts as long as that copy,
and their sign-in widens to include it.
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
    if key in overview.index(v.orgs):
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


@router.post("/projects/preview")
def preview(body: NewProject, v: Viewer = Depends(viewer)) -> dict[str, Any]:
    """What the project would look like: its forecast and what sets the date. Nothing is saved."""
    return svc.summary(_bundle(v, body), body.draft)


@router.post("/projects")
def create(body: NewProject, request: Request, response: Response, v: Viewer = Depends(viewer)) -> dict[str, Any]:
    """Create the project the person checked. A ledger record says who created it."""
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
