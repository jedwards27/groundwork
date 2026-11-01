"""Load a site folder (the file-drop connector for a schedule export plus context files).

Layout::

    site.yaml               org, site, asset + milestones, parties, people, facts
    schedule.csv            one row per item; predecessors in one column ("a; b FS+15bd; c FF+5bd")
    events.yaml             events that can be played
    reference_projects.csv  shared reference rows (comparable items)
    evidence/*.yaml         structured evidence (quotes, fee offers)
    inbox/*.eml             messages referenced by events

Every problem found is collected and raised together, so a person loading their own export sees
the whole list at once.
"""

from __future__ import annotations

import csv
import email
import email.policy
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from groundwork.ingest.envelope import PROVENANCE_VALUES, Envelope

ITEM_KINDS = (
    "study",
    "approval",
    "permit",
    "inspection",
    "test",
    "delivery",
    "milestone",
    "notice",
    "agreement",
    "consent",
    "financing",
    "land",
)
STATUSES = ("done", "in_progress", "not_started")
ROLES = (
    "landlord",
    "lessee",
    "end_user",
    "developer",
    "to",
    "iso",
    "ahj",
    "agency",
    "regulator",
    "vendor",
    "epc",
    "lender",
    "offtaker",
    "investor",
    "ie",
    "operator",
    "community",
)
LEVELS = ("federal", "state", "local", "none")
EVENT_KINDS = ("schedule_change", "evidence", "acknowledgment", "injection")
MILESTONE_KINDS = ("energization", "delivery", "cod", "substantial_completion", "final_acceptance")
_PRED = re.compile(r"^(?P<key>[\w-]+)(?:\s+(?P<kind>FS|SS|FF)(?P<lag>[+-]\d+)?(?P<unit>bd|cd)?)?$")


class LoadError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("site folder has problems:\n  - " + "\n  - ".join(problems))


@dataclass(frozen=True)
class PartyRow:
    key: str
    name: str
    roles: tuple[str, ...]
    level: str = "none"
    reached_via: str | None = None
    provenance: str = "synthetic"
    source: str = ""
    note: str = ""


@dataclass(frozen=True)
class PersonRow:
    key: str
    party: str
    name: str
    title: str = ""
    email: str = ""
    approver: bool = False


@dataclass(frozen=True)
class ItemRow:
    key: str
    code: str
    title: str
    kind: str
    owner: str
    performer: str
    status: str
    planned_start: date | None
    planned_finish: date
    actual_finish: date | None
    calendar: str
    provenance: str
    source: str
    notes: str


@dataclass(frozen=True)
class LinkRow:
    pred: str
    succ: str
    kind: str = "FS"
    lag: int = 0
    lag_calendar: str = "business"


@dataclass(frozen=True)
class MilestoneRow:
    kind: str
    label: str
    item: str
    target_date: date
    binding_agreement: str = ""
    provenance: str = "synthetic"
    source: str = ""
    note: str = ""


@dataclass(frozen=True)
class ImpactRow:
    item: str
    low: int
    high: int
    calendar: str = "calendar"
    leg: str = ""
    owner: str = ""


@dataclass(frozen=True)
class EventRow:
    key: str
    kind: str
    title: str
    from_party: str
    received_at: datetime
    body: str
    message_path: str | None
    forwarded_from: str | None
    evidence_key: str | None
    links: tuple[str, ...]
    impacts: tuple[ImpactRow, ...]
    provenance: str
    source: str
    note: str


@dataclass(frozen=True)
class EvidenceRow:
    key: str
    kind: str
    title: str
    party: str | None
    data: dict[str, Any]
    provenance: str
    source: str
    envelope: Envelope


@dataclass(frozen=True)
class FactRow:
    label: str
    value: str
    provenance: str
    source: str = ""


@dataclass(frozen=True)
class ReferenceRowIn:
    key: str
    label: str
    item_code: str
    measure: str
    value_days: float | None
    value_days_high: float | None
    attrs: dict[str, str]
    source_url: str
    provenance: str
    note: str


