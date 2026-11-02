"""Day-1 schema. Every org-scoped table carries ``org_id`` and is protected by row-level security
(see migrations/versions/0001_day1_schema.py). ``reference_project`` is the one shared table.

``org`` is the customer boundary (the account that pays). It is never called a tenant: in this
industry a tenant is a lessee, which is a party role.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _org() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("org.id"), nullable=False)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Org(Base):
    __tablename__ = "org"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()
    # Set only on a hosted-demo sandbox: the org and everything in it is deleted after this time.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DailyUsage(Base):
    """How many times something happened today, across every org: the hosted demo's caps (runs,
    live planner calls, new sandboxes). Counters only, no org data, so no row-level security; a
    sandbox's deletion never resets a cap."""

    __tablename__ = "daily_usage"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    metric: Mapped[str] = mapped_column(Text, primary_key=True)
    n: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Party(Base):
    __tablename__ = "party"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_party_org_key"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)


class Site(Base):
    __tablename__ = "site"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_site_org_key"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    profile: Mapped[str] = mapped_column(Text, nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    principal_party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("party.id"), nullable=False
    )
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    holidays: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    calendar_note: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created()


class SiteParty(Base):
    __tablename__ = "site_party"
    __table_args__ = (UniqueConstraint("site_id", "party_id", "role", name="uq_site_party_role"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.id"), nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("party.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    reached_via_party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("party.id"))
    provenance: Mapped[str] = mapped_column(Text, nullable=False)


class Person(Base):
    __tablename__ = "person"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_person_org_key"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    party_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("party.id"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    approver: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Asset(Base):
    __tablename__ = "asset"
    __table_args__ = (UniqueConstraint("site_id", "key", name="uq_asset_site_key"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.id"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_mw: Mapped[float | None] = mapped_column(Float)


class Item(Base):
    __tablename__ = "item"
    __table_args__ = (UniqueConstraint("site_id", "key", name="uq_item_site_key"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.id"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    owner_party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("party.id"), nullable=False
    )
    performer_party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("party.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_finish: Mapped[date] = mapped_column(Date, nullable=False)
    actual_finish: Mapped[date | None] = mapped_column(Date)
    calendar: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)


class Milestone(Base):
    __tablename__ = "milestone"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    binding_agreement: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)


class Dependency(Base):
    __tablename__ = "dependency"
    __table_args__ = (UniqueConstraint("pred_item_id", "succ_item_id", name="uq_dependency_pair"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.id"), nullable=False)
    pred_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id"), nullable=False)
    succ_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    lag_days: Mapped[int] = mapped_column(Integer, nullable=False)
    lag_calendar: Mapped[str] = mapped_column(Text, nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("site_id", "key", name="uq_evidence_site_key"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.id"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("party.id"))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    external_ref: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    blob_location: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)


class ItemEvidence(Base):
    __tablename__ = "item_evidence"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id"), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=False
    )
    cited_text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)


class Event(Base):
    __tablename__ = "event"
    __table_args__ = (UniqueConstraint("site_id", "key", name="uq_event_site_key"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.id"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    from_party: Mapped[str] = mapped_column(Text, nullable=False)
    forwarded_from: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    message_ref: Mapped[str | None] = mapped_column(Text)
    evidence_key: Mapped[str | None] = mapped_column(Text)
    links: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    impacts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scripted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Run(Base):
    __tablename__ = "run"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.id"), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("event.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id")
    )
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Plan(Base):
    __tablename__ = "plan"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("run.id"), nullable=False)
    arm: Mapped[str] = mapped_column(Text, nullable=False)
    planner: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created()


class ReferenceProject(Base):
    """Shared across orgs (no org_id, no row-level security). Public or anonymized rows only."""

    __tablename__ = "reference_project"
    id: Mapped[uuid.UUID] = _pk()
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    item_code: Mapped[str] = mapped_column(Text, nullable=False)
    measure: Mapped[str] = mapped_column(Text, nullable=False)
    value_days: Mapped[float | None] = mapped_column(Float)
    value_days_high: Mapped[float | None] = mapped_column(Float)
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)


class MandateVersion(Base):
    """One row per version of a site's grant of authority. Versions are never edited."""

    __tablename__ = "mandate"
    __table_args__ = (UniqueConstraint("site_id", "version", name="uq_mandate_site_version"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    preset: Mapped[str] = mapped_column(Text, nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id")
    )
    created_at: Mapped[datetime] = _created()


class Action(Base):
    """A proposed action, immutable once written. Its state is derived from decisions, approvals
    and ledger entries; nothing updates this row."""

    __tablename__ = "action"
    __table_args__ = (UniqueConstraint("plan_id", "ref", name="uq_action_plan_ref"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("run.id"), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plan.id"), nullable=False)
    arm: Mapped[str] = mapped_column(Text, nullable=False)
    ref: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    executor: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str | None] = mapped_column(Text)
    asks_party: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    effect: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    proposed_autonomy: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    action_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()


class Decision(Base):
    """The gateway's decision on an action under one mandate version. Re-decisions add rows."""

    __tablename__ = "decision"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("action.id"), nullable=False)
    mandate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    delta: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    effect_class: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    record_bearing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    content_class: Mapped[str | None] = mapped_column(Text)
    classifier: Mapped[str] = mapped_column(Text, nullable=False)
    amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created()


class Approval(Base):
    """A typed approval or decline by a named person, bound to the exact action and mandate version.
    The only writer is POST /actions/{id}/approvals; no inbound message can create one."""

    __tablename__ = "approval"
    __table_args__ = (UniqueConstraint("action_id", "person_id", name="uq_approval_action_person"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("action.id"), nullable=False)
    action_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mandate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("person.id"), nullable=False)
    kid: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = _created()


class LedgerEntry(Base):
    """Append-only, hash-chained per org. ``recorded_at`` is the exact RFC 3339 string that was
    hashed; ``seq`` is contiguous from 1. A trigger rejects UPDATE, DELETE and TRUNCATE, and the
    app role has only SELECT and INSERT."""

    __tablename__ = "ledger_entry"
    __table_args__ = (UniqueConstraint("org_id", "seq", name="uq_ledger_org_seq"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    entry_type: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    arm: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


ORG_SCOPED_TABLES: tuple[str, ...] = (
    "party",
    "site",
    "site_party",
    "person",
    "asset",
    "item",
    "milestone",
    "dependency",
    "evidence",
    "item_evidence",
    "event",
    "run",
    "plan",
    "mandate",
    "action",
    "decision",
    "approval",
    "ledger_entry",
)
