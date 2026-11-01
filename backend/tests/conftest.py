"""Test setup. Database tests use the groundwork_test database (see `make db-setup`)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from groundwork.config import REPO_ROOT, get_settings

# Point the app and owner URLs at the test database before anything builds an engine.
_cfg = get_settings()
os.environ["DATABASE_URL"] = _cfg.test_database_url
os.environ["DATABASE_OWNER_URL"] = _cfg.test_database_owner_url
# Tests never call the live API unless a test opts in explicitly (marker `live`).
_LIVE_KEY = _cfg.anthropic_api_key
os.environ["ANTHROPIC_API_KEY"] = ""
get_settings.cache_clear()

FIXTURE = REPO_ROOT / "fixtures" / "lake-mariner"


def _db_available() -> bool:
    try:
        import psycopg

        url = get_settings().database_owner_url.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(url, connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    return FIXTURE


@pytest.fixture(scope="session")
def migrated_db():
    if not _db_available():
        pytest.skip("test database not reachable; run `make db-setup`")
    from alembic import command
    from alembic.config import Config

    from groundwork.db.session import engine_for

    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    url = get_settings().database_owner_url
    cfg.cmd_opts = type("o", (), {"x": [f"url={url}"]})()  # type: ignore[assignment]
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield url
    engine_for.cache_clear()


@pytest.fixture()
def seeded(migrated_db):
    """A freshly seeded org for the Lake Mariner fixture, plus a second org with a copy of it."""
    import dataclasses

    from groundwork.db import repo
    from groundwork.db.session import owner_session
    from groundwork.ingest import load_site

    bundle = load_site(FIXTURE)
    other = dataclasses.replace(bundle, org_name="Second org (isolation test)")
    with owner_session() as s:
        org_a = repo.seed_bundle(s, bundle)
        org_b = repo.seed_bundle(s, other)
    return {"org_a": org_a, "org_b": org_b, "bundle": bundle}
