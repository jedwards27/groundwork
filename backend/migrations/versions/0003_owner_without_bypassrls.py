"""The owner role no longer needs BYPASSRLS: stop forcing row-level security on table owners.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01

Managed Postgres (Neon, Render, RDS) does not let you grant BYPASSRLS, so the owner role
(migrations, seeding, reset) gets past row-level security the standard way, by owning the tables.
FORCE ROW LEVEL SECURITY would bind even the owner, so it comes off every table. The app role is
not an owner and has no BYPASSRLS, so nothing changes for it (ADR 0007, tests/test_db_rls.py).
"""

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None

_EACH = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r' AND {where}
  LOOP
    EXECUTE format('ALTER TABLE public.%I {action} ROW LEVEL SECURITY', r.relname);
  END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_EACH.format(where="c.relforcerowsecurity", action="NO FORCE"))


def downgrade() -> None:
    op.execute(_EACH.format(where="c.relrowsecurity", action="FORCE"))
