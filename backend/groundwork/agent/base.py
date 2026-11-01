"""Shared types for planners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from groundwork.schemas.plan import Arm, Plan


class PlannerError(RuntimeError):
    """The planner returned nothing usable."""


class PlannerRefused(PlannerError):
    """The model declined (stop_reason == "refusal")."""

    def __init__(self, category: str | None, explanation: str | None = None):
        self.category = category
        super().__init__(
            f"model declined the request (category: {category or 'unspecified'})"
            + (f": {explanation}" if explanation else "")
        )


@dataclass(frozen=True)
class PlanContext:
    """Everything a planner may see, already rendered by the service layer.

    ``site_state`` and ``ledger_tail`` must be byte-stable for a given site and ledger head so the
    prompt prefix caches. ``mandate_lines`` is None in the blind arm.
    """

    principal_key: str
    principal_name: str
    as_of: str
    site_state: dict[str, Any]
    ledger_tail: list[dict[str, Any]]
    never_kinds: list[str]
    owner_goals: list[str]
    glossary: dict[str, str]
    event: dict[str, Any]
    arm: Arm
    mandate_lines: list[str] | None = None


@dataclass
class PlannerResult:
    plan: Plan
    planner: str  # "claude" | "simulated"
    model_id: str
    prompt_hash: str
    usage: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None


class Planner(Protocol):
    name: str

    def plan(self, ctx: PlanContext) -> PlannerResult: ...
