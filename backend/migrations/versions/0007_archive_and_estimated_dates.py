"""Projects can be archived, and a step's date can be marked as an estimate.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04

Both columns are additive. Existing projects stay active, and existing steps keep exact dates.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("item", sa.Column("date_estimated", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("item", "date_estimated")
    op.drop_column("site", "archived_at")
