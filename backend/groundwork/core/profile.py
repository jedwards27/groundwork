"""A DomainProfile carries the rules a vertical brings to the generic engine.

The engine never adds edges from a profile. Profiles *validate* data: each OrderRule says
"wherever both item codes exist, the first must precede the second through some path".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import networkx as nx

from groundwork.core.cpm import Link


@dataclass(frozen=True)
class OrderRule:
    before: str  # item code
    after: str  # item code
    note: str = ""
    assumption: bool = False  # True when the rule itself is an assumption to verify


@dataclass(frozen=True)
class DomainProfile:
    name: str
    order_rules: tuple[OrderRule, ...] = ()
    # Party role -> role class. Classes: regulator | counterparty_binding | counterparty_routine | internal.
    role_class: Mapping[str, str] = field(default_factory=dict)
    # Business days a party in this role typically takes to respond to a request (assumptions).
    response_lag_bd: Mapping[str, int] = field(default_factory=dict)
    # Extra business days when the item's owner has this role (e.g. an independent reviewer).
    owner_extra_lag_bd: Mapping[str, int] = field(default_factory=dict)
    # Columns of the reference-class table used to group comparable items.
    reference_key: tuple[str, ...] = ("item_code",)
    # Milestone kind -> headline template, e.g. "{asset} delivers in".
    milestone_headline: Mapping[str, str] = field(default_factory=dict)
    glossary: Mapping[str, str] = field(default_factory=dict)


def validate_links(profile: DomainProfile, codes: Mapping[str, str], links: Iterable[Link]) -> list[str]:
    """Return one message per violated order rule. ``codes`` maps item key -> item code."""
    g = nx.DiGraph()
    g.add_nodes_from(codes)
    g.add_edges_from((ln.pred, ln.succ) for ln in links)
    by_code: dict[str, list[str]] = {}
    for key, code in codes.items():
        by_code.setdefault(code, []).append(key)
    problems: list[str] = []
    for rule in profile.order_rules:
        for a in by_code.get(rule.before, []):
            for b in by_code.get(rule.after, []):
                if not nx.has_path(g, a, b):
                    tag = " (rule is an assumption to verify)" if rule.assumption else ""
                    problems.append(f"{a} ({rule.before}) must precede {b} ({rule.after}){tag}: {rule.note}")
    return problems
