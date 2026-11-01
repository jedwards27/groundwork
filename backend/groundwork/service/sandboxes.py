"""Sandbox orgs for the hosted demo.

Each visitor's demo login gets a private copy of the demo org's fixture, stored as an org of its
own. Row-level security keeps visitors apart exactly as it keeps customers apart, so two people
clicking through the link at once never see each other's runs, approvals or ledger. Sandboxes are
deleted, ledger and all, when they expire or when their visitor starts over (ADR 0007).
"""

from __future__ import annotations

import dataclasses
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import owner_session
from groundwork.ingest import load_site
from groundwork.ingest.site_loader import SiteBundle


class SandboxLimit(RuntimeError):
    """Today's allowance of new sandboxes (GROUNDWORK_SANDBOX_DAILY_CAP) is used up."""


def _demo_bundles() -> list[SiteBundle]:
    cfg = get_settings()
    folders = sorted(p for p in cfg.groundwork_fixtures_dir.iterdir() if (p / "site.yaml").exists())
    return [b for b in (load_site(f) for f in folders) if b.org_name == cfg.groundwork_demo_org]


def create(now: datetime | None = None) -> uuid.UUID:
    """A new sandbox org seeded with the demo org's sites. Expired sandboxes are swept first."""
    cfg = get_settings()
    if not repo.claim_daily("sandboxes", cfg.groundwork_sandbox_daily_cap):
        raise SandboxLimit(
            f"this demo hands out {cfg.groundwork_sandbox_daily_cap} sandboxes a day and they are used up; "
            "try again after midnight UTC"
        )
    now = now or datetime.now(UTC)
    sweep(now)
    bundles = _demo_bundles()
    if not bundles:
        raise RuntimeError(f"no fixture folder belongs to the demo org {cfg.groundwork_demo_org!r}")
    name = f"{cfg.groundwork_demo_org} · sandbox {secrets.token_hex(4)}"
    with owner_session() as s:
        org_id = None
        for i, b in enumerate(bundles):
            org_id = repo.seed_bundle(s, dataclasses.replace(b, org_name=name), replace=i == 0)
        assert org_id is not None
        org = s.get(m.Org, org_id)
        assert org is not None
        org.expires_at = now + timedelta(hours=cfg.groundwork_sandbox_ttl_hours)
    return org_id


def live(org_id: uuid.UUID, now: datetime | None = None) -> bool:
    """True when `org_id` is a sandbox that has not expired."""
    now = now or datetime.now(UTC)
    with owner_session() as s:
        org = s.get(m.Org, org_id)
        return bool(org and org.expires_at and org.expires_at > now)


def discard(org_id: uuid.UUID) -> None:
    """Delete one sandbox now (its visitor started over). Never touches a non-sandbox org."""
    with owner_session() as s:
        org = s.get(m.Org, org_id)
        if org is not None and org.expires_at is not None:
            _delete(s, org_id)


def sweep(now: datetime | None = None) -> int:
    """Delete every sandbox past its expiry; return how many."""
    now = now or datetime.now(UTC)
    with owner_session() as s:
        expired = list(
            s.execute(select(m.Org.id).where(m.Org.expires_at.is_not(None), m.Org.expires_at < now)).scalars()
        )
        for org_id in expired:
            _delete(s, org_id)
    return len(expired)


def _delete(s, org_id: uuid.UUID) -> None:  # noqa: ANN001 - sqlalchemy Session
    repo.delete_org_data(s, org_id)
    s.execute(delete(m.Org).where(m.Org.id == org_id))
