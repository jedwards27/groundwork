"""The hosted profile: it refuses to start on development secrets, caps runs, can hold no idle
database connections, and resets itself nightly (ADR 0007)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import NullPool

from groundwork.config import Settings, hosted_problems
from groundwork.db.session import engine_for
from groundwork.service.reset import seconds_until

STRONG = {
    "groundwork_dev_hmac_secret": "s" * 48,
    "groundwork_admin_token": "a" * 32,
    "database_url": "postgresql+psycopg://groundwork_app:Xq9@db.example/groundwork?sslmode=require",
    "database_owner_url": "postgresql+psycopg://groundwork_owner:Zr4@db.example/groundwork?sslmode=require",
    "groundwork_daily_run_cap": 300,
    "groundwork_daily_live_run_cap": 30,
}


def _settings(**over) -> Settings:
    return Settings(_env_file=None, **{**STRONG, **over})  # type: ignore[call-arg]


def test_a_strong_configuration_passes():
    assert hosted_problems(_settings()) == []


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        ({"groundwork_dev_hmac_secret": ""}, "GROUNDWORK_DEV_HMAC_SECRET"),
        ({"groundwork_dev_hmac_secret": "short"}, "GROUNDWORK_DEV_HMAC_SECRET"),
        ({"groundwork_admin_token": ""}, "GROUNDWORK_ADMIN_TOKEN is missing"),
        ({"groundwork_admin_token": "s" * 48}, "must differ from the signing secret"),
        (
            {"database_url": "postgresql+psycopg://groundwork_app:groundwork_app_dev@localhost/groundwork"},
            "DATABASE_URL uses a development password",
        ),
        (
            {"database_owner_url": "postgresql+psycopg://groundwork_owner:groundwork_owner_dev@x/groundwork"},
            "DATABASE_OWNER_URL uses a development password",
        ),
        ({"database_owner_url": STRONG["database_url"]}, "different roles"),
        ({"groundwork_daily_run_cap": 0}, "GROUNDWORK_DAILY_RUN_CAP"),
        ({"groundwork_daily_live_run_cap": 1000}, "GROUNDWORK_DAILY_LIVE_RUN_CAP"),
    ],
)
def test_each_weakness_is_named(override, problem):
    assert any(problem in p for p in hosted_problems(_settings(**override)))


def test_the_development_defaults_never_pass():
    dev = Settings(_env_file=None)  # type: ignore[call-arg]
    assert len(hosted_problems(dev)) >= 4


def test_the_api_refuses_to_start_hosted_on_dev_secrets(env):
    env(GROUNDWORK_HOSTED="true", GROUNDWORK_DEV_HMAC_SECRET="dev", GROUNDWORK_ADMIN_TOKEN="")
    from groundwork.api.app import app

    with pytest.raises(RuntimeError, match="refusing to serve the hosted profile"), TestClient(app):
        pass


def test_nullpool_holds_no_connections(env):
    env(GROUNDWORK_DB_NULLPOOL="true")
    assert isinstance(engine_for("postgresql+psycopg://u:p@localhost/x").pool, NullPool)
    env(GROUNDWORK_DB_NULLPOOL="false")
    assert not isinstance(engine_for("postgresql+psycopg://u:p@localhost/x").pool, NullPool)


@pytest.mark.parametrize(
    ("now", "hour", "seconds"),
    [
        (datetime(2026, 11, 1, 7, 30, tzinfo=UTC), 8, 1800),
        (datetime(2026, 11, 1, 8, 0, tzinfo=UTC), 8, 86400),
        (datetime(2026, 11, 1, 9, 0, tzinfo=UTC), 8, 23 * 3600),
        (datetime(2026, 12, 31, 23, 59, tzinfo=UTC), 0, 60),
    ],
)
def test_the_nightly_reset_waits_for_the_next_hour(now, hour, seconds):
    assert seconds_until(hour, now) == seconds


@pytest.mark.db
def test_the_daily_run_cap_counts_across_orgs(seeded, env):
    """Each hosted visitor has their own org, so a per-org cap would bound nothing."""
    env(GROUNDWORK_DAILY_RUN_CAP="1")
    from groundwork.api.app import app
    from tests.test_api import _token

    with TestClient(app) as c:
        a = {"Authorization": f"Bearer {_token(seeded['org_a'])}"}
        b = {"Authorization": f"Bearer {_token(seeded['org_b'])}"}
        assert c.post("/sites/lake-mariner/events", json={"event": "event-a"}, headers=a).status_code == 202
        r = c.post("/sites/lake-mariner/events", json={"event": "event-a"}, headers=b)
        assert r.status_code == 429 and "runs a day" in r.json()["detail"]


@pytest.mark.db
def test_claims_count_up_to_the_cap(seeded):
    from groundwork.db.repo import claim_daily

    assert [claim_daily("probe", 2) for _ in range(3)] == [True, True, False]
    assert claim_daily("other", 1) is True
