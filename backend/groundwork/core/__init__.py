"""Generic scheduling engine.

Nothing in this package knows what kind of project it is scheduling. Vocabulary, sequencing
rules and reference-class keys come from a DomainProfile (see ``groundwork.domain``) and from
the fixture data. A test greps this package for domain words and fails if it finds any.
"""

from groundwork.core.calendar import CalendarKind, WorkCalendar
from groundwork.core.cpm import (
    Adjustment,
    CycleError,
    Delay,
    Link,
    Schedule,
    Target,
    Task,
    TaskResult,
    schedule,
)
from groundwork.core.profile import DomainProfile, OrderRule, validate_links

__all__ = [
    "Adjustment",
    "CalendarKind",
    "CycleError",
    "Delay",
    "DomainProfile",
    "Link",
    "OrderRule",
    "Schedule",
    "Target",
    "Task",
    "TaskResult",
    "WorkCalendar",
    "schedule",
    "validate_links",
]
