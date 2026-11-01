"""Settings, read from the environment and the repo-root .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    anthropic_api_key: str = ""
    groundwork_planner_model: str = "claude-opus-5-5"
    groundwork_classifier_model: str = "claude-haiku-5-5"
    groundwork_report_model: str = "claude-haiku-5-5"

    database_url: str = "postgresql+psycopg://groundwork_app:groundwork_app_dev@localhost:5432/groundwork"
    database_owner_url: str = (
        "postgresql+psycopg://groundwork_owner:groundwork_owner_dev@localhost:5432/groundwork"
    )
    test_database_url: str = (
        "postgresql+psycopg://groundwork_app:groundwork_app_dev@localhost:5432/groundwork_test"
    )
    test_database_owner_url: str = (
        "postgresql+psycopg://groundwork_owner:groundwork_owner_dev@localhost:5432/groundwork_test"
    )

    groundwork_dev_hmac_secret: str = ""
    groundwork_token_ttl_hours: int = 24
    executors_dry_run: bool = True
    groundwork_hosted: bool = False
    groundwork_daily_live_run_cap: int = 50
    # Every run (simulated or live) per org per UTC day; 0 means no cap. The hosted demo sets one.
    groundwork_daily_run_cap: int = 0
    # Open a database connection per request instead of keeping a pool, so a scale-to-zero
    # Postgres (Neon's free plan) can suspend between visits. Hosted only.
    groundwork_db_nullpool: bool = False
    # Reload every fixture site at this UTC hour each day (0-23); -1 turns it off. Hosted only.
    groundwork_nightly_reset_utc_hour: int = -1
    groundwork_admin_token: str = ""
    # Demo personas: lets the web app's server log in as a seeded person without a password.
    # On by default for local use and the hosted demo; off for any real deployment.
    groundwork_demo_login: bool = False
    groundwork_demo_org: str = "Groundwork demo org (end-user posture)"
    groundwork_fixtures_dir: Path = REPO_ROOT / "fixtures"

    @property
    def dry_run(self) -> bool:
        """Executors never send while this is true. The hosted profile forces it on."""
        return True if self.groundwork_hosted else self.executors_dry_run

    @property
    def token_ttl_hours(self) -> int:
        return 1 if self.groundwork_hosted else self.groundwork_token_ttl_hours


@lru_cache
def get_settings() -> Settings:
    return Settings()


DEV_PASSWORDS = ("groundwork_app_dev", "groundwork_owner_dev")


def hosted_problems(cfg: Settings) -> list[str]:
    """Why this configuration must not serve the public hosted demo; empty when it may.

    The API refuses to start in the hosted profile while any of these holds, so a deploy can never
    run on the development secrets or database passwords (the stop-ship list in the README).
    """
    problems: list[str] = []
    if len(cfg.groundwork_dev_hmac_secret) < 32:
        problems.append("GROUNDWORK_DEV_HMAC_SECRET is missing or shorter than 32 characters")
    if len(cfg.groundwork_admin_token) < 20:
        problems.append("GROUNDWORK_ADMIN_TOKEN is missing or shorter than 20 characters")
    if cfg.groundwork_admin_token and cfg.groundwork_admin_token == cfg.groundwork_dev_hmac_secret:
        problems.append("GROUNDWORK_ADMIN_TOKEN must differ from the signing secret")
    for name, url in (("DATABASE_URL", cfg.database_url), ("DATABASE_OWNER_URL", cfg.database_owner_url)):
        if any(p in url for p in DEV_PASSWORDS):
            problems.append(f"{name} uses a development password")
    if cfg.database_url == cfg.database_owner_url:
        problems.append("DATABASE_URL and DATABASE_OWNER_URL must use different roles")
    if cfg.groundwork_daily_run_cap <= 0:
        problems.append("GROUNDWORK_DAILY_RUN_CAP must be a positive number on a public demo")
    if not 0 <= cfg.groundwork_daily_live_run_cap <= 200:
        problems.append("GROUNDWORK_DAILY_LIVE_RUN_CAP must be between 0 and 200")
    return problems
