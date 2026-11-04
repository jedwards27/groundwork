"""The plugin's demo remembers which fixture it was seeded from, so an update reloads a changed demo.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-03

The plugin seeded Lake Mariner only on first launch. After an update, the demo kept the old build's
mandate and its old run, which no longer matched the scripted plans or the demo skill, and the demo
message reported "already played". Existing rows get no fingerprint, so each install that predates
this column reloads its demo once on the next launch.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site", sa.Column("fixture_fingerprint", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("site", "fixture_fingerprint")
