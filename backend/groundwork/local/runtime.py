"""Start Groundwork on this computer: an embedded Postgres under ``~/.groundwork/pgdata``, the two
database roles, migrations, and the Lake Mariner demo project.

The embedded database is ``pgserver`` (a real Postgres 16 in a Python wheel), so row-level
security, the ledger's append-only trigger and the advisory lock behave exactly as in the hosted
and development setups. ``database="existing"`` uses whatever the environment already points to
(development and tests).

Nothing here writes to stdout: the plugin's tool server speaks MCP over stdout.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import structlog
from sqlalchemy import select

from groundwork.config import REPO_ROOT, get_settings
from groundwork.local.home import home, local_secrets

DEMO_SITE = "lake-mariner"


def quiet_stdout_logging() -> None:
    """Send every log line to stderr, so stdout carries only the MCP protocol."""
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(sys.stderr))
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, force=True)


def _start_embedded() -> str:
    """Start (or reuse) the embedded Postgres and create the roles. Returns its socket directory."""
    import pgserver  # type: ignore[import-not-found]  # the plugin's runtime extra (Python 3.12)

    srv = pgserver.get_server(home() / "pgdata", cleanup_mode=None)
    srv.psql((REPO_ROOT / "scripts" / "db-setup.sql").read_text())
    return parse_qs(urlparse(srv.get_uri()).query)["host"][0]


def _url(role: str, password: str, db: str, socket_dir: str) -> str:
    return f"postgresql+psycopg://{role}:{password}@/{db}?host={socket_dir}"


def configure(database: Literal["embedded", "existing"]) -> None:
    """Point the settings at the local database and the local secrets, before anything connects."""
    from groundwork.db.session import engine_for

    secrets = local_secrets()
    if database == "embedded":
        sock = _start_embedded()
        os.environ["DATABASE_URL"] = _url("groundwork_app", "groundwork_app_dev", "groundwork", sock)
        os.environ["DATABASE_OWNER_URL"] = _url("groundwork_owner", "groundwork_owner_dev", "groundwork", sock)
        # Project data reaches Anthropic only through the person's own Claude app, never from here.
        os.environ["ANTHROPIC_API_KEY"] = ""
    os.environ["GROUNDWORK_DEV_HMAC_SECRET"] = secrets["hmac_secret"]
    os.environ["GROUNDWORK_ADMIN_TOKEN"] = secrets["admin_token"]
    os.environ["EXECUTORS_DRY_RUN"] = "true"
    os.environ["GROUNDWORK_HOSTED"] = "false"
    os.environ["GROUNDWORK_DEMO_LOGIN"] = "false"
    os.environ["GROUNDWORK_LOCAL"] = "true"
    get_settings.cache_clear()
    engine_for.cache_clear()


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={get_settings().database_owner_url}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")


def seed_demo() -> bool:
    """Load Lake Mariner the first time. Returns True if it was loaded now."""
    from groundwork.db import models as m
    from groundwork.db import repo
    from groundwork.db.session import owner_session
    from groundwork.ingest import load_site

    with owner_session() as s:
        if s.execute(select(m.Site).where(m.Site.key == DEMO_SITE)).first() is not None:
            return False
        repo.seed_bundle(s, load_site(get_settings().groundwork_fixtures_dir / DEMO_SITE))
    return True


def boot(database: Literal["embedded", "existing"] = "embedded") -> dict[str, Any]:
    from groundwork.service.runs import sweep_interrupted

    quiet_stdout_logging()
    configure(database)
    migrate()
    seeded = seed_demo()
    swept = sweep_interrupted()
    return {"home": str(home()), "database": database, "demo_seeded": seeded, "runs_swept": swept}
