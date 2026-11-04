"""A project from what a person wrote down: in the plugin, the draft Claude prepares from their
words or email; on the website, the form they fill in. Both become the same two files, are checked
by the same loader, and are created as an org of their own, with its own ledger.
"""

from __future__ import annotations

import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import owner_session
from groundwork.ingest import load_site
from groundwork.ingest.site_loader import LoadError, SiteBundle
from groundwork.ledger import append
from groundwork.service import views


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "project"


@dataclass(frozen=True)
class Owner:
    """The person a new project belongs to: its one approver."""

    name: str
    email: str = ""
    organization: str = ""


class PersonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    email: str = ""
    title: str = ""


class PartyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(description="Short lowercase key, for example 'gc' or 'city-permits'.")
    name: str
    role: Literal[
        "contractor", "designer", "consultant", "vendor", "landlord", "lender", "ahj", "agency", "regulator", "developer", "operator", "community"
    ] = Field(description="ahj is the permit office; agency is an inspector or utility.")
    people: list[PersonIn] = Field(default_factory=list)


Kind = Literal[
    "study", "approval", "permit", "inspection", "test", "delivery", "install", "milestone", "notice",
    "agreement", "consent", "financing", "land", "decision", "meeting", "payment",
]
KIND_HELP = (
    "install is fitting or installing work; decision is a selection or sign-off; meeting is a meeting or "
    "presentation; payment is an invoice, deposit or payment."
)
Status = Literal["done", "in_progress", "not_started", "cancelled"]
STATUS_HELP = "cancelled means descoped: it stays on record, but nothing waits on it and the forecast ignores it."


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(description="Short lowercase key, unique in the project.")
    title: str
    kind: Kind = Field(description=KIND_HELP)
    owner: str = Field(description="Party key responsible, or 'you' for the person's own side.")
    status: Status = Field(description=STATUS_HELP)
    start: date | None = None
    finish: date | None = Field(
        default=None,
        description="Planned finish, or the actual finish when done. Leave empty only for a done step whose "
        "finish date isn't known; it is then marked as an estimate.",
    )
    approximate: bool = Field(
        default=False, description="True when the date is an estimate, for example 'early December' or 'about two weeks'."
    )
    depends_on: list[str] = Field(default_factory=list, description="Item keys that must finish first, as a source states.")
    assumed_depends_on: list[str] = Field(
        default_factory=list,
        description="Item keys you believe must finish first but no source states. Flagged for the person to confirm.",
    )
    source: str = Field(default="", description="Where this came from: an email subject, a file, the person.")
    notes: str = ""

    @model_validator(mode="after")
    def _finish_needed(self) -> ItemIn:
        if self.finish is None and self.status not in ("done", "cancelled"):
            raise ValueError(f"{self.key}: finish is required unless the step is done or cancelled")
        return self


class ProjectDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    location: str = ""
    as_of: date | None = Field(default=None, description="The project's current date; today if empty. Set it in the past to backtest.")
    finish_label: str = Field(description="What finishing means, for example 'Kitchen usable' or 'Store opens'.")
    finish_item: str = Field(description="Key of the item that marks the finish.")
    finish_target: date = Field(description="The date the finish is promised or hoped for.")
    parties: list[PartyIn]
    your_side: list[PersonIn] = Field(
        default_factory=list, description="Other people on the person's own side (a partner, a colleague). Never approvers."
    )
    items: list[ItemIn]
    template: Literal["supervised", "standard", "auto"] = "supervised"


def _local_timezone() -> str:
    """The computer's time zone, for a project's working calendar."""
    try:
        from pathlib import Path

        target = str(Path("/etc/localtime").resolve())
        return target.split("zoneinfo/", 1)[1]
    except (OSError, IndexError):
        return "UTC"


