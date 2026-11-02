"""A scripted event always plays with the hand-written plan, even when a live planner is configured.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02

The two-minute demo must run the same way every time, on a laptop with an API key and on the hosted
demo without one, so its event is marked scripted and the pipeline never sends it to a model.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("event", sa.Column("scripted", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("event", "scripted")
