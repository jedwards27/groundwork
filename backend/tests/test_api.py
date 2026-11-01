import pytest
from fastapi.testclient import TestClient

from groundwork.api.app import app
from groundwork.api.auth import mint
from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db.session import owner_session

pytestmark = pytest.mark.db


def _token(org_id, person_key="dana"):
    from sqlalchemy import select

    with owner_session() as s:
        p = s.execute(
            select(m.Person).where(m.Person.org_id == org_id, m.Person.key == person_key)
        ).scalar_one()
    return mint(p.id, org_id, secret=get_settings().groundwork_dev_hmac_secret, ttl_hours=1)


@pytest.fixture()
def client(seeded):
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {_token(seeded['org_a'])}"
        yield c


def test_requires_a_token(seeded):
    with TestClient(app) as c:
        assert c.get("/sites").status_code == 401
        assert c.get("/sites", headers={"Authorization": "Bearer gw1.x.y.z"}).status_code == 401


def test_sites_chain_forecast(client):
    sites = client.get("/sites").json()
    assert [x["key"] for x in sites] == ["lake-mariner"]
    assert sites[0]["gate"] == "to_accept"
    chain = client.get("/sites/lake-mariner/chain").json()
    assert chain["gate"] == "to_accept" and len(chain["items"]) == 26
    preview = client.get("/sites/lake-mariner/forecast", params={"scenario": "event-a"}).json()
    assert preview["milestone"]["forecast_finish"] == "2027-03-01"
    cp = client.get("/sites/lake-mariner/critical-path").json()
    assert [x["key"] for x in cp["critical_path"]] == ["to_accept", "witness", "l3", "l4"]
    assert client.get("/sites/nowhere/chain").status_code == 404
    assert client.get("/sites/lake-mariner/chain", params={"scenario": "nope"}).status_code == 422


def test_play_event_runs_and_persists(client):
    r = client.post("/sites/lake-mariner/events", json={"event": "event-a"})
    assert r.status_code == 202
    run = client.get(f"/runs/{r.json()['run_id']}").json()
    assert run["status"] == "done"
    kinds = [s["kind"] for s in run["summary"]["steps"]]
    assert kinds[:3] == ["queued", "running", "forecast"]
    assert ["plan", "decided", "executed", "differential", "report", "done"] == [
        k for k in kinds if k in ("plan", "decided", "executed", "differential", "report", "done")
    ]
    assert kinds[-1] == "blind_skipped"  # no live model in tests
    assert client.get("/sites/lake-mariner/chain").json()["milestone"]["forecast_finish"] == "2027-03-01"
    assert client.post("/sites/lake-mariner/events", json={"event": "event-a"}).status_code == 409
    with client.stream("GET", f"/runs/{r.json()['run_id']}/stream") as s:
        body = "".join(s.iter_text())
    assert "event: step" in body and "event: end" in body
    with client.stream("GET", f"/runs/{r.json()['run_id']}/stream", headers={"Last-Event-ID": "3"}) as s:
        resumed = "".join(s.iter_text())
    assert '"i": 4' in resumed and '"i": 1,' not in resumed


def test_other_org_cannot_see_this_orgs_run(client, seeded):
    r = client.post("/sites/lake-mariner/events", json={"event": "event-b"})
    other = {"Authorization": f"Bearer {_token(seeded['org_b'])}"}
    assert client.get(f"/runs/{r.json()['run_id']}", headers=other).status_code == 404


def test_admin_reset_needs_the_admin_token(seeded):
    with TestClient(app) as c:
        assert c.post("/admin/reset").status_code == 403


def test_demo_login_is_off_by_default_and_works_when_on(seeded, monkeypatch):
    from groundwork.config import get_settings as gs

    with TestClient(app) as c:
        assert c.get("/auth/personas").status_code == 404
        monkeypatch.setenv("GROUNDWORK_DEMO_LOGIN", "true")
        gs.cache_clear()
        try:
            people = c.get("/auth/personas").json()
            assert {p["key"] for p in people} == {"dana", "priya", "sam"}  # the principal's people only
            assert c.post("/auth/demo-login", json={"person": "morgan"}).status_code == 404
            tok = c.post("/auth/demo-login", json={"person": "dana"}).json()["token"]
            assert c.get("/me", headers={"Authorization": f"Bearer {tok}"}).json()["person"] == "dana"
            assert c.post("/auth/demo-login", json={"person": "nobody"}).status_code == 404
        finally:
            monkeypatch.delenv("GROUNDWORK_DEMO_LOGIN")
            gs.cache_clear()


def test_tamper_is_admin_only_and_detected(client, seeded, monkeypatch):
    from groundwork.config import get_settings as gs

    assert client.post("/admin/tamper").status_code == 403
    client.post("/sites/lake-mariner/events", json={"event": "event-a"})
    token = gs().groundwork_admin_token
    monkeypatch.setenv("GROUNDWORK_DEMO_ORG", seeded["bundle"].org_name)
    gs.cache_clear()
    try:
        if token:
            r = client.post("/admin/tamper", headers={"X-Admin-Token": token})
            assert r.status_code == 200
            assert client.get("/sites/lake-mariner/ledger/verify").json()["ok"] is False
    finally:
        gs.cache_clear()
