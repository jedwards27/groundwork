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

from pydantic import BaseModel, ConfigDict, Field
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


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(description="Short lowercase key, unique in the project.")
    title: str
    kind: Literal["study", "approval", "permit", "inspection", "test", "delivery", "milestone", "notice", "agreement", "consent", "financing", "land"]
    owner: str = Field(description="Party key responsible, or 'you' for the person's own side.")
    status: Literal["done", "in_progress", "not_started"]
    start: date | None = None
    finish: date = Field(description="Planned finish (or the actual finish when done).")
    depends_on: list[str] = Field(default_factory=list, description="Item keys that must finish first, as a source states.")
    assumed_depends_on: list[str] = Field(
        default_factory=list,
        description="Item keys you believe must finish first but no source states. Flagged for the person to confirm.",
    )
    source: str = Field(default="", description="Where this came from: an email subject, a file, the person.")


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
    cols = ["key", "title", "kind", "owner", "performer", "status", "planned_start", "planned_finish", "actual_finish", "calendar", "predecessors", "provenance", "source", "notes"]
    w = csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    for it in d.items:
        w.writerow(
            {
                "key": it.key,
                "title": it.title,
                "kind": it.kind,
                "owner": it.owner,
                "performer": it.owner,
                "status": it.status,
                "planned_start": it.start.isoformat() if it.start else "",
                "planned_finish": it.finish.isoformat(),
                "actual_finish": it.finish.isoformat() if it.status == "done" else "",
                "calendar": "calendar",
                "predecessors": ";".join([*it.depends_on, *it.assumed_depends_on]),
                "provenance": "synthetic",
                "source": it.source,
                "notes": "",
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


def create(bundle: SiteBundle, *, by: str, expires_at: datetime | None = None) -> uuid.UUID:
    """Create the project as a new org, with its ledger's first records. Owner role."""
    with owner_session() as s:
        org_id = repo.seed_bundle(s, bundle, replace=False)
        if expires_at is not None:
            org = s.get(m.Org, org_id)
            assert org is not None
            org.expires_at = expires_at
        append(s, "project_created", {"project": bundle.site_key, "by": by, "items": len(bundle.items)}, org_id=org_id)
    return org_id


def me_in(org_id: uuid.UUID) -> uuid.UUID:
    """The id of the project's own person ("me") in its org."""
    with owner_session() as s:
        return s.execute(select(m.Person.id).where(m.Person.org_id == org_id, m.Person.key == "me")).scalar_one()