def write_folder(d: ProjectDraft, key: str, folder: Path, owner: Owner, org_name: str) -> Path:
    """The project as the two files every site folder has: site.yaml and schedule.csv. The person
    who wrote it is "me", the project's one approver, on their own side ("you")."""
    import csv
    import io

    import yaml

    from groundwork.policy.terms import TEMPLATES

    who = owner
    folder.mkdir(parents=True, exist_ok=True)
    parties: list[dict[str, Any]] = [
        {"key": "you", "name": who.organization or who.name, "roles": ["owner"], "provenance": "synthetic"}
    ]
    people: list[dict[str, Any]] = [{"key": "me", "party": "you", "name": who.name, "email": who.email, "approver": True}]
    for i, x in enumerate(d.your_side, start=1):
        people.append({"key": f"you-{i}", "party": "you", "name": x.name, "title": x.title, "email": x.email.lower()})
    for p in d.parties:
        parties.append({"key": p.key, "name": p.name, "roles": [p.role], "provenance": "synthetic"})
        for i, x in enumerate(p.people, start=1):
            people.append({"key": f"{p.key}-{i}", "party": p.key, "name": x.name, "title": x.title, "email": x.email.lower()})
    assumed = [f"{b}>{it.key}" for it in d.items for b in it.assumed_depends_on]
    doc = {
        "org": {"name": org_name, "timezone": _local_timezone()},
        "site": {
            "key": key,
            "name": d.name,
            "location": d.location,
            "profile": "general",
            "as_of": (d.as_of or date.today()).isoformat(),
            "principal": "you",
            "attrs": {"live": "true", **({"assumed_links": ";".join(assumed)} if assumed else {})},
            "calendar": {"holidays": []},
        },
        "asset": {
            "key": "project",
            "name": d.name,
            "milestones": [
                {
                    "kind": "substantial_completion",
                    "label": d.finish_label,
                    "item": d.finish_item,
                    "target_date": d.finish_target.isoformat(),
                    "provenance": "synthetic",
                }
            ],
        },
        "parties": parties,
        "people": people,
        "mandate": {"preset": TEMPLATES[d.template], "approvers": ["me"]},
    }
    (folder / "site.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    out = io.StringIO()
    cols = ["key", "title", "kind", "owner", "performer", "status", "planned_start", "planned_finish", "actual_finish", "estimated", "calendar", "predecessors", "provenance", "source", "notes"]
    w = csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    as_of = d.as_of or date.today()
    for it in d.items:
        finish = it.finish or min(as_of, it.start or as_of)
        w.writerow(
            {
                "key": it.key,
                "title": it.title,
                "kind": it.kind,
                "owner": it.owner,
                "performer": it.owner,
                "status": it.status,
                "planned_start": it.start.isoformat() if it.start else "",
                "planned_finish": finish.isoformat(),
                "actual_finish": finish.isoformat() if it.status == "done" else "",
                "estimated": "true" if (it.approximate or it.finish is None) else "",
                "calendar": "calendar",
                "predecessors": ";".join([*it.depends_on, *it.assumed_depends_on]),
                "provenance": "synthetic",
                "source": it.source,
                "notes": it.notes or ("Finished; the date isn't known." if it.finish is None and it.status == "done" else ""),
            }
        )
    (folder / "schedule.csv").write_text(out.getvalue())
    return folder


class ProjectProblem(ValueError):
    """The project can't be created as written; `problems` says what to fix."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def load(d: ProjectDraft, key: str, owner: Owner, org_name: str, folder: Path | None = None) -> SiteBundle:
    """Write the project's files (to `folder`, or a throwaway one) and load them, or raise
    ProjectProblem with every problem at once."""
    if folder is None:
        folder = Path(tempfile.mkdtemp(prefix="groundwork-project-"))
    write_folder(d, key, folder, owner, org_name)
    try:
        return load_site(folder)
    except LoadError as exc:
        raise ProjectProblem(list(exc.problems)) from exc


def summary(bundle: SiteBundle, d: ProjectDraft) -> dict[str, Any]:
    """What the person checks before creating it: the forecast and what sets the date."""
    from groundwork.service.state import SiteState

    chain = views.chain_view(SiteState.from_bundle(bundle))
    titles = {i.key: i.title for i in chain.items}
    ms = chain.milestone
    return {
        "project": bundle.site_key,
        "name": bundle.site_name,
        "items": len(bundle.items),
        "parties": [p.name for p in bundle.parties],
        "finish": d.finish_label,
        "target": d.finish_target.isoformat(),
        "as_of": str(bundle.as_of),
        "forecast": str(ms.forecast_finish),
        "days_late": ms.delta_days,
        "sets_the_date": titles.get(chain.gate or ""),
        "assumed_links": [f"{titles[b]} before {titles[it.key]}" for it in d.items for b in it.assumed_depends_on],
        "template": d.template,
    }


def taken(bundle: SiteBundle) -> bool:
    """A project with this key or org name already exists somewhere."""
    with owner_session() as s:
        if s.execute(select(m.Site).where(m.Site.key == bundle.site_key)).first() is not None:
            return True
        return s.execute(select(m.Org).where(m.Org.name == bundle.org_name)).first() is not None


def snapshot(bundle: SiteBundle) -> dict[str, Any]:
    """What the project held when it was created, for its first ledger record: enough to see later
    what changed, and a hash of the whole folder."""
    import hashlib
    import json

    ms = bundle.milestones[0] if bundle.milestones else None
    steps = [
        {"key": i.key, "title": i.title, "status": i.status, "finish": str(i.actual_finish or i.planned_finish), **({"estimated": True} if i.estimated else {})}
        for i in bundle.items
    ]
    body = {
        "name": bundle.site_name,
        "as_of": str(bundle.as_of),
        "finish": {"label": ms.label, "step": ms.item, "target": str(ms.target_date)} if ms else None,
        "parties": [p.name for p in bundle.parties],
        "people": len(bundle.people),
        "links": len(bundle.links),
        "steps": steps,
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return {**body, "snapshot_sha256": digest}


def create(bundle: SiteBundle, *, by: str, expires_at: datetime | None = None) -> uuid.UUID:
    """Create the project as a new org, with its ledger's first records. Owner role."""
    with owner_session() as s:
        org_id = repo.seed_bundle(s, bundle, replace=False)
        if expires_at is not None:
            org = s.get(m.Org, org_id)
            assert org is not None
            org.expires_at = expires_at
        append(
            s,
            "project_created",
            {"project": bundle.site_key, "by": by, "items": len(bundle.items), "snapshot": snapshot(bundle)},
            org_id=org_id,
        )
    return org_id


def overlaps(emails: set[str], party_names: set[str], *, skip: str | None = None) -> list[dict[str, Any]]:
    """Other active projects that share people (by email) or a party (by name) with these. Mail from
    a shared person can belong to either project, so routing asks unless the thread or subject says."""
    emails = {e.lower() for e in emails if e}
    names = {n.strip().lower() for n in party_names if n.strip()}
    out: list[dict[str, Any]] = []
    with owner_session() as s:
        for site in s.execute(select(m.Site).where(m.Site.archived_at.is_(None))).scalars():
            if site.key == skip:
                continue
            org = s.get(m.Org, site.org_id)
            if org is None or org.expires_at is not None:
                continue
            party_ids = {sp.party_id for sp in s.execute(select(m.SiteParty).where(m.SiteParty.site_id == site.id)).scalars()}
            parties = [p for p in s.execute(select(m.Party).where(m.Party.id.in_(party_ids))).scalars() if p.key != "you"]
            people = s.execute(select(m.Person).where(m.Person.party_id.in_(party_ids), m.Person.key != "me")).scalars()
            shared_people = sorted({p.email.lower() for p in people if p.email and p.email.lower() in emails})
            shared_parties = sorted({p.name for p in parties if p.name.strip().lower() in names})
            if shared_people or shared_parties:
                out.append({"project": site.key, "name": site.name, "people": shared_people, "parties": shared_parties})
    return out


# --- archive, restore, delete -------------------------------------------------------------------
def archive(org_id: uuid.UUID, site_id: uuid.UUID, *, by: str, why: str) -> None:
    """Hide the project from home and from mail routing. Nothing is deleted; restore undoes it."""
    from datetime import UTC

    with owner_session() as s:
        site = s.get(m.Site, site_id)
        assert site is not None
        site.archived_at = datetime.now(UTC)
        append(s, "project_archived", {"project": site.key, "by": by, "why": why}, org_id=org_id)


def restore(org_id: uuid.UUID, site_id: uuid.UUID, *, by: str) -> None:
    with owner_session() as s:
        site = s.get(m.Site, site_id)
        assert site is not None
        site.archived_at = None
        append(s, "project_restored", {"project": site.key, "by": by}, org_id=org_id)


def delete(org_id: uuid.UUID, *, by: str, why: str, log: Path | None = None) -> dict[str, Any]:
    """Delete the project and its ledger for good. The ledger can't record its own deletion, so a
    line goes to a local log instead: what was deleted, by whom, and the ledger's last hash, which
    still checks any receipt someone kept."""
    import json
    from datetime import UTC

    with owner_session() as s:
        site = s.execute(select(m.Site).where(m.Site.org_id == org_id)).scalar_one()
        head = s.execute(
            select(m.LedgerEntry).where(m.LedgerEntry.org_id == org_id).order_by(m.LedgerEntry.seq.desc()).limit(1)
        ).scalar_one_or_none()
        entry = {
            "deleted_at": datetime.now(UTC).isoformat(),
            "project": site.key,
            "name": site.name,
            "by": by,
            "why": why,
            "records": head.seq if head else 0,
            "last_hash": head.hash if head else None,
        }
        repo.delete_org_data(s, org_id)
        s.execute(sa_delete(m.Org).where(m.Org.id == org_id))
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
    return entry


def me_in(org_id: uuid.UUID) -> uuid.UUID:
    """The id of the project's own person ("me") in its org."""
    with owner_session() as s:
        return s.execute(select(m.Person.id).where(m.Person.org_id == org_id, m.Person.key == "me")).scalar_one()

