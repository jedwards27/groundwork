"""Changing a project after it exists, from a real project's feedback: seeing every step, editing
steps and details as drafts the person confirms, cancelled and estimated steps, steps past plan
with no word, shared people across projects, and archiving or deleting a project.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import select

from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session, owner_session
from groundwork.local import drafts, tools
from groundwork.local.confirm import decide
from groundwork.service import views
from tests import test_local_plugin as _plugin

ORIGIN = _plugin.ORIGIN
local = _plugin.local  # fixtures shared with the plugin tests
page = _plugin.page

pytestmark = pytest.mark.db


def _draft(name: str = "Connaught Place", *, people: list[str] | None = None, items: list[tools.ItemIn] | None = None) -> tools.ProjectDraft:
    emails = people if people is not None else ["colette@monette.test"]
    return tools.ProjectDraft(
        name=name,
        as_of=date(2026, 11, 3),
        finish_label="Rooms finished",
        finish_item="final",
        finish_target=date(2027, 1, 15),
        parties=[
            tools.PartyIn(
                key="designer",
                name="Monette Interiors",
                role="designer",
                people=[tools.PersonIn(name=f"Person {n}", email=e) for n, e in enumerate(emails)],
            ),
            tools.PartyIn(key="shop", name="Drapery Shop", role="vendor"),
        ],
        items=items
        or [
            tools.ItemIn(key="kickoff", title="Kickoff meeting with the designer", kind="meeting", owner="designer", status="done", finish=date(2025, 3, 1)),
            tools.ItemIn(key="palette", title="Paint palette chosen", kind="decision", owner="you", status="done", finish=None),
            tools.ItemIn(key="deposit", title="Deposit invoice paid", kind="payment", owner="you", status="done", finish=date(2025, 4, 2)),
            tools.ItemIn(key="rods", title="Curtain rods delivered", kind="delivery", owner="shop", status="not_started", finish=date(2026, 8, 4), depends_on=["deposit"]),
            tools.ItemIn(key="hang", title="Curtains installed in the living room", kind="install", owner="shop", status="not_started", finish=date(2026, 12, 1), approximate=True, depends_on=["rods"]),
            tools.ItemIn(key="final", title="Final walkthrough", kind="milestone", owner="you", status="not_started", finish=date(2027, 1, 10), depends_on=["hang"]),
        ],
    )


def _create(name: str = "Connaught Place", **kw) -> str:
    out = tools.start_project(_draft(name, **kw))
    assert "draft" in out, out
    assert decide(out["draft"], "confirm").startswith("Created")
    return out["project"]


def test_every_step_is_listed_with_new_kinds_and_estimated_dates(local):
    tools.setup("Jude Test", "jude@example.test")
    key = _create()
    out = tools.steps(key)
    assert out["total"] == 6 and out["shown"] == 6
    by = {s["item"]: s for s in out["steps"]}
    assert by["kickoff"]["kind"] == "meeting" and by["kickoff"]["finished"] == "2025-03-01"
    assert by["palette"]["status"] == "done" and by["palette"]["estimated"] is True  # finished, date not known
    assert by["hang"]["estimated"] is True and by["hang"]["kind"] == "install"
    assert by["hang"]["waits_on"] == ["rods"]
    assert [s["item"] for s in tools.steps(key, "done")["steps"]] == ["kickoff", "deposit", "palette"]
    st = tools.status(key)
    assert st["steps_total"] == 6 and "steps()" in st["every_step"]

    # The project's first ledger record keeps what it held, so later changes can be seen.
    with org_session(tools._ref(key).org_id) as s:
        first = s.execute(select(m.LedgerEntry).where(m.LedgerEntry.entry_type == "project_created")).scalar_one()
    snap = first.payload["snapshot"]
    assert len(snap["steps"]) == 6 and snap["finish"]["target"] == "2027-01-15" and len(snap["snapshot_sha256"]) == 64


def test_a_step_past_plan_with_no_word_widens_the_late_case_and_is_flagged(local):
    tools.setup("Jude Test", "jude@example.test")
    key = _create()
    st = tools.status(key)
    stale = {x["item"]: x for x in st["past_plan_no_word"]}
    assert stale["rods"]["days_past"] == (date(2026, 11, 3) - date(2026, 8, 4)).days
    assert st["finish"]["range"][1] > st["finish"]["range"][0]  # no longer a single date
    # A message about the rods after their planned date counts as word on them.
    tools.record_message(
        "Rods shipped", "Your rods shipped today and arrive next week.", "2026-11-03T09:00:00-08:00",
        project=key, source="note", progress=[tools.Progress(item="rods", status="in_progress", date=date(2026, 11, 3), why="shipped today")],
    )
    assert "rods" not in {x["item"] for x in tools.status(key)["past_plan_no_word"]}


def test_steps_change_only_when_the_person_confirms(page):
    client, _ = page
    tools.setup("Jude Test", "jude@example.test")
    key = _create()
    before = tools.status(key)["finish"]["forecast"]
    out = tools.edit_steps(
        key,
        "Rods descoped; the shop is hanging the existing ones. Add the dining room.",
        add=[tools.ItemIn(key="dining", title="Dining room curtains installed", kind="install", owner="shop", status="not_started", finish=date(2026, 12, 20), depends_on=["deposit"])],
        change=[tools.StepChange(key="rods", status="cancelled"), tools.StepChange(key="final", depends_on=["hang", "dining"])],
        remove=["kickoff"],
    )
    assert out["forecast_now"]["forecast"] == before
    # Nothing has changed yet.
    assert tools.steps(key)["total"] == 6
    view = next(d for d in client.get("/api/home").json()["drafts"] if d["id"] == out["draft"])
    texts = [ln["text"] for ln in view["lines"]]
    assert any(t.startswith("Add: Dining room curtains installed") for t in texts)
    assert any("Curtain rods delivered" in t and "cancelled" in t for t in texts)
    assert "Remove: Kickoff meeting with the designer" in texts

    r = client.post(f"/api/drafts/{out['draft']}", json={"verdict": "confirm"}, headers=ORIGIN)
    assert r.status_code == 200 and "1 added, 2 changed, 1 removed" in r.json()["message"]
    after = {s["item"]: s for s in tools.steps(key)["steps"]}
    assert "kickoff" not in after and "dining" in after
    assert after["rods"]["status"] == "cancelled" and after["rods"]["forecast"] is None
    assert sorted(after["final"]["waits_on"]) == ["dining", "hang"]
    # Cancelled steps are neither open nor past due.
    assert "rods" not in {x["item"] for x in tools.status(key)["past_plan_no_word"]}
    assert "rods" not in {x["item"] for x in tools.status(key)["waiting_on"]}
    with org_session(tools._ref(key).org_id) as s:
        rec = s.execute(select(m.LedgerEntry).where(m.LedgerEntry.entry_type == "steps_changed")).scalar_one()
    assert rec.payload["removed"] == ["kickoff"] and rec.payload["by"] == "Jude Test"


def test_edits_that_would_break_the_project_are_refused(local):
    tools.setup("Jude Test", "jude@example.test")
    key = _create()
    with pytest.raises(tools.ToolError, match="marks the finish"):
        tools.edit_steps(key, "x", remove=["final"])
    with pytest.raises(tools.ToolError, match="marks the finish"):
        tools.edit_steps(key, "x", change=[tools.StepChange(key="final", status="cancelled")])
    with pytest.raises(tools.ToolError, match="wouldn't hold together"):
        tools.edit_steps(key, "loop", change=[tools.StepChange(key="deposit", depends_on=["final"])])
    with pytest.raises(tools.ToolError, match="not a party"):
        tools.edit_steps(key, "x", change=[tools.StepChange(key="rods", owner="nobody")])
    assert drafts.pending(key, "steps") == []


def test_project_details_and_parties_change_by_draft(page):
    client, _ = page
    tools.setup("Jude Test", "jude@example.test")
    first = _create("Phase one", people=["a@one.test"])
    key = _create()
    out = tools.edit_project(
        key,
        "The designer renamed; the walkthrough moved.",
        tools.ProjectChange(
            name="Connaught Place with Monette Interiors",
            finish_target=date(2027, 2, 1),
            rename_parties=[tools.edits.PartyRename(key="designer", name="Monette Interiors LLC")],
            add_parties=[tools.PartyIn(key="painter", name="Avery Painting", role="contractor", people=[tools.PersonIn(name="Avery", email="avery@paint.test")])],
            follows=first,
        ),
    )
    view = next(d for d in client.get("/api/home").json()["drafts"] if d["id"] == out["draft"])
    assert any(ln["text"].startswith("Name: Connaught Place → Connaught Place with Monette Interiors") for ln in view["lines"])
    assert client.post(f"/api/drafts/{out['draft']}", json={"verdict": "confirm"}, headers=ORIGIN).status_code == 200
    site = client.get(f"/api/sites/{key}").json()
    assert site["name"] == "Connaught Place with Monette Interiors" and site["attrs"]["follows"] == first
    assert {p["name"] for p in site["parties"]} >= {"Monette Interiors LLC", "Avery Painting"}
    assert site["milestones"][0]["target_date"] == "2027-02-01"
    # Mail from the new party's person now routes here.
    rec = tools.record_message("Paint start", "We can start Monday.", "2026-11-03T10:00:00-08:00", from_email="avery@paint.test")
    assert rec["project"] == key


def test_overlaps_warn_and_routing_asks_unless_the_message_names_the_project(local):
    tools.setup("Jude Test", "jude@example.test")
    a = _create("Connaught Place interiors")
    out = tools.start_project(_draft("Connaught Place with Monette"))
    assert out["overlaps"][0]["project"] == a and out["overlaps"][0]["people"] == ["colette@monette.test"]
    assert decide(out["draft"], "confirm").startswith("Created")
    b = out["project"]
    with pytest.raises(tools.ToolError, match="edit_steps"):
        tools.start_project(_draft("Connaught Place with Monette"))

    unclear = tools.record_message("Fabric samples", "Samples attached.", "2026-11-03T11:00:00-08:00", from_email="colette@monette.test")
    assert unclear["recorded"] is False and sorted(unclear["candidates"]) == sorted([a, b])
    named = tools.record_message(
        "Connaught Place with Monette: fabric", "Samples attached.", "2026-11-03T11:00:00-08:00", from_email="colette@monette.test"
    )
    assert named["project"] == b and "names this one" in named["routed"]

    # Archiving the duplicate takes it out of routing: her mail now has one home.
    tools.archive_project(a, "duplicate of the Monette project")
    d = drafts.pending(a, "archive")[0]
    assert decide(d["id"], "confirm").startswith("Archived")
    routed = tools.record_message("Fabric samples", "Samples attached.", "2026-11-03T12:00:00-08:00", from_email="colette@monette.test")
    assert routed["project"] == b
    listing = tools.projects()
    assert [p["project"] for p in listing["projects"]] == [b, "lake-mariner"]
    assert listing["archived"][0]["project"] == a


def test_archive_restore_and_delete_are_the_persons_and_recorded(page):
    client, _ = page
    tools.setup("Jude Test", "jude@example.test")
    key = _create("Connaught Place interiors")
    other = _create("Keeper", people=["k@keep.test"])

    assert client.post(f"/api/projects/{key}/archive", json={"why": "duplicate"}, headers=ORIGIN).status_code == 200
    home = client.get("/api/home").json()
    assert key not in [p["project"] for p in home["projects"]] and home["archived"][0]["project"] == key
    assert client.get(f"/api/sites/{key}").json()["archived_at"]
    assert client.post(f"/api/projects/{key}/restore", headers=ORIGIN).status_code == 200
    with org_session(tools._ref(key).org_id) as s:
        kinds = [r.entry_type for r in s.execute(select(m.LedgerEntry).order_by(m.LedgerEntry.seq)).scalars()]
    assert kinds[-2:] == ["project_archived", "project_restored"]

    # Delete from a draft: Claude drafts it, the person types the key to confirm.
    d = tools.delete_project(key, "duplicate")["draft"]
    view = next(x for x in home_drafts(client) if x["id"] == d)
    assert view["type_to_confirm"] == key
    wrong = client.post(f"/api/drafts/{d}", json={"verdict": "confirm", "typed": "nope"}, headers=ORIGIN)
    assert wrong.status_code == 409
    ok = client.post(f"/api/drafts/{d}", json={"verdict": "confirm", "typed": key}, headers=ORIGIN)
    assert ok.status_code == 200 and ok.json()["message"].startswith("Deleted")
    with owner_session() as s:
        assert s.execute(select(m.Site).where(m.Site.key == key)).first() is None
        assert s.execute(select(m.Site).where(m.Site.key == other)).first() is not None
    line = json.loads((page_home(client) / "deleted.jsonl").read_text().splitlines()[-1])
    assert line["project"] == key and line["by"] == "Jude Test" and len(line["last_hash"]) == 64

    # The demo can be archived but not deleted; the other project is untouched.
    assert client.post("/api/projects/lake-mariner/delete", json={"typed": "lake-mariner"}, headers=ORIGIN).status_code == 409
    assert tools.steps(other)["total"] == 6


def test_cancelling_a_late_step_on_the_path_pulls_the_forecast_in(local):
    tools.setup("Jude Test", "jude@example.test")
    key = _create(
        items=[
            tools.ItemIn(key="a", title="Fabric ordered", kind="delivery", owner="shop", status="not_started", finish=date(2026, 11, 20)),
            tools.ItemIn(key="b", title="Custom fabric arrives", kind="delivery", owner="shop", status="not_started", finish=date(2027, 3, 1), depends_on=["a"]),
            tools.ItemIn(key="final", title="Final walkthrough", kind="milestone", owner="you", status="not_started", finish=date(2027, 1, 10), depends_on=["a", "b"]),
        ]
    )
    late = tools.status(key)["finish"]["forecast"]
    out = tools.edit_steps(key, "custom fabric descoped", change=[tools.StepChange(key="b", status="cancelled")])
    assert out["forecast_if_confirmed"]["forecast"] < late
    ref = tools._ref(key)
    with org_session(ref.org_id) as s:
        state = repo.load_state(s, key)
    assert views.chain_view(state).milestone.forecast_finish.isoformat() == late  # unchanged until confirmed


def home_drafts(client) -> list[dict]:
    return client.get("/api/home").json()["drafts"]


def page_home(client):  # noqa: ARG001 - the home folder the fixture set
    import os
    from pathlib import Path

    return Path(os.environ["GROUNDWORK_HOME"])
