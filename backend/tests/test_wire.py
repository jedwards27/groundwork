"""The planner's wire schema must compile under the API's structured-output limits, and map back to
the domain Plan without losing anything the gateway reads."""

from groundwork.agent.simulated import load_plans
from groundwork.agent.wire import WireAction, WireEffect, WireIntent, WireParams, WirePlan, from_plan, to_plan
from groundwork.config import get_settings


def _fields(schema: dict) -> list[tuple[str, dict, bool]]:
    out = []
    objects = [schema, *schema.get("$defs", {}).values()]
    for obj in objects:
        req = set(obj.get("required", []))
        out += [(k, v, k in req) for k, v in obj.get("properties", {}).items()]
    return out


def test_wire_schema_has_no_optional_or_union_fields():
    # API limits per request: 24 optional and 16 union-typed fields. The domain Plan has 28 and 19.
    fields = _fields(WirePlan.model_json_schema())
    assert [k for k, _, required in fields if not required] == []
    assert [k for k, v, _ in fields if "anyOf" in v or isinstance(v.get("type"), list)] == []


def test_every_simulated_plan_round_trips_through_the_wire_form():
    plans = load_plans(get_settings().groundwork_fixtures_dir / "lake-mariner" / "simulated_plans.yaml")
    assert plans
    for plan in plans.values():
        assert to_plan(from_plan(plan)) == plan


def test_blanks_become_absent_and_zero_deposit_survives():
    params = dict.fromkeys(WireParams.model_fields, "")
    params.update(attendees=[], deposit_cents=0, window_start="2027-01-11")
    w = WirePlan(
        assessment="x",
        actions=[
            WireAction(
                ref="a1",
                title="t",
                executor="reserve_slot",
                recipient=" ",
                asks_party="",
                params=WireParams(**params),
                effect=WireEffect(kind="none", item="", pred="", days=0, realized_by="own_action"),
                proposed_autonomy="ask",
                rationale="r",
                evidence=[],
            )
        ],
        intent=WireIntent(auto=[], ask=["a1"], refuse=[]),
    )
    a = to_plan(w).actions[0]
    assert a.recipient is None and a.params.subject is None and a.params.attendees is None
    assert a.params.deposit_cents == 0 and a.params.window_start == "2027-01-11"
    assert a.effect.item is None and a.effect.pred is None
