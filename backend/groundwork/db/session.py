"""Database sessions.

``org_session`` is the only way application code touches org-scoped tables: it opens a
transaction and sets ``app.org_id`` with ``set_config(..., true)`` (transaction-local, bound as a
parameter). Row-level security reads that setting; when it is missing every policy fails closed.
``require_org`` lets repository functions assert they are inside such a session.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from groundwork.config import get_settings


class OrgScopeError(RuntimeError):
    """A query ran outside an org-scoped session."""


@lru_cache
def engine_for(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def app_engine() -> Engine:
    return engine_for(get_settings().database_url)


def owner_engine() -> Engine:
    return engine_for(get_settings().database_owner_url)


@contextmanager
def org_session(org_id: uuid.UUID | str, *, engine: Engine | None = None) -> Iterator[Session]:
    with Session(engine or app_engine(), expire_on_commit=False) as s, s.begin():
        s.execute(text("select set_config('app.org_id', :org, true)"), {"org": str(org_id)})
        yield s


@contextmanager
def owner_session(*, engine: Engine | None = None) -> Iterator[Session]:
    """Owner role: bypasses row-level security. Seeding, reset and admin only."""
    with Session(engine or owner_engine(), expire_on_commit=False) as s, s.begin():
        yield s


def require_org(session: Session) -> uuid.UUID:
    value = session.execute(text("select nullif(current_setting('app.org_id', true), '')")).scalar()
    if not value:
        raise OrgScopeError("org-scoped query outside org_session()")
    return uuid.UUID(str(value))
