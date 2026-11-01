"""Repository: load a site folder into the database (owner role) and read a SiteState back
(app role, row-level security). Reads call ``require_org`` first."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from groundwork.db import models as m
from groundwork.db.session import require_org
from groundwork.ingest.site_loader import (
    EventRow,
    FactRow,
    ImpactRow,
    ItemRow,
    LinkRow,
    MilestoneRow,
    PartyRow,
    PersonRow,
    ReferenceRowIn,
    SiteBundle,
)
from groundwork.service.state import EvidenceLite, SiteState

# Children first, so deletes respect foreign keys.
_ORG_DELETE_ORDER = (
    m.Approval, m.Decision, m.Action, m.MandateVersion, m.Plan, m.Run, m.Event, m.ItemEvidence, m.Evidence,
    m.Milestone, m.Dependency, m.Item, m.Asset, m.SiteParty, m.Person,
)


def delete_org_data(s: Session, org_id: uuid.UUID) -> None:
    """Owner role only. Deletes everything an org owns (reseed and demo reset).

    The ledger's append-only trigger is disabled for the length of this transaction and re-enabled
    before commit. That is exactly the move an operator with owner credentials could make to rewrite
    history, which is why the attestation exports the head hash: a reset is visible as a new chain.
    """
    s.execute(text("ALTER TABLE ledger_entry DISABLE TRIGGER ledger_no_update_delete"))
    s.execute(delete(m.LedgerEntry).where(m.LedgerEntry.org_id == org_id))
    s.execute(text("ALTER TABLE ledger_entry ENABLE TRIGGER ledger_no_update_delete"))
    for model in _ORG_DELETE_ORDER:
        s.execute(delete(model).where(model.org_id == org_id))
    s.execute(text("DELETE FROM site WHERE org_id = :o"), {"o": org_id})
    s.execute(delete(m.Party).where(m.Party.org_id == org_id))


def seed_bundle(s: Session, b: SiteBundle, *, replace: bool = True) -> uuid.UUID:
    """Owner role. Create (or replace) the org named in the bundle and load the site into it."""
    org = s.execute(select(m.Org).where(m.Org.name == b.org_name)).scalar_one_or_none()
    if org is None:
        org = m.Org(name=b.org_name, timezone=b.timezone)
        s.add(org)
        s.flush()
    elif replace:
        delete_org_data(s, org.id)
    oid = org.id

    party_ids: dict[str, uuid.UUID] = {}
    for p in b.parties:
        row = m.Party(
            org_id=oid, key=p.key, name=p.name, provenance=p.provenance, source=p.source, note=p.note
        )
        s.add(row)
        s.flush()
        party_ids[p.key] = row.id
    site = m.Site(
        org_id=oid,
        key=b.site_key,
        name=b.site_name,
        location=b.location,
        profile=b.profile,
        as_of=b.as_of,
        principal_party_id=party_ids[b.principal],
        attrs=b.attrs,
        holidays=[d.isoformat() for d in b.holidays],
        calendar_note=b.calendar_note,
        facts=[asdict(f) for f in b.facts],
    )
    s.add(site)
    s.flush()
    for p in b.parties:
        for role in p.roles:
            s.add(
                m.SiteParty(
                    org_id=oid,
                    site_id=site.id,
                    party_id=party_ids[p.key],
                    role=role,
                    level=p.level,
                    reached_via_party_id=party_ids.get(p.reached_via) if p.reached_via else None,
                    provenance=p.provenance,
                )
            )
    for x in b.people:
        s.add(
            m.Person(
                org_id=oid,
                party_id=party_ids[x.party],
                key=x.key,
                name=x.name,
                title=x.title,
                email=x.email,
                approver=x.approver,
            )
        )
    asset = m.Asset(
        org_id=oid, site_id=site.id, key=b.asset_key, name=b.asset_name, capacity_mw=b.capacity_mw
    )
    s.add(asset)
    item_ids: dict[str, uuid.UUID] = {}
    for i in b.items:
        row = m.Item(
            org_id=oid,
            site_id=site.id,
            key=i.key,
            code=i.code,
            title=i.title,
            kind=i.kind,
            owner_party_id=party_ids[i.owner],
            performer_party_id=party_ids[i.performer],
            status=i.status,
            planned_start=i.planned_start,
            planned_finish=i.planned_finish,
            actual_finish=i.actual_finish,
            calendar=i.calendar,
            provenance=i.provenance,
            source=i.source,
            notes=i.notes,
        )
        s.add(row)
        s.flush()
        item_ids[i.key] = row.id
    s.flush()
    for pos, ms in enumerate(b.milestones):
        s.add(
            m.Milestone(
                org_id=oid,
                asset_id=asset.id,
                kind=ms.kind,
                label=ms.label,
                item_id=item_ids[ms.item],
                target_date=ms.target_date,
                binding_agreement=ms.binding_agreement,
                position=pos,
                provenance=ms.provenance,
                source=ms.source,
                note=ms.note,
            )
        )
    for ln in b.links:
        s.add(
            m.Dependency(
                org_id=oid,
                site_id=site.id,
                pred_item_id=item_ids[ln.pred],
                succ_item_id=item_ids[ln.succ],
                kind=ln.kind,
                lag_days=ln.lag,
                lag_calendar=ln.lag_calendar,
            )
        )
    for e in b.evidence:
        s.add(
            m.Evidence(
                org_id=oid,
                site_id=site.id,
                key=e.key,
                kind=e.kind,
                title=e.title,
                party_id=party_ids.get(e.party) if e.party else None,
                data=_jsonable(e.data),
                source_kind=e.envelope.source_kind,
                external_ref=e.envelope.external_ref,
                content_hash=e.envelope.content_hash,
                blob_location=e.envelope.blob_location,
                media_type=e.envelope.media_type,
                fetched_at=e.envelope.fetched_at,
                provenance=e.provenance,
                source=e.source,
            )
        )
    for ev in b.events:
        s.add(
            m.Event(
                org_id=oid,
                site_id=site.id,
                key=ev.key,
                kind=ev.kind,
                title=ev.title,
                from_party=ev.from_party,
                forwarded_from=ev.forwarded_from,
                received_at=ev.received_at,
                body=ev.body,
                message_ref=ev.message_path,
                evidence_key=ev.evidence_key,
                links=list(ev.links),
                impacts=[asdict(i) for i in ev.impacts],
                provenance=ev.provenance,
                source=ev.source,
                note=ev.note,
                status="available",
            )
        )
    state_mandate = _initial_mandate(b)
    s.add(m.MandateVersion(org_id=oid, site_id=site.id, version=1, preset=state_mandate.preset,
                           doc=state_mandate.model_dump(mode="json")))
    s.flush()
    from groundwork.ledger import append

    append(s, "mandate_issued", {"site": b.site_key, "version": 1, "preset": state_mandate.preset,
                                 "issuer": state_mandate.issuer, "approvers": state_mandate.ask.approvers,
                                 "summary": state_mandate.plain_lines()}, org_id=oid)
    for r in b.reference_rows:
        existing = s.execute(
            select(m.ReferenceProject).where(m.ReferenceProject.key == r.key)
        ).scalar_one_or_none()
        values = dict(
            label=r.label,
            item_code=r.item_code,
            measure=r.measure,
            value_days=r.value_days,
            value_days_high=r.value_days_high,
            attrs=r.attrs,
            source_url=r.source_url,
            provenance=r.provenance,
            note=r.note,
        )
        if existing is None:
            s.add(m.ReferenceProject(key=r.key, **values))
        else:
            for k, v in values.items():
                setattr(existing, k, v)
    s.flush()
    return oid


def _initial_mandate(b: SiteBundle):  # type: ignore[no-untyped-def]
    from groundwork.policy import build_preset

    spec = b.mandate
    return build_preset(spec.preset, issuer=b.principal, approvers=list(spec.approvers),
                        legal_approvers=list(spec.legal_approvers), sla_hours=spec.sla_hours,
                        owner_goals=list(spec.owner_goals), valid_from=b.as_of)


def _jsonable(v: object) -> object:
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def list_site_keys(s: Session) -> list[str]:
    require_org(s)
    return list(s.execute(select(m.Site.key).order_by(m.Site.key)).scalars())


def load_state(s: Session, site_key: str) -> SiteState:
    org_id = require_org(s)
    site = s.execute(select(m.Site).where(m.Site.key == site_key)).scalar_one_or_none()
    if site is None:
        raise KeyError(site_key)
    parties = {p.id: p for p in s.execute(select(m.Party)).scalars()}
    pkey = {pid: p.key for pid, p in parties.items()}
    links_by_party: dict[uuid.UUID, list[m.SiteParty]] = {}
    for sp in s.execute(select(m.SiteParty).where(m.SiteParty.site_id == site.id)).scalars():
        links_by_party.setdefault(sp.party_id, []).append(sp)
    party_rows: list[PartyRow] = []
    for pid, sps in links_by_party.items():
        p = parties[pid]
        via = next((sp.reached_via_party_id for sp in sps if sp.reached_via_party_id), None)
        party_rows.append(
            PartyRow(
                p.key,
                p.name,
                tuple(sorted(sp.role for sp in sps)),
                sps[0].level,
                pkey[via] if via else None,
                p.provenance,
                p.source,
                p.note,
            )
        )
    party_rows.sort(key=lambda r: r.key)
    people = [
        PersonRow(x.key, pkey[x.party_id], x.name, x.title, x.email, x.approver)
        for x in s.execute(select(m.Person).order_by(m.Person.key)).scalars()
    ]
    items_db = list(s.execute(select(m.Item).where(m.Item.site_id == site.id).order_by(m.Item.key)).scalars())
    ikey = {i.id: i.key for i in items_db}
    items = [
        ItemRow(
            i.key,
            i.code,
            i.title,
            i.kind,
            pkey[i.owner_party_id],
            pkey[i.performer_party_id],
            i.status,
            i.planned_start,
            i.planned_finish,
            i.actual_finish,
            i.calendar,
            i.provenance,
            i.source,
            i.notes,
        )
        for i in items_db
    ]
    links = [
        LinkRow(ikey[d.pred_item_id], ikey[d.succ_item_id], d.kind, d.lag_days, d.lag_calendar)
        for d in s.execute(select(m.Dependency).where(m.Dependency.site_id == site.id)).scalars()
    ]
    asset = s.execute(select(m.Asset).where(m.Asset.site_id == site.id)).scalars().first()
    assert asset is not None
    milestones = [
        MilestoneRow(
            ms.kind,
            ms.label,
            ikey[ms.item_id],
            ms.target_date,
            ms.binding_agreement,
            ms.provenance,
            ms.source,
            ms.note,
        )
        for ms in s.execute(
            select(m.Milestone).where(m.Milestone.asset_id == asset.id).order_by(m.Milestone.position)
        ).scalars()
    ]
    events_db = list(
        s.execute(select(m.Event).where(m.Event.site_id == site.id).order_by(m.Event.received_at)).scalars()
    )
    events = [
        EventRow(
            e.key,
            e.kind,
            e.title,
            e.from_party,
            e.received_at,
            e.body,
            e.message_ref,
            e.forwarded_from,
            e.evidence_key,
            tuple(e.links),
            tuple(ImpactRow(**i) for i in e.impacts),
            e.provenance,
            e.source,
            e.note,
        )
        for e in events_db
    ]
    evidence = [
        EvidenceLite(
            e.key,
            e.kind,
            e.title,
            pkey.get(e.party_id) if e.party_id else None,
            e.data,
            e.provenance,
            e.source,
        )
        for e in s.execute(select(m.Evidence).where(m.Evidence.site_id == site.id)).scalars()
    ]
    refs = [
        ReferenceRowIn(
            r.key,
            r.label,
            r.item_code,
            r.measure,
            r.value_days,
            r.value_days_high,
            dict(r.attrs),
            r.source_url,
            r.provenance,
            r.note,
        )
        for r in s.execute(select(m.ReferenceProject).order_by(m.ReferenceProject.key)).scalars()
    ]
    ids: dict[str, uuid.UUID] = {f"party:{k}": pid for pid, k in pkey.items()}
    ids.update({f"item:{i.key}": i.id for i in items_db})
    ids.update({f"event:{e.key}": e.id for e in events_db})
    ids.update({f"person:{x.key}": x.id for x in s.execute(select(m.Person)).scalars()})
    return SiteState(
        key=site.key,
        name=site.name,
        location=site.location,
        profile=site.profile,
        as_of=site.as_of,
        principal=pkey[site.principal_party_id],
        attrs={k: str(v) for k, v in site.attrs.items()},
        holidays=tuple(date.fromisoformat(h) for h in site.holidays),
        calendar_note=site.calendar_note,
        asset_key=asset.key,
        asset_name=asset.name,
        capacity_mw=asset.capacity_mw,
        milestones=milestones,
        parties=party_rows,
        people=people,
        items=items,
        links=links,
        events=events,
        event_status={e.key: e.status for e in events_db},
        evidence=evidence,
        facts=[FactRow(**f) for f in site.facts],
        reference_rows=refs,
        org_id=org_id,
        site_id=site.id,
        ids=ids,
        timezone=_org_timezone(s, org_id),
    )


def _org_timezone(s: Session, org_id: uuid.UUID) -> str:
    org = s.get(m.Org, org_id)
    return org.timezone if org is not None else "UTC"


def set_event_status(s: Session, site_id: uuid.UUID, event_key: str, status: str) -> None:
    require_org(s)
    s.execute(
        update(m.Event)
        .where(m.Event.site_id == site_id, m.Event.key == event_key)
        .values(status=status, applied_at=datetime.now(UTC) if status == "applied" else None)
    )


def active_mandate(s: Session, site_id: uuid.UUID):  # type: ignore[no-untyped-def]
    """The latest mandate version for a site, as a Mandate model."""
    from groundwork.policy import Mandate

    require_org(s)
    row = s.execute(select(m.MandateVersion).where(m.MandateVersion.site_id == site_id)
                    .order_by(m.MandateVersion.version.desc())).scalars().first()
    if row is None:
        raise KeyError("no mandate for site")
    return Mandate.model_validate(row.doc)
