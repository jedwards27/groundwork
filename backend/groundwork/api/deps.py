"""FastAPI dependencies: identity from the viewer's token, and an org-scoped session for it."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from groundwork.api.auth import Identity
from groundwork.api.viewer import Viewer, resolve, viewer
from groundwork.db.session import org_session


def identity(request: Request, v: Viewer = Depends(viewer)) -> Identity:
    """The viewer's identity in the org this request is about (its project, run or action)."""
    return resolve(v, request.path_params)


def db(who: Identity = Depends(identity)) -> Iterator[Session]:
    """The org comes from the signed token and the viewer's own orgs, never from a header the
    caller chooses."""
    with org_session(who.org_id) as s:
        yield s
