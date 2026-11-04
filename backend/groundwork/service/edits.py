"""Changing a project after it exists: its steps, its details and its parties.

Claude drafts a change; the person confirms it in the app. Each change is first applied to an
in-memory copy of the project and run through the engine, so a draft that would break the project
(an unknown key, a loop in the links, removing the finish step) is refused before anyone sees it,
and the draft can show the forecast it would give. Confirming checks again against the project as
it is then, and writes one ledger record.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, or_, select

from groundwork.db import models as m
from groundwork.db.session import owner_session
from groundwork.ingest.site_loader import ItemRow, LinkRow, MilestoneRow, PartyRow
from groundwork.ledger import append
from groundwork.service import views
from groundwork.service.projects import KIND_HELP, STATUS_HELP, ItemIn, Kind, PartyIn, Status
from groundwork.service.state import SiteState


class EditProblem(ValueError):
    """The change can't be made as written; the message says why."""


class StepChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(description="The step to change.")
    title: str | None = None
    kind: Kind | None = Field(default=None, description=KIND_HELP)
    owner: str | None = Field(default=None, description="Party key, or 'you'.")
    status: Status | None = Field(default=None, description=STATUS_HELP)
    start: date | None = None
    finish: date | None = Field(default=None, description="Planned finish, or the actual finish for a done step.")
    approximate: bool | None = Field(default=None, description="True when the date is an estimate.")
    depends_on: list[str] | None = Field(default=None, description="Replaces the steps that must finish first.")
    notes: str | None = None
    source: str | None = None


class PartyRename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str


class ProjectChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    location: str | None = None
    finish_label: str | None = None
    finish_target: date | None = None
    finish_step: str | None = Field(default=None, description="Key of the step that marks the finish.")
    add_parties: list[PartyIn] = Field(default_factory=list)
    rename_parties: list[PartyRename] = Field(default_factory=list)
    follows: str | None = Field(
        default=None, description="Key of an earlier project this one follows on from; empty string clears it."
    )


# --- steps -------------------------------------------------------------------------------------
def _changed(i: ItemRow, c: StepChange) -> ItemRow:
    status = c.status or i.status
    row = dataclasses.replace(
        i,
        title=c.title if c.title is not None else i.title,
        kind=c.kind or i.kind,
        owner=c.owner or i.owner,
        performer=c.owner or i.performer,
        status=status,
        planned_start=c.start if c.start is not None else i.planned_start,
        notes=c.notes if c.notes is not None else i.notes,
        source=c.source if c.source is not None else i.source,
        estimated=c.approximate if c.approximate is not None else i.estimated,
    )
    if status == "done":
        known = c.finish or i.actual_finish
        row = dataclasses.replace(row, actual_finish=known or i.planned_finish)
        if known is None and c.approximate is None:
            row = dataclasses.replace(row, estimated=True)
    else:
        row = dataclasses.replace(row, actual_finish=None, planned_finish=c.finish or i.planned_finish)
    if row.planned_start and row.planned_start > row.planned_finish:
        raise EditProblem(f"{i.key}: start {row.planned_start} is after finish {row.planned_finish}")
    return row


def _new(it: ItemIn, as_of: date) -> ItemRow:
    finish = it.finish or min(as_of, it.start or as_of)
    return ItemRow(
        it.key, it.key, it.title, it.kind, it.owner, it.owner, it.status, it.start, finish,
        finish if it.status == "done" else None, "calendar", "synthetic", it.source, it.notes,
        it.approximate or it.finish is None,
    )


