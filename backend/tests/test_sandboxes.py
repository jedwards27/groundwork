"""Sandbox orgs: in the hosted demo every visitor gets a private copy of the demo, kept apart from
every other visitor by row-level security, and deleted when it expires or its visitor starts over."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from groundwork.db import models as m
from groundwork.db.session import owner_session

pytestmark = pytest.mark.db

SITE = "lake-mariner"


@pytest.fixture()
def client(seeded, env):
    env(GROUNDWORK_DEMO_LOGIN="true", GROUNDWORK_SANDBOXES="true", GROUNDWORK_SANDBOX_DAILY_CAP="20")
    from groundwork.api.app import app

    with TestClient(app) as c:
        yield c
    from groundwork.service import sandboxes

    sandboxes.sweep(datetime.now(UTC) + timedelta(days=365))  # leave no sandbox for the next test


def login(c: TestClient, person: str = "dana", token: str | None = None, fresh: bool = False) -> str:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = c.post("/auth/demo-login", json={"person": person, "fresh": fresh}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def get(c: TestClient, token: str, path: str):
    r = c.get(path, headers={"Authorization": f"Bearer {token}"})
    return r


def sandbox_count() -> int:
    with owner_session() as s:
        return s.execute(
            select(func.count()).select_from(m.Org).where(m.Org.expires_at.is_not(None))
        ).scalar_one()


def test_each_visitor_gets_a_private_sandbox(client):
    alice, bob = login(client), login(client)
    me_a, me_b = get(client, alice, "/me").json(), get(client, bob, "/me").json()
    assert me_a["org"] != me_b["org"] and "sandbox" in me_a["org"]
    assert me_a["sandbox_expires_at"] and me_b["sandbox_expires_at"]
    assert client.get("/health").json()["sandboxes"] is True

    # Alice plays event A; Bob's copy of the demo does not move.
    r = client.post(
        f"/sites/{SITE}/events", json={"event": "event-a"}, headers={"Authorization": f"Bearer {alice}"}
    )
    assert r.status_code == 202
    assert get(client, alice, f"/sites/{SITE}/latest-plan").json() is not None
    assert get(client, bob, f"/sites/{SITE}/latest-plan").json() is None
    assert get(client, bob, f"/sites/{SITE}/ledger/verify").json()["count"] == 1
    days = lambda t: get(client, t, f"/sites/{SITE}/chain").json()["milestone"]["days_remaining"]  # noqa: E731
    assert days(alice) > days(bob)
    # Bob cannot reach Alice's run even with its id.
    assert get(client, bob, f"/runs/{r.json()['run_id']}").status_code == 404


def test_switching_persona_stays_in_the_same_sandbox(client):
    dana = login(client, "dana")
    priya = login(client, "priya", token=dana)
    assert get(client, dana, "/me").json()["org"] == get(client, priya, "/me").json()["org"]
    assert sandbox_count() == 1


def test_starting_over_replaces_the_sandbox(client):
    first = login(client)
    org = get(client, first, "/me").json()["org"]
    again = login(client, token=first, fresh=True)
    assert get(client, again, "/me").json()["org"] != org
    assert get(client, first, "/me").status_code == 401  # the old sandbox is gone
    assert sandbox_count() == 1


def test_expired_sandboxes_are_swept_with_their_ledgers(client):
    from groundwork.service import sandboxes

    token = login(client)
    client.post(
        f"/sites/{SITE}/events", json={"event": "event-a"}, headers={"Authorization": f"Bearer {token}"}
    )
    with owner_session() as s:
        org = s.execute(select(m.Org).where(m.Org.expires_at.is_not(None))).scalar_one()
        org_id = org.id
        assert (
            s.execute(
                select(func.count()).select_from(m.LedgerEntry).where(m.LedgerEntry.org_id == org_id)
            ).scalar_one()
            > 1
        )
        org.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    assert sandboxes.sweep() == 1
    with owner_session() as s:
        assert s.get(m.Org, org_id) is None
        assert (
            s.execute(
                select(func.count()).select_from(m.LedgerEntry).where(m.LedgerEntry.org_id == org_id)
            ).scalar_one()
            == 0
        )
    # An expired sandbox's token no longer reaches anything; logging in again starts a new one.
    assert get(client, token, "/me").status_code == 401
    assert get(client, login(client, token=token), "/me").status_code == 200


def test_the_shared_demo_org_is_never_discarded(client, seeded):
    from groundwork.service import sandboxes

    sandboxes.discard(seeded["org_a"])
    with owner_session() as s:
        assert s.get(m.Org, seeded["org_a"]) is not None


def test_the_daily_sandbox_cap_returns_429(client, env):
    env(GROUNDWORK_SANDBOX_DAILY_CAP="1")
    login(client)
    r = client.post("/auth/demo-login", json={"person": "dana"})
    assert r.status_code == 429 and "sandboxes a day" in r.json()["detail"]


def test_without_sandboxes_everyone_shares_the_demo_org(seeded, env):
    env(GROUNDWORK_DEMO_LOGIN="true", GROUNDWORK_SANDBOXES="false")
    from groundwork.api.app import app

    with TestClient(app) as c:
        a, b = login(c), login(c)
        assert get(c, a, "/me").json()["org"] == get(c, b, "/me").json()["org"]
        assert get(c, a, "/me").json()["sandbox_expires_at"] is None
    assert sandbox_count() == 0
