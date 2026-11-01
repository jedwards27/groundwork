"""The grant of authority and the gateway that enforces it.

The gateway is a pure function over typed requests: the planner proposes, the gateway decides,
executors only ever receive decided actions. Nothing here imports a planner, a model client or an
executor, and nothing here knows what kind of project it governs.
"""

from groundwork.policy.content_rules import classify_text
from groundwork.policy.gateway import Decision, RequestContext, decide, derive_kind
from groundwork.policy.mandate import AskRouting, AutoRule, Mandate, SpendLimit
from groundwork.policy.presets import PRESETS, build_preset

__all__ = [
    "PRESETS",
    "AskRouting",
    "AutoRule",
    "Decision",
    "Mandate",
    "RequestContext",
    "SpendLimit",
    "build_preset",
    "classify_text",
    "decide",
    "derive_kind",
]