@dataclass
class SiteBundle:
    root: Path
    org_name: str
    timezone: str
    site_key: str
    site_name: str
    location: str
    profile: str
    as_of: date
    principal: str
    attrs: dict[str, str]
    holidays: tuple[date, ...]
    calendar_note: str
    asset_key: str
    asset_name: str
    capacity_mw: float | None
    milestones: list[MilestoneRow]
    parties: list[PartyRow]
    people: list[PersonRow]
    items: list[ItemRow]
    links: list[LinkRow]
    events: list[EventRow]
    evidence: list[EvidenceRow]
    facts: list[FactRow]
    reference_rows: list[ReferenceRowIn]
    envelopes: list[Envelope] = field(default_factory=list)

    def item(self, key: str) -> ItemRow:
        return next(i for i in self.items if i.key == key)

    def party(self, key: str) -> PartyRow:
        return next(p for p in self.parties if p.key == key)


def _date(v: Any, where: str, problems: list[str]) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    try:
        return date.fromisoformat(str(v).strip())
    except ValueError:
        problems.append(f"{where}: {v!r} is not a YYYY-MM-DD date")
        return None


def _prov(v: Any, where: str, problems: list[str]) -> str:
    v = (v or "synthetic").strip()
    if v not in PROVENANCE_VALUES:
        problems.append(f"{where}: provenance {v!r} must be one of {', '.join(PROVENANCE_VALUES)}")
    return v


def parse_predecessors(cell: str, succ: str, problems: list[str]) -> list[LinkRow]:
    out: list[LinkRow] = []
    for raw in (cell or "").split(";"):
        token = raw.strip()
        if not token:
            continue
        m = _PRED.match(token)
        if not m:
            problems.append(
                f"schedule.csv {succ}: cannot read predecessor {token!r} (expected e.g. 'a', 'a FS+15bd')"
            )
            continue
        out.append(
            LinkRow(
                pred=m["key"],
                succ=succ,
                kind=m["kind"] or "FS",
                lag=int(m["lag"] or 0),
                lag_calendar="calendar" if m["unit"] == "cd" else "business",
            )
        )
    return out


def _read_message(path: Path) -> str:
    msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    body = msg.get_body(preferencelist=("plain",))
    return body.get_content().strip() if body is not None else ""  # type: ignore[union-attr]