def apply_steps_to_state(state: SiteState, payload: dict[str, Any]) -> SiteState:
    """The project as it would be with this change. Raises EditProblem if it can't be made."""
    add = [ItemIn.model_validate(x) for x in payload.get("add", [])]
    change = [StepChange.model_validate(x) for x in payload.get("change", [])]
    remove = list(payload.get("remove", []))
    keys = {i.key for i in state.items}
    parties = {p.key for p in state.parties}
    finish = {ms.item for ms in state.milestones}
    problems: list[str] = []
    for it in add:
        if it.key in keys:
            problems.append(f"{it.key!r} is already a step; change it instead")
        if it.owner not in parties:
            problems.append(f"{it.key}: owner {it.owner!r} is not a party; parties: {', '.join(sorted(parties))}")
    new_keys = keys | {it.key for it in add}
    for c in change:
        if c.key not in keys:
            problems.append(f"{c.key!r} is not a step in this project")
        if c.owner and c.owner not in parties:
            problems.append(f"{c.key}: owner {c.owner!r} is not a party; parties: {', '.join(sorted(parties))}")
        if c.status == "cancelled" and c.key in finish:
            problems.append(f"{c.key} marks the finish, so it can't be cancelled; change the finish step first")
    touched = {imp.item for e in state.events for imp in e.impacts}
    for k in remove:
        if k not in keys:
            problems.append(f"{k!r} is not a step in this project")
        elif k in finish:
            problems.append(f"{k} marks the finish, so it can't be removed; change the finish step first")
        elif k in touched:
            problems.append(f"a message moved {k}'s dates, so it stays on record; mark it cancelled instead")
    after = new_keys - set(remove)
    for it in add:
        for b in [*it.depends_on, *it.assumed_depends_on]:
            if b not in after:
                problems.append(f"{it.key}: depends on {b!r}, which is not a step")
    for c in change:
        for b in c.depends_on or []:
            if b not in after:
                problems.append(f"{c.key}: depends on {b!r}, which is not a step")
    if problems:
        raise EditProblem("; ".join(problems))
    by_key = {c.key: c for c in change}
    items = [_changed(i, by_key[i.key]) if i.key in by_key else i for i in state.items if i.key not in remove]
    items += [_new(it, state.as_of) for it in add]
    replaced = {c.key for c in change if c.depends_on is not None}
    links = [ln for ln in state.links if ln.pred not in remove and ln.succ not in remove and ln.succ not in replaced]
    links += [LinkRow(b, c.key) for c in change if c.depends_on is not None for b in c.depends_on]
    links += [LinkRow(b, it.key) for it in add for b in [*it.depends_on, *it.assumed_depends_on]]
    out = dataclasses.replace(state, items=items, links=links)
    try:
        views.chain_view(out)
    except Exception as exc:  # the engine names the loop or the missing key
        raise EditProblem(f"the steps wouldn't hold together: {exc}") from exc
    return out


def apply_steps(org_id: uuid.UUID, site_id: uuid.UUID, state: SiteState, payload: dict[str, Any], by: str) -> str:
    """Write a confirmed change of steps. Checks it again against the project as it is now."""
    after = apply_steps_to_state(state, payload)
    remove = set(payload.get("remove", []))
    added = {it["key"] for it in payload.get("add", [])}
    changed = {c["key"] for c in payload.get("change", [])}
    rows = {i.key: i for i in after.items}
    with owner_session() as s:
        site = s.get(m.Site, site_id)
        assert site is not None
        party_ids = {
            p.key: p.id
            for p in s.execute(
                select(m.Party).join(m.SiteParty, m.SiteParty.party_id == m.Party.id).where(m.SiteParty.site_id == site_id)
            ).scalars()
        }
        db = {i.key: i for i in s.execute(select(m.Item).where(m.Item.site_id == site_id)).scalars()}
        for k in remove:
            iid = db[k].id
            s.execute(delete(m.Dependency).where(or_(m.Dependency.pred_item_id == iid, m.Dependency.succ_item_id == iid)))
            s.execute(delete(m.ItemEvidence).where(m.ItemEvidence.item_id == iid))
            s.execute(delete(m.Item).where(m.Item.id == iid))
        for k in changed:
            row, i = db[k], rows[k]
            row.title, row.kind, row.status = i.title, i.kind, i.status
            row.owner_party_id = row.performer_party_id = party_ids[i.owner]
            row.planned_start, row.planned_finish, row.actual_finish = i.planned_start, i.planned_finish, i.actual_finish
            row.notes, row.source, row.date_estimated = i.notes, i.source, i.estimated
        for k in added:
            i = rows[k]
            row = m.Item(
                org_id=org_id, site_id=site_id, key=i.key, code=i.code, title=i.title, kind=i.kind,
                owner_party_id=party_ids[i.owner], performer_party_id=party_ids[i.owner], status=i.status,
                planned_start=i.planned_start, planned_finish=i.planned_finish, actual_finish=i.actual_finish,
                calendar=i.calendar, provenance=i.provenance, source=i.source, notes=i.notes, date_estimated=i.estimated,
            )
            s.add(row)
            s.flush()
            db[k] = row
        relinked = added | {c["key"] for c in payload.get("change", []) if c.get("depends_on") is not None}
        for k in relinked:
            s.execute(delete(m.Dependency).where(m.Dependency.succ_item_id == db[k].id))
            for ln in (x for x in after.links if x.succ == k):
                s.add(
                    m.Dependency(
                        org_id=org_id, site_id=site_id, pred_item_id=db[ln.pred].id, succ_item_id=db[k].id,
                        kind=ln.kind, lag_days=ln.lag, lag_calendar=ln.lag_calendar,
                    )
                )
        assumed = [f"{b}>{it['key']}" for it in payload.get("add", []) for b in it.get("assumed_depends_on", [])]
        kept = [x for x in (site.attrs or {}).get("assumed_links", "").split(";") if x and not set(x.split(">")) & remove]
        if assumed or len(kept) != len([x for x in (site.attrs or {}).get("assumed_links", "").split(";") if x]):
            site.attrs = {**(site.attrs or {}), "assumed_links": ";".join(kept + assumed)}
        append(
            s,
            "steps_changed",
            {
                "added": [{"key": k, "title": rows[k].title} for k in sorted(added)],
                "changed": payload.get("change", []),
                "removed": sorted(remove),
                "why": payload.get("why", ""),
                "by": by,
            },
            org_id=org_id,
        )
    return f"Steps changed: {len(added)} added, {len(changed)} changed, {len(remove)} removed."


