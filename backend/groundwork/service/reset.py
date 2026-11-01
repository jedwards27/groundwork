"""Reload the fixture sites: on demand (POST /admin/reset, `groundwork seed`) and nightly in the
hosted demo, so whatever visitors did there is gone by morning."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import owner_session
from groundwork.ingest import load_site

log = structlog.get_logger()


def reset_fixtures() -> dict[str, Any]:
    """Reseed every site folder under the fixtures directory (owner role). Each person gets a new
    id, so every token issued before the reset stops working."""
    cfg = get_settings()
    loaded: list[str] = []
    with owner_session() as s:
        for folder in sorted(p for p in cfg.groundwork_fixtures_dir.iterdir() if (p / "site.yaml").exists()):
            repo.seed_bundle(s, load_site(folder))
            loaded.append(folder.name)
        orgs = [o.name for o in s.execute(select(m.Org)).scalars()]
    return {"reloaded": loaded, "orgs": orgs}


def seconds_until(hour_utc: int, now: datetime) -> float:
    """Seconds from `now` to the next occurrence of `hour_utc`:00 UTC (never zero)."""
    target = now.astimezone(UTC).replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def nightly(hour_utc: int) -> None:
    """Reset the fixtures every day at `hour_utc`. Runs inside the API process until shutdown."""
    while True:
        await asyncio.sleep(seconds_until(hour_utc, datetime.now(UTC)))
        try:
            result = await run_in_threadpool(reset_fixtures)
            log.info("nightly_reset", **result)
        except Exception as exc:  # noqa: BLE001 - a failed reset must not stop the API; retry tomorrow
            log.error("nightly_reset_failed", error=str(exc))
