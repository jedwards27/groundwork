"""What a run says as it works: the lines the Inbox shows, one by one, while Groundwork reads a
message, plans, checks each step against the mandate and reports. Edit the wording freely. Each
function returns one line; the run stores the line, and nothing else depends on its words (the
decisions, the ledger and the report check use the run's data, not this text)."""

from __future__ import annotations

from datetime import date
from typing import Any


def day(value: Any) -> str:
    """A date as people write it ("Feb 17, 2027"), from a date or an ISO string."""
    if not value:
        return "no date"
    d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return f"{d:%b} {d.day}, {d.year}"


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def received(title: str) -> str:
    return f"Message received: {title}"


def reading() -> str:
    return "Reading it"


def forecast(before: Any, after: Any, waiting_on: str | None) -> str:
    line = (
        f"Forecast moved from {day(before)} to {day(after)}"
        if before != after
        else f"Forecast unchanged: {day(after)}"
    )
    return line + (f". Waiting on: {waiting_on}" if waiting_on else "")


def planner_failed(error: str) -> str:
    return f"The live planner failed ({error}); the simulated plan was used instead."


# How a plan's author is named in brackets after "Planned 3 next steps".
SIMULATED_PLANNER = "simulated planner"


def planned(steps: int, author: str) -> str:
    return f"Planned {steps} next {_plural(steps, 'step', 'steps')} ({author})"


def planned_by_claude(steps: int, model_id: str, where: str) -> str:
    return planned(steps, f"{model_id} in {where}")


def comparison_planned(steps: int, author: str) -> str:
    """The comparison plan made without the mandate (kept for the record; the Inbox hides it)."""
    return f"Comparison plan without your rules: {steps} steps ({author})"


def decided(allow: int, ask: int, deny: int, held: int) -> str:
    line = f"Checked each against your rules: {allow} can go ahead, {ask} {_plural(ask, 'needs', 'need')} you, {deny} not allowed"
    if held:
        line += (
            f". The AI wanted to do {held} on its own that your rules say need you, "
            f"so the gateway held {_plural(held, 'it', 'them')}"
        )
    return line


def executed(count: int) -> str:
    return f"Did {count} on its own (a demo: recorded, not sent)" if count else "Nothing ran on its own"


def differential(days_if_they_agree: int) -> str:
    if days_if_they_agree:
        return f"If you approve what needs you and the others agree, the plan wins back {days_if_they_agree} days"
    return "The plan wins back no days by itself; it gets answers sooner"


def report(ok: bool, detail: Any) -> str:
    return (
        "Wrote its report; it matches the record" if ok else f"Its report doesn't match the record: {detail}"
    )


def acknowledgment() -> str:
    return "An automatic reply: kept as information. No action changed state; only you can approve."


def comparison_failed(error: str) -> str:
    return f"Blind arm did not complete: {error}"


def comparison_skipped() -> str:
    return "Comparison plan skipped: it needs a live model."


def done() -> str:
    return "Done"


def waiting_for_report() -> str:
    return "Waiting for Claude's report"
