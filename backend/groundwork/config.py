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
