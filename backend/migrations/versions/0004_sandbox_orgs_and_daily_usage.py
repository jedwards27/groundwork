"""Sandbox orgs for the hosted demo (org.expires_at) and day counters for caps that span orgs.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01

In the hosted demo every visitor gets a private copy of the fixture as its own org; row-level
security keeps visitors apart exactly as it keeps customers apart. Caps on runs, live planner calls
and new sandboxes must count across all of those orgs and survive a sandbox's deletion, so they
live in `daily_usage`, which holds counters only (ADR 0007).
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("org", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "daily_usage",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("metric", sa.Text(), primary_key=True),
        sa.Column("n", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON daily_usage TO groundwork_app")


def downgrade() -> None:
    op.drop_table("daily_usage")
    op.drop_column("org", "expires_at")
