"""Deterministic text rules: a floor under the model classifier, and the only classifier when no
model is configured. The final class is the most severe of the rules and the model, so text can
only make a decision stricter, never looser.
"""

from __future__ import annotations

import re

from groundwork.schemas.action import ContentClass

SEVERITY = [ContentClass.none, ContentClass.commits_money, ContentClass.accepts_terms, ContentClass.waives_rights,
            ContentClass.legal_notice, ContentClass.unknown]

_RULES: list[tuple[ContentClass, re.Pattern[str]]] = [
    (ContentClass.legal_notice, re.compile(
        r"\b(notice of|hereby notif\w*|cure period|in default|event of default|terminat\w*|liquidated damages|"
        r"breach|reserv\w* (our|its|all|the) rights|remed(y|ies) under)\b", re.I)),
    (ContentClass.waives_rights, re.compile(r"\b(waive\w*|waiver|relinquish\w*|forg?o(ing|es)?|hold harmless|"
                                            r"release (any|all) claims?)\b", re.I)),
    (ContentClass.accepts_terms, re.compile(r"\b(we accept|we agree|agree to|accept(ance|ed)?|approved?|"
                                            r"go ahead with|sign[- ]off|confirm the order)\b", re.I)),
    (ContentClass.commits_money, re.compile(r"(\$\s?\d)|\b(fee|invoice|payment|pay|deposit|purchase order|"
                                            r"PO number|wire|remit\w*|expedite charge)\b", re.I)),
]


def classify_text(*parts: str | None) -> ContentClass:
    text = "\n".join(p for p in parts if p)
    found = [cls for cls, pat in _RULES if pat.search(text)]
    return max(found, key=SEVERITY.index) if found else ContentClass.none


def stricter(a: ContentClass, b: ContentClass) -> ContentClass:
    return max(a, b, key=SEVERITY.index)