# --- project details and parties ---------------------------------------------------------------
def apply_project_to_state(state: SiteState, payload: dict[str, Any], known_projects: set[str]) -> SiteState:
    c = ProjectChange.model_validate(payload.get("change", {}))
    problems: list[str] = []
    keys = {i.key for i in state.items}
    party_keys = {p.key for p in state.parties}
    if c.finish_step and c.finish_step not in keys:
        problems.append(f"{c.finish_step!r} is not a step in this project")
    if c.finish_step and next((i for i in state.items if i.key == c.finish_step), None) is not None:
        if state.item(c.finish_step).status == "cancelled":
            problems.append(f"{c.finish_step} is cancelled, so it can't mark the finish")
    for p in c.add_parties:
        if p.key in party_keys:
            problems.append(f"{p.key!r} is already a party; rename it instead")
    for r in c.rename_parties:
        if r.key not in party_keys:
            problems.append(f"{r.key!r} is not a party in this project")
    if c.follows and c.follows not in known_projects:
        problems.append(f"no project {c.follows!r} to follow on from")
    if c.follows and c.follows == state.key:
        problems.append("a project can't follow on from itself")
    if problems:
        raise EditProblem("; ".join(problems))
    ms = state.milestones[0]
    ms2 = dataclasses.replace(
        ms,
        label=c.finish_label or ms.label,
        target_date=c.finish_target or ms.target_date,
        item=c.finish_step or ms.item,
    )
    renames = {r.key: r.name for r in c.rename_parties}
    parties = [dataclasses.replace(p, name=renames.get(p.key, p.name)) for p in state.parties]
    parties += [PartyRow(p.key, p.name, (p.role,), "none", None, "synthetic", "", "") for p in c.add_parties]
    attrs = dict(state.attrs)
    if c.follows is not None:
        attrs["follows"] = c.follows
    out = dataclasses.replace(
        state,
        name=c.name or state.name,
        location=c.location if c.location is not None else state.location,
        milestones=[ms2, *state.milestones[1:]],
        parties=parties,
        attrs=attrs,
    )
    try:
        views.chain_view(out)
    except Exception as exc:
        raise EditProblem(f"the project wouldn't hold together: {exc}") from exc
    return out


def apply_project(org_id: uuid.UUID, site_id: uuid.UUID, state: SiteState, payload: dict[str, Any], by: str, known: set[str]) -> str:
    apply_project_to_state(state, payload, known)
    c = ProjectChange.model_validate(payload.get("change", {}))
    with owner_session() as s:
        site = s.get(m.Site, site_id)
        assert site is not None
        if c.name:
            site.name = c.name
        if c.location is not None:
            site.location = c.location
        if c.follows is not None:
            site.attrs = {**(site.attrs or {}), "follows": c.follows}
        if c.finish_label or c.finish_target or c.finish_step:
            ms = s.execute(
                select(m.Milestone).join(m.Asset, m.Asset.id == m.Milestone.asset_id).where(m.Asset.site_id == site_id).order_by(m.Milestone.position)
            ).scalars().first()
            assert ms is not None
            if c.finish_label:
                ms.label = c.finish_label
            if c.finish_target:
                ms.target_date = c.finish_target
            if c.finish_step:
                ms.item_id = s.execute(select(m.Item.id).where(m.Item.site_id == site_id, m.Item.key == c.finish_step)).scalar_one()
        for r in c.rename_parties:
            party = s.execute(
                select(m.Party).join(m.SiteParty, m.SiteParty.party_id == m.Party.id).where(m.SiteParty.site_id == site_id, m.Party.key == r.key)
            ).scalars().first()
            assert party is not None
            party.name = r.name
        for p in c.add_parties:
            row = m.Party(org_id=org_id, key=p.key, name=p.name, provenance="synthetic", source="", note="")
            s.add(row)
            s.flush()
            s.add(m.SiteParty(org_id=org_id, site_id=site_id, party_id=row.id, role=p.role, level="none", provenance="synthetic"))
            for n, x in enumerate(p.people, start=1):
                s.add(
                    m.Person(
                        org_id=org_id, party_id=row.id, key=f"{p.key}-{n}", name=x.name, title=x.title,
                        email=x.email.lower(), approver=False,
                    )
                )
        append(s, "project_changed", {"change": c.model_dump(mode="json", exclude_defaults=True), "why": payload.get("why", ""), "by": by}, org_id=org_id)
    return "Project details changed."


def milestone_of(state: SiteState) -> MilestoneRow:
    return state.milestones[0]
