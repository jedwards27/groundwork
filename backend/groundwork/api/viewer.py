"""Who is looking, and in which project's org a request runs.

A token names one person in one org (``api/auth.py``). A viewer is the set of (person, org) pairs a
signed-in browser may act as:

- a hosted visitor or a developer: one pair, the demo project's lead in their copy of the demo;
- the plugin's local runtime: one pair per project on this computer, because each local project is
  its own org with its own ledger. You are "me" on your own projects and the demo lead on the demo.

Each request still runs in exactly one org's session with row-level security, as before. The org
comes from the request's project key, run id or action id, and only from the viewer's own orgs.

The browser holds the token in an HttpOnly cookie its scripts cannot read. Scripts and the CLI may
send it as a bearer header instead. A cookie is sent by the browser on its own, so every state
change that arrives with a cookie must also prove it came from this app's own pages (``guard_csrf``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select

from groundwork.api.auth import Identity, TokenError, mint_local, mint_many, verify, verify_local, verify_many
from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db.session import owner_session

COOKIE = "gw_session"
LOCAL_TTL_HOURS = 24 * 30
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class Viewer:
    identities: tuple[Identity, ...]
    local: bool = False

    @property
    def orgs(self) -> set[uuid.UUID]:
        return {i.org_id for i in self.identities}

    def in_org(self, org_id: uuid.UUID) -> Identity:
        found = next((i for i in self.identities if i.org_id == org_id), None)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        return found


def token_of(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.cookies.get(COOKIE)


def lead(s, org_id: uuid.UUID) -> m.Person | None:  # noqa: ANN001 - sqlalchemy Session
    """The person a browser acts as in an org: "me" on a local project, else the first approver on
    the principal's side (the demo project's lead)."""
    people = list(s.execute(select(m.Person).where(m.Person.org_id == org_id).order_by(m.Person.key)).scalars())
    mine = next((p for p in people if p.key == "me"), None)
    if mine is not None:
        return mine
    principals = {x for (x,) in s.execute(select(m.Site.principal_party_id).where(m.Site.org_id == org_id))}
    return next((p for p in people if p.approver and p.party_id in principals), None)


def local_identities(kid: str, exp: datetime) -> tuple[Identity, ...]:
    """Every project org on this computer (sandboxes never exist locally), as its lead."""
    out: list[Identity] = []
    with owner_session() as s:
        orgs = s.execute(
            select(m.Org).where(m.Org.expires_at.is_(None)).where(m.Org.id.in_(select(m.Site.org_id))).order_by(m.Org.name)
        ).scalars()
        for org in orgs:
            person = lead(s, org.id)
            if person is not None:
                out.append(Identity(person.id, org.id, kid, exp))
    return tuple(out)


def viewer_or_none(request: Request) -> Viewer | None:
    token = token_of(request)
    if not token:
        return None
    cfg = get_settings()
    secret = cfg.groundwork_dev_hmac_secret
    ids: tuple[Identity, ...] | None = None
    try:
        ids = (verify(token, secret=secret),)
    except TokenError:
        try:
            ids = verify_many(token, secret=secret)
        except TokenError:
            pass
    if ids is not None:
        # Reloading the demo gives its people new ids; a token naming people who are gone is a
        # signed-out browser, which the app then signs in again.
        with owner_session() as s:
            alive = set(s.execute(select(m.Person.id).where(m.Person.id.in_([i.person_id for i in ids]))).scalars())
        kept = tuple(i for i in ids if i.person_id in alive)
        return Viewer(kept) if kept else None
    if not cfg.groundwork_local:
        return None
    try:
        kid, exp = verify_local(token, secret=secret)
    except TokenError:
        return None
    return Viewer(local_identities(kid, exp), local=True)


def viewer(request: Request) -> Viewer:
    found = viewer_or_none(request)
    if found is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "not signed in (open the app from its link, or send a bearer token from `groundwork token <person>`)",
        )
    return found


def _owner_org(model: type[m.Run] | type[m.Action], key: str) -> uuid.UUID | None:
    try:
        ident = uuid.UUID(key)
    except ValueError:
        return None
    with owner_session() as s:
        row = s.get(model, ident)
        return row.org_id if row is not None else None


def resolve(v: Viewer, path_params: dict[str, str]) -> Identity:
    """The viewer's identity in the org this request is about."""
    if len(v.identities) == 1:
        return v.identities[0]
    if not v.identities:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no projects yet")
    if site := path_params.get("site"):
        with owner_session() as s:
            orgs = [o for (o,) in s.execute(select(m.Site.org_id).where(m.Site.key == site)) if o in v.orgs]
        if not orgs:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no project {site!r}")
        return v.in_org(orgs[0])
    for name, model in (("run_id", m.Run), ("action_id", m.Action)):
        if key := path_params.get(name):
            org = _owner_org(model, key)
            if org is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
            return v.in_org(org)
    return v.identities[0]


def set_cookie(request: Request, response: Response, token: str, ttl_hours: int) -> None:
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        COOKIE, token, max_age=ttl_hours * 3600, httponly=True, samesite="lax", secure=secure, path="/"
    )


def person_cookie(request: Request, response: Response, pairs: list[tuple[uuid.UUID, uuid.UUID]]) -> None:
    """Sign this browser in as these (person, org) pairs: the first is the one it shows as "you"."""
    cfg = get_settings()
    token = mint_many(pairs, secret=cfg.groundwork_dev_hmac_secret, ttl_hours=cfg.token_ttl_hours)
    set_cookie(request, response, token, cfg.token_ttl_hours)


def local_cookie(request: Request, response: Response) -> None:
    secret = get_settings().groundwork_dev_hmac_secret
    set_cookie(request, response, mint_local(secret=secret, ttl_hours=LOCAL_TTL_HOURS), LOCAL_TTL_HOURS)


def csrf_problem(request: Request) -> str | None:
    """Why a state change must be refused, or None. Only a request carrying the session cookie can
    be forged by another site; one with its own bearer header, or no credential, is not at risk."""
    if request.method not in UNSAFE or COOKIE not in request.cookies:
        return None
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return None
    origin = request.headers.get("origin")
    if not origin or urlsplit(origin).netloc != request.headers.get("host"):
        return "cross-site request refused: the Origin header must match this app"
    ctype = request.headers.get("content-type", "")
    if request.headers.get("content-length", "0") != "0" and not ctype.startswith("application/json"):
        return "send JSON"
    return None
