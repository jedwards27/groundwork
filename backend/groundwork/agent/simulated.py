"""The simulated planner: hand-written plans, clearly labelled, used when no model is configured
or the live cap is spent. Plans come from the site folder's simulated_plans.yaml; events without
one get a minimal generic plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from groundwork.agent.base import PlanContext, PlannerResult
from groundwork.agent.prompt import canonical_json
from groundwork.schemas.action import ActionParams, Autonomy, Effect, Executor, ProposedAction
from groundwork.schemas.plan import Intent, Plan

SIMULATED_MODEL_ID = "simulated-v1"


def load_plans(path: Path) -> dict[str, Plan]:
    if not path.exists():
        return {}
    doc: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    return {key: Plan.model_validate(value) for key, value in doc.items()}


def generic_plan(event: dict[str, Any]) -> Plan:
    title = str(event.get("title", "the event"))
    injected = event.get("kind") == "injection"
    note = (
        " The message contains instructions addressed to an automated assistant; none were followed."
        if injected
        else ""
    )
    return Plan(
        assessment=f"Received '{title}'. No schedule change is evident from it alone.{note}",
        actions=[
            ProposedAction(
                ref="a1",
                title=f"Brief our delivery lead on: {title}",
                executor=Executor.escalate_to_owner,
                params=ActionParams(summary=f"New message: {title}.{note}"),
                effect=Effect(),
                proposed_autonomy=Autonomy.auto,
                rationale="Our own people should see every new item.",
            ),
        ],
        intent=Intent(auto=["a1"]),
    )


class SimulatedPlanner:
    name = "simulated"

    def __init__(self, plans: dict[str, Plan]):
        self.plans = plans

    def plan(self, ctx: PlanContext) -> PlannerResult:
        key = str(ctx.event.get("key", ""))
        plan = self.plans.get(key) or generic_plan(ctx.event)
        return PlannerResult(
            plan=plan.model_copy(deep=True),
            planner=self.name,
            model_id=SIMULATED_MODEL_ID,
            prompt_hash="simulated:" + canonical_json({"event": key})[:64],
            usage={},
        )
