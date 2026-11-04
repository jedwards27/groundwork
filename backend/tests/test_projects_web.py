"""Creating a project on the website: a form the person fills in, a forecast they check, then the
project, as an org of its own with its own ledger. In the demo, a visitor's sign-in widens to it."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from groundwork.db import models as m
from groundwork.db.session import org_session, owner_session

pytestmark = pytest.mark.db

ORIGIN = {"origin": "http://testserver"}


def kitchen(name: str = "Kitchen remodel") -> dict:
    return {
        "your_name": "Jude",
        "draft": {
            "name": name,
            "location": "Oakland, CA",
            "as_of": "2026-11-02",
            "finish_label": "Kitchen usable",
            "finish_item": "final",
            "finish_target": "2027-02-01",
            "template": "supervised",
            "parties": [
                {"key": "gc", "name": "Bayside Builders", "role": "contractor", "people": [{"name": "Bob Ruiz", "email": "bob@bayside.test"}]},
                {"key": "city", "name": "Oakland Planning & Building", "role": "ahj", "people": []},
            ],
            "items": [
                {"key": "permit", "title": "Building permit issued", "kind": "permit", "owner": "city", "status": "in_progress", "finish": "2026-12-01"},
                {"key": "cabinets", "title": "Cabinets delivered", "kind": "delivery", "owner": "gc", "status": "not_started", "finish": "2027-01-05"},
                {"key": "install", "title": "Cabinets installed", "kind": "milestone", "owner": "gc", "status": "not_started", "finish": "2027-01-20", "depends_on": ["permit", "cabinets"]},
                {"key": "final", "title": "Final inspection passed", "kind": "inspection", "owner": "city", "status": "not_started", "finish": "2027-01-28", "depends_on": ["install"]},
            ],
        },
    }


@pytest.fixture()
def visitor(seeded, env):
    env(GROUNDWORK_DEMO_LOGIN="true")
    from groundwork.api.app import app

    with TestClient(app) as c:
        assert c.post("/session").status_code == 200
        yield c
    _drop_projects()


def _drop_projects() -> None:
    from groundwork.db import repo

    with owner_session() as s:
        for org in s.execute(select(m.Org).where(m.Org.name.like("Groundwork project:%"))).scalars().all():
            repo.delete_org_data(s, org.id)
            s.delete(org)


def test_a_visitor_checks_the_forecast_then_creates_a_project_that_joins_their_sign_in(visitor):
    preview = visitor.post("/projects/preview", json=kitchen(), headers=ORIGIN)
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert p["project"] == "kitchen-remodel" and p["forecast"] and p["sets_the_date"]
    assert [x["project"] for x in visitor.get("/home").json()["projects"]] == ["lake-mariner"]  # nothing saved yet

    made = visitor.post("/projects", json=kitchen(), headers=ORIGIN)
    assert made.status_code == 200, made.text
    assert "gw_session" in made.headers["set-cookie"]
    assert {x["project"] for x in visitor.get("/home").json()["projects"]} == {"lake-mariner", "kitchen-remodel"}
    me = visitor.get("/sites/kitchen-remodel/me").json()
    assert me["person"] == "me" and me["name"] == "Jude" and me["approver"] is True
    assert visitor.get("/session").json()["you"]["name"] == "Jordan Brooks"  # still the demo's lead first
    ledger = visitor.get("/sites/kitchen-remodel/ledger?arm=").json()["entries"]
    assert any(e["type"] == "project_created" and e["payload"]["by"] == "Jude" for e in ledger)
    assert visitor.post("/projects", json=kitchen(), headers=ORIGIN).status_code == 409  # same name again


def test_a_form_with_mistakes_lists_every_problem(visitor):
    bad = kitchen()
    bad["draft"]["items"][2]["depends_on"] = ["permit", "nothing-called-this"]
    r = visitor.post("/projects/preview", json=bad, headers=ORIGIN)
    assert r.status_code == 422 and any("nothing-called-this" in p for p in r.json()["detail"])


def test_the_demo_reset_keeps_a_visitors_own_project(visitor):
    assert visitor.post("/projects", json=kitchen(), headers=ORIGIN).status_code == 200
    assert visitor.post("/demo/reset", headers=ORIGIN).status_code == 200
    assert {x["project"] for x in visitor.get("/home").json()["projects"]} == {"lake-mariner", "kitchen-remodel"}


def test_in_the_hosted_demo_a_visitors_project_is_private_and_ends_with_their_copy(seeded, env):
    env(GROUNDWORK_DEMO_LOGIN="true", GROUNDWORK_SANDBOXES="true", GROUNDWORK_SANDBOX_DAILY_CAP="20")
    from groundwork.api.app import app
    from groundwork.service import sandboxes

    try:
        with TestClient(app) as alice, TestClient(app) as bob:
            alice.post("/session")
            bob.post("/session")
            assert alice.post("/projects", json=kitchen(), headers=ORIGIN).status_code == 200
            assert "kitchen-remodel" not in {x["project"] for x in bob.get("/home").json()["projects"]}
            assert bob.get("/sites/kitchen-remodel/chain").status_code == 404
            with owner_session() as s:
                orgs = {o.name: o.expires_at for o in s.execute(select(m.Org).where(m.Org.expires_at.is_not(None))).scalars()}
            project = next(v for k, v in orgs.items() if k.startswith("Groundwork project: Kitchen remodel"))
            assert project in orgs.values() and sum(1 for v in orgs.values() if v == project) >= 2  # same end as the copy
            # Starting over replaces the copy of the demo and keeps the project.
            assert alice.post("/demo/reset", headers=ORIGIN).status_code == 200
            assert "kitchen-remodel" in {x["project"] for x in alice.get("/home").json()["projects"]}
    finally:
        sandboxes.sweep(datetime.now(UTC) + timedelta(days=365))


def test_projects_belong_to_their_own_org_and_ledger(visitor):
    visitor.post("/projects", json=kitchen(), headers=ORIGIN)
    with owner_session() as s:
        org = s.execute(select(m.Org).where(m.Org.name.like("Groundwork project: Kitchen remodel%"))).scalar_one()
    with org_session(org.id) as s:
        assert [x.key for x in s.execute(select(m.Site)).scalars()] == ["kitchen-remodel"]


def test_a_sign_in_whose_person_was_reloaded_away_counts_as_signed_out(visitor):
    from groundwork.service import reset

    assert visitor.get("/session").json()["signed_in"] is True
    reset.reset_fixtures()  # the demo's people get new ids
    assert visitor.get("/session").json()["signed_in"] is False
    assert visitor.get("/me").status_code == 401
    assert visitor.post("/session", headers=ORIGIN).status_code == 200 and visitor.get("/me").json()["person"] == "jordan"


def test_the_public_demo_does_not_create_projects(visitor, env):
    # The hosted profile refuses to start on development secrets, so it's switched on after start-up.
    env(GROUNDWORK_DEMO_LOGIN="true", GROUNDWORK_HOSTED="true")
    for path in ("/projects/preview", "/projects"):
        r = visitor.post(path, json=kitchen(), headers=ORIGIN)
        assert r.status_code == 403 and "your computer" in r.json()["detail"]
