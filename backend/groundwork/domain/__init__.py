"""Vertical-specific rules. Each subpackage exposes one DomainProfile.

This is the only place outside ``fixtures/`` where the words of a particular kind of project
are allowed. The generic packages consume a profile; they never import a vertical directly.
"""

from groundwork.core.profile import DomainProfile
from groundwork.domain.datacenter import PROFILE as DATACENTER

PROFILES: dict[str, DomainProfile] = {DATACENTER.name: DATACENTER}


def get_profile(name: str) -> DomainProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise KeyError(f"unknown domain profile {name!r}; known: {', '.join(PROFILES)}") from exc
