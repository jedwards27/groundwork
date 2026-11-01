"""The blind arm runs beside the user's plan for measurement only: it is never executed, cannot be
approved, does not consume spend headroom, and does not move the forecast."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from groundwork.agent.base import PlannerResult
from groundwork.api.app import app
from groundwork.db import models as m
from groundwork.db.session import org_session
from groundwork.schemas import Autonomy, Plan
from groundwork.schemas.action import ActionParams, Executor, ProposedAction
from groundwork.service import pipeline
from tests.test_pipeline import by_ref, plan, play, token

pytestmark = pytest.mark.db


class FakeLivePlanner:
    """Stands in for Claude: returns the simulated plan, plus a spend action in the blind arm."""

    name = "claude"

    def __init__(self, base):
        self.base = base

    def plan(self, ctx):
        p: Plan = self.base.plans[ctx.event["key"]].model_copy(deep=True)
        if ctx.arm.value == "blind":
            for a in p.actions:
                a.proposed_autonomy = Autonomy.auto
            p.actions.append(
                ProposedAction(
                    ref="z9",
                    title="Engage the IE again",
                    executor=Executor.commit_spend,
                    recipient="ie-lead",
                    params=ActionParams(amount_ref="ie-quote", scope="x"),
                    proposed_autonomy=Autonomy.auto,
                    rationale="r",
                )
            )
        return PlannerResult(
            plan=p,
            planner="claude",
            model_id="fake-claude",
            prompt_hash="sha256:fake",
            usage={"input_tokens": 1},
        )


@pytest.fixture()
def live(monkeypatch):
    real = pipeline.choose_tools

    def fake(s, site_key, force_simulated=False):
        t = real(s, site_key, force_simulated=True)
        t.live, t.note = True, ""
        t.planner = FakeLivePlanner(t.simulated)
        return t

    monkeypatch.setattr(pipeline, "choose_tools", fake)


def test_blind_arm_is_measurement_only(live, seeded):
    with TestClient(app) as api:
        api.headers.update(token(seeded["org_a"], "dana"))
        run = play(api, "event-a")
        plans = api.get(f"/runs/{run['id']}/plans").json()
        blind = next(p for p in plans if p["arm"] == "blind")
        informed = plan(api, run)
        assert {a["state"] for a in blind["actions"]} <= {"pending", "executing", "refused"}
        assert all(not any(e["type"] == "executed" for e in a["ledger"]) for a in blind["actions"])
        assert blind["differential"] is None
        z9 = by_ref(blind)["z9"]
        assert (
            api.post(
                f"/actions/{z9['id']}/approvals", json={"verdict": "approve", "idempotency_key": "b1"}
            ).status_code
            == 409
        )
        pending = api.get("/sites/lake-mariner/actions/pending").json()
        assert {p["ref"] for p in pending} == {"a2", "a6", "a7"}
        assert informed["differential"]["recovered_if_they_agree"] == 14
        with org_session(seeded["org_a"]) as s:
            assert pipeline.spent_today(s, "America/New_York") == 1850000  # the informed a3 only
            assert s.execute(select(m.Plan).where(m.Plan.arm == "blind")).first() is not None
        sc = api.get("/sites/lake-mariner/scorecard").json()["rows"]
        assert {(r["arm"], r["model_id"]) for r in sc} == {
            ("informed", "fake-claude"),
            ("blind", "fake-claude"),
        }
        blind_row = next(r for r in sc if r["arm"] == "blind")
        assert blind_row["over_reach"] >= 3 and blind_row["label"] == "judging the owner's intent unaided"
        att = api.get("/sites/lake-mariner/attestation").json()["attestation"]
        assert att["proposal_deltas"]["blind"]["over_reach"] >= 3 and att["violations"]["count"] == 0
