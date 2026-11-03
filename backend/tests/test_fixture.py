"""Golden tests on the Lake Mariner fixture. The gate is computed, never asserted by hand."""

from datetime import date

import pytest

from groundwork.core import validate_links
from groundwork.domain import get_profile
from groundwork.ingest import load_site
from groundwork.service import views
from groundwork.service.state import SiteState


@pytest.fixture(scope="module")
def state(fixture_dir):
    return SiteState.from_bundle(load_site(fixture_dir))


def test_counts(state):
    assert len(state.items) == 26
    assert len(state.links) == 31
    assert len({i.key for i in state.items}) == 26


def test_every_row_has_provenance(state):
    allowed = {"public", "synthetic", "assumption_to_verify"}
    assert {i.provenance for i in state.items} <= allowed
    assert {p.provenance for p in state.parties} <= allowed
    public_without_url = [
        i.key for i in state.items if i.provenance == "public" and not i.source.startswith("http")
    ]
    assert public_without_url == []


def test_profile_rules_hold(state):
    _, links, _, codes = views.engine_inputs(state)
    assert validate_links(get_profile(state.profile), codes, links) == []


def test_profile_catches_a_missing_edge(state):
    _, links, _, codes = views.engine_inputs(state)
    broken = [ln for ln in links if not (ln.pred == "elec_cert" and ln.succ == "witness")]
    problems = validate_links(get_profile(state.profile), codes, broken)
    assert any("elec_cert" in p and "witness" in p for p in problems)


def test_baseline_gate_is_computed_to_accept(state):
    c = views.chain_view(state)
    assert c.gate == "to_accept"
    assert c.critical_path == ["to_accept", "witness", "l3", "l4"]
    assert c.min_float == 3
    assert c.milestone.forecast_finish == date(2027, 2, 17)
    assert c.milestone.target_date == date(2027, 2, 22)


def test_baseline_schedule_is_date_consistent(state):
    c = views.chain_view(state)
    shifted = [i.key for i in c.items if i.status != "done" and i.finish_shift_days != 0]
    assert shifted == []


def test_energization_is_very_early_january_and_delivery_follows(state):
    # Public: the first data hall begins energizing in "very early January" 2027. The fixture
    # models energization as the end of the witness test; delivery (L4) comes about six weeks later.
    ms = {m.kind: m for m in views.site_view(state).milestones}
    assert ms["energization"].forecast_finish == date(2027, 1, 6)
    assert ms["delivery"].forecast_finish == date(2027, 2, 17)


def test_christmas_sits_inside_the_witness_notice(state):
    c = views.chain_view(state)
    loss = next(x for x in c.calendar_losses if x.pred == "to_accept" and x.succ == "witness")
    assert loss.holidays == [date(2026, 12, 24), date(2026, 12, 25)]


def test_event_a_two_legs_reach_delivery(state):
    f = views.forecast_view(state, scenario=["event-a"])
    assert f.milestone.forecast_low == date(2027, 3, 29)
    assert f.milestone.forecast_finish == date(2027, 4, 13)
    assert f.milestone.forecast_high == date(2027, 4, 28)
    c = views.chain_view(state, scenario=["event-a"])
    assert c.gate == "to_accept"
    assert c.critical_path == ["to_accept", "witness", "l3", "l4"]
    reason = next(i for i in f.items if i.key == "to_accept").reason
    assert "redoes the electrical safety study" in reason and "reviews it again" in reason


def test_event_b_runs_through_witness_and_installation(state):
    c = views.chain_view(state, scenario=["event-b"])
    assert c.gate == "swgr"
    assert c.critical_path[0] == "swgr" and c.critical_path[-1] == "l4"
    assert "witness" in c.critical_path and "elec_install" in c.critical_path
    assert c.milestone.delta_days and c.milestone.delta_days > 0


def test_party_paths_follow_reached_via(state):
    assert views.path_from_principal(state, "anthropic") == []
    assert views.path_from_principal(state, "fluidstack") == ["fluidstack"]
    assert views.path_from_principal(state, "nyseg") == ["fluidstack", "terawulf", "nyseg"]
    assert views.path_from_principal(state, "ie") == ["ie"]


def test_reference_sets_are_shown_not_applied(state):
    f = views.forecast_view(state)
    gate = next(i for i in f.items if i.key == "to_accept").reference
    assert gate is not None and gate.headline == "no comparable items yet"
    l4 = next(i for i in f.items if i.key == "l4").reference
    assert l4 is not None and l4.n_points == 0 and not l4.applied
