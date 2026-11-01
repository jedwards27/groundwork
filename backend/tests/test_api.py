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
    assert [s["kind"] for s in run["summary"]["steps"]] == ["queued", "running", "forecast", "done"]
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
