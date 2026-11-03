import pytest
from fastapi.testclient import TestClient

from groundwork.api.app import app
from groundwork.api.auth import mint
from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db.session import owner_session

pytestmark = pytest.mark.db


def _token(org_id, person_key="jordan"):
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
    assert preview["milestone"]["forecast_finish"] == "2027-04-13"
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
    assert client.get("/sites/lake-mariner/chain").json()["milestone"]["forecast_finish"] == "2027-04-13"
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


def test_demo_sign_in_is_off_by_default_and_signs_in_the_one_demo_person(seeded, monkeypatch):
    from groundwork.config import get_settings as gs

    with TestClient(app) as c:
        assert c.post("/auth/demo-login").status_code == 404
        assert c.post("/session").status_code == 404
        monkeypatch.setenv("GROUNDWORK_DEMO_LOGIN", "true")
        gs.cache_clear()
        try:
            assert c.get("/auth/personas").status_code == 404  # no choosing who to be
            tok = c.post("/auth/demo-login").json()["token"]
            assert c.get("/me", headers={"Authorization": f"Bearer {tok}"}).json()["person"] == "jordan"
            assert c.get("/session").json()["signed_in"] is False

            # A browser signs in with a cookie its scripts cannot read.
            r = c.post("/session")
            assert r.status_code == 200 and "token" not in r.json()
            assert "httponly" in r.headers["set-cookie"].lower()
            s = c.get("/session").json()
            assert s["signed_in"] and s["you"]["name"] == "Jordan Brooks" and s["you"]["demo_lead"] is True
            assert c.get("/me").json()["person"] == "jordan"
        finally:
            monkeypatch.delenv("GROUNDWORK_DEMO_LOGIN")
            gs.cache_clear()


def test_a_cookie_cannot_carry_a_state_change_from_another_site(seeded, monkeypatch):
    from groundwork.config import get_settings as gs

    monkeypatch.setenv("GROUNDWORK_DEMO_LOGIN", "true")
    gs.cache_clear()
    try:
        with TestClient(app) as c:
            c.post("/session")
            play = {"event": "event-a"}
            assert c.post("/sites/lake-mariner/events", json=play).status_code == 403  # no Origin
            evil = {"origin": "https://elsewhere.example"}
            assert c.post("/sites/lake-mariner/events", json=play, headers=evil).status_code == 403
            ours = {"origin": "http://testserver"}
            assert c.post("/sites/lake-mariner/events", content="event=event-a", headers=ours | {"content-type": "application/x-www-form-urlencoded"}).status_code == 403
            assert c.post("/sites/lake-mariner/events", json=play, headers=ours).status_code == 202
            assert c.get("/sites/lake-mariner/events").status_code == 200  # reads need no proof
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