def load_site(root: Path | str) -> SiteBundle:
    root = Path(root)
    problems: list[str] = []
    envelopes: list[Envelope] = []

    site_doc = yaml.safe_load((root / "site.yaml").read_text())
    envelopes.append(Envelope.for_file(root / "site.yaml", root))
    org, site, asset = site_doc.get("org", {}), site_doc["site"], site_doc["asset"]

    parties: list[PartyRow] = []
    for p in site_doc.get("parties", []):
        roles = tuple(p.get("roles", []))
        for r in roles:
            if r not in ROLES:
                problems.append(f"site.yaml party {p['key']}: unknown role {r!r}")
        level = p.get("level", "none")
        if level not in LEVELS:
            problems.append(f"site.yaml party {p['key']}: unknown level {level!r}")
        parties.append(
            PartyRow(
                p["key"],
                p["name"],
                roles,
                level,
                p.get("reached_via"),
                _prov(p.get("provenance"), f"party {p['key']}", problems),
                p.get("source", ""),
                p.get("note", ""),
            )
        )
    party_keys = {p.key for p in parties}
    for p in parties:
        if p.reached_via and p.reached_via not in party_keys:
            problems.append(f"party {p.key}: reached_via {p.reached_via!r} is not a party")
    principal = site.get("principal", "")
    if principal not in party_keys:
        problems.append(f"site.yaml: principal {principal!r} is not a party")

    people = [
        PersonRow(
            x["key"],
            x["party"],
            x["name"],
            x.get("title", ""),
            x.get("email", ""),
            bool(x.get("approver", False)),
        )
        for x in site_doc.get("people", [])
    ]
    for x in people:
        if x.party not in party_keys:
            problems.append(f"person {x.key}: party {x.party!r} is not a party")

    items: list[ItemRow] = []
    links: list[LinkRow] = []
    with (root / "schedule.csv").open(newline="") as fh:
        envelopes.append(Envelope.for_file(root / "schedule.csv", root))
        for n, row in enumerate(csv.DictReader(fh), start=2):
            key = (row.get("key") or "").strip()
            where = f"schedule.csv line {n} ({key or '?'})"
            if not key:
                problems.append(f"{where}: missing key")
                continue
            kind = row.get("kind", "").strip()
            if kind not in ITEM_KINDS:
                problems.append(f"{where}: kind {kind!r} must be one of {', '.join(ITEM_KINDS)}")
            status = row.get("status", "").strip()
            if status not in STATUSES:
                problems.append(f"{where}: status {status!r} must be one of {', '.join(STATUSES)}")
            owner, performer = (
                row.get("owner", "").strip(),
                (row.get("performer") or row.get("owner", "")).strip(),
            )
            for who, label in ((owner, "owner"), (performer, "performer")):
                if who not in party_keys:
                    problems.append(f"{where}: {label} {who!r} is not a party in site.yaml")
            start = _date(row.get("planned_start"), where, problems)
            finish = _date(row.get("planned_finish"), where, problems)
            actual = _date(row.get("actual_finish"), where, problems)
            if finish is None:
                problems.append(f"{where}: planned_finish is required")
                continue
            if start and start > finish:
                problems.append(f"{where}: planned_start {start} is after planned_finish {finish}")
            if status == "done" and actual is None:
                problems.append(f"{where}: done items need an actual_finish")
            cal = (row.get("calendar") or "business").strip()
            if cal not in ("business", "calendar"):
                problems.append(f"{where}: calendar must be business or calendar")
            items.append(
                ItemRow(
                    key,
                    (row.get("code") or key).strip(),
                    row.get("title", "").strip(),
                    kind,
                    owner,
                    performer,
                    status,
                    start,
                    finish,
                    actual,
                    cal,
                    _prov(row.get("provenance"), where, problems),
                    (row.get("source") or "").strip(),
                    (row.get("notes") or "").strip(),
                )
            )
            links.extend(parse_predecessors(row.get("predecessors", ""), key, problems))
    item_keys = {i.key for i in items}
    if len(item_keys) != len(items):
        problems.append("schedule.csv: duplicate item keys")
    for ln in links:
        if ln.pred not in item_keys:
            problems.append(f"schedule.csv {ln.succ}: predecessor {ln.pred!r} is not an item")

    milestones: list[MilestoneRow] = []
    for m in asset.get("milestones", []):
        td = _date(m.get("target_date"), f"milestone {m.get('label')}", problems)
        if m.get("kind") not in MILESTONE_KINDS:
            problems.append(f"milestone {m.get('label')}: kind must be one of {', '.join(MILESTONE_KINDS)}")
        if m.get("item") not in item_keys:
            problems.append(f"milestone {m.get('label')}: item {m.get('item')!r} is not in schedule.csv")
        if td:
            milestones.append(
                MilestoneRow(
                    m["kind"],
                    m["label"],
                    m["item"],
                    td,
                    m.get("binding_agreement", ""),
                    _prov(m.get("provenance"), "milestone", problems),
                    m.get("source", ""),
                    m.get("note", ""),
                )
            )

    evidence: list[EvidenceRow] = []
    for path in sorted((root / "evidence").glob("*.yaml")) if (root / "evidence").exists() else []:
        doc = yaml.safe_load(path.read_text())
        env = Envelope.for_file(path, root, provenance=doc.get("provenance", "synthetic"))
        envelopes.append(env)
        evidence.append(
            EvidenceRow(
                doc["key"],
                doc.get("kind", "document"),
                doc.get("title", ""),
                doc.get("party"),
                doc,
                _prov(doc.get("provenance"), path.name, problems),
                doc.get("source", ""),
                env,
            )
        )
    status_report = root / "status-report-2026-10-30.md"
    if status_report.exists():
        env = Envelope.for_file(status_report, root)
        envelopes.append(env)
        evidence.append(
            EvidenceRow(
                "status-report-2026-10-30",
                "status_report",
                "CB-5 weekly status report",
                "terawulf",
                {"text": status_report.read_text()},
                "synthetic",
                "",
                env,
            )
        )
    evidence_keys = {e.key for e in evidence}

    events: list[EventRow] = []
    ev_doc = (
        yaml.safe_load((root / "events.yaml").read_text())
        if (root / "events.yaml").exists()
        else {"events": []}
    )
    for e in ev_doc.get("events", []):
        where = f"events.yaml {e.get('key')}"
        if e.get("kind") not in EVENT_KINDS:
            problems.append(f"{where}: kind must be one of {', '.join(EVENT_KINDS)}")
        body, msg_path = "", e.get("message")
        if msg_path:
            p = root / msg_path
            if not p.exists():
                problems.append(f"{where}: message {msg_path} not found")
            else:
                body = _read_message(p)
                envelopes.append(Envelope.for_file(p, root))
        impacts = []
        for imp in e.get("impacts", []) or []:
            if imp["item"] not in item_keys:
                problems.append(f"{where}: impact item {imp['item']!r} is not in schedule.csv")
            if int(imp["low"]) > int(imp["high"]):
                problems.append(f"{where}: impact low > high")
            impacts.append(
                ImpactRow(
                    imp["item"],
                    int(imp["low"]),
                    int(imp["high"]),
                    imp.get("calendar", "calendar"),
                    imp.get("leg", ""),
                    imp.get("owner", ""),
                )
            )
        for ln in e.get("links", []) or []:
            if ln not in item_keys:
                problems.append(f"{where}: linked item {ln!r} is not in schedule.csv")
        if e.get("evidence") and e["evidence"] not in evidence_keys:
            problems.append(f"{where}: evidence {e['evidence']!r} not found")
        from_party = e.get("from", "public")
        if from_party != "public" and from_party not in party_keys:
            problems.append(f"{where}: from {from_party!r} is not a party")
        received = e.get("received_at")
        if not isinstance(received, datetime):
            try:
                received = datetime.fromisoformat(str(received))
            except ValueError:
                problems.append(f"{where}: received_at is not an ISO timestamp")
                continue
        events.append(
            EventRow(
                e["key"],
                e.get("kind", "evidence"),
                e.get("title", ""),
                from_party,
                received,
                body,
                msg_path,
                e.get("forwarded_from"),
                e.get("evidence"),
                tuple(e.get("links", []) or []),
                tuple(impacts),
                _prov(e.get("provenance"), where, problems),
                e.get("source", ""),
                (e.get("note") or "").strip(),
            )
        )

    reference_rows: list[ReferenceRowIn] = []
    ref_path = root / "reference_projects.csv"
    if ref_path.exists():
        envelopes.append(Envelope.for_file(ref_path, root))
        with ref_path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                attrs = {
                    c: (row.get(c) or "").strip()
                    for c in ("iso_region", "transmission_owner", "voltage_class", "county")
                }

                def num(v: str | None) -> float | None:
                    return float(v) if v not in (None, "") else None

                reference_rows.append(
                    ReferenceRowIn(
                        row["key"],
                        row["label"],
                        row["item_code"],
                        row.get("measure", "duration"),
                        num(row.get("value_days")),
                        num(row.get("value_days_high")),
                        attrs,
                        row.get("source_url", ""),
                        _prov(row.get("provenance"), f"reference {row['key']}", problems),
                        row.get("note", ""),
                    )
                )

    facts = [
        FactRow(
            f["label"], str(f["value"]), _prov(f.get("provenance"), "fact", problems), f.get("source", "")
        )
        for f in site_doc.get("facts", [])
    ]

    cal = site.get("calendar", {}) or {}
    holidays = tuple(d for d in (_date(h, "calendar", problems) for h in cal.get("holidays", [])) if d)
    as_of = _date(site.get("as_of"), "site.as_of", problems)

    if problems:
        raise LoadError(problems)
    assert as_of is not None
    return SiteBundle(
        root=root,
        org_name=org.get("name", "Default org"),
        timezone=org.get("timezone", "UTC"),
        site_key=site["key"],
        site_name=site["name"],
        location=site.get("location", ""),
        profile=site.get("profile", ""),
        as_of=as_of,
        principal=principal,
        attrs={k: str(v) for k, v in (site.get("attrs") or {}).items()},
        holidays=holidays,
        calendar_note=(cal.get("note") or "").strip(),
        asset_key=asset["key"],
        asset_name=asset["name"],
        capacity_mw=asset.get("capacity_mw"),
        milestones=milestones,
        parties=parties,
        people=people,
        items=items,
        links=links,
        events=events,
        evidence=evidence,
        facts=facts,
        reference_rows=reference_rows,
        envelopes=envelopes,
    )
