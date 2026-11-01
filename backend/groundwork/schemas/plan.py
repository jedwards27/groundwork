"""Plan (written by a planner before any decision) and Report (written after execution)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from groundwork.schemas.action import ProposedAction


class Arm(StrEnum):
    informed = "informed"  # the mandate is in the prompt; this plan is what the user sees and executors run
    blind = "blind"  # only the never-list and the owner's goals; feeds the scorecard, never executes


class Intent(BaseModel):
    """What the planner expects the gateway to do with each action (action refs)."""

    model_config = ConfigDict(extra="forbid")
    auto: list[str] = Field(default_factory=list)
    ask: list[str] = Field(default_factory=list)
    refuse: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessment: str
    actions: list[ProposedAction]
    intent: Intent


class Report(BaseModel):
    """Written after execution from the ledger rows; checked against the ledger."""

    model_config = ConfigDict(extra="forbid")
    did: list[str] = Field(default_factory=list)
    asked: list[str] = Field(default_factory=list)
    refused: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    summary: str
