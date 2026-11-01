"""Row-level security: the app role sees only its own org, fails closed without one, and cannot
write fixture tables. The owner role (migrations, seeding) sees everything."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import OrgScopeError, app_engine, org_session, owner_session, require_org

pytestmark = pytest.mark.db


def test_app_role_is_not_the_owner(seeded):
    with app_engine().connect() as c:
        role = c.execute(text("select current_user")).scalar()
        bypass = c.execute(text("select rolbypassrls from pg_roles where rolname = current_user")).scalar()
        owner = c.execute(text("select tableowner from pg_tables where tablename = 'item'")).scalar()
    assert role == "groundwork_app" and bypass is False and owner != role


def test_without_org_the_app_role_sees_nothing(seeded):
    with app_engine().connect() as c:
        assert c.execute(text("select count(*) from item")).scalar() == 0
        assert c.execute(text("select count(*) from org")).scalar() == 0


def test_org_isolation(seeded):
    with org_session(seeded["org_a"]) as s:
        orgs = {i.org_id for i in s.execute(select(m.Item)).scalars()}
        assert orgs == {seeded["org_a"]}
        assert s.execute(select(m.Item).where(m.Item.org_id == seeded["org_b"])).first() is None
    with owner_session() as s:
        both = {i.org_id for i in s.execute(select(m.Item)).scalars()}
    assert {seeded["org_a"], seeded["org_b"]} <= both


def test_app_role_cannot_write_fixture_tables(seeded):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with org_session(seeded["org_a"]) as s:
            s.execute(text("update item set title = 'x'"))


def test_app_role_cannot_write_into_another_org(seeded):
    with pytest.raises(ProgrammingError):
        with org_session(seeded["org_a"]) as s:
            site = s.execute(select(m.Site)).scalars().first()
            ev = s.execute(select(m.Event)).scalars().first()
            s.execute(
                text(
                    "insert into run (id, org_id, site_id, event_id, status) values "
                    "(gen_random_uuid(), :o, :s, :e, 'queued')"
                ),
                {"o": seeded["org_b"], "s": site.id, "e": ev.id},
            )


def test_require_org_outside_session_raises(seeded):
    from sqlalchemy.orm import Session

    with Session(app_engine()) as s, pytest.raises(OrgScopeError):
        require_org(s)


def test_state_round_trips_through_the_database(seeded):
    from groundwork.service import views

    with org_session(seeded["org_a"]) as s:
        state = repo.load_state(s, "lake-mariner")
    assert len(state.items) == 26 and len(state.links) == 31
    assert views.chain_view(state).gate == "to_accept"
