"""FastAPI dependencies: identity from the bearer token, and an org-scoped session for it."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from groundwork.api.auth import Identity, TokenError, verify
from groundwork.config import get_settings
from groundwork.db.session import org_session


def identity(authorization: str | None = Header(default=None)) -> Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "missing bearer token (mint one with `groundwork token <person>`)"
        )
    try:
        return verify(
            authorization.split(" ", 1)[1].strip(), secret=get_settings().groundwork_dev_hmac_secret
        )
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


def db(who: Identity = Depends(identity)) -> Iterator[Session]:
    """The org comes from the signed token, never from a header the caller chooses."""
    with org_session(who.org_id) as s:
        yield s
