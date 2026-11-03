"""The outbound guard: a ``PreToolUse`` hook asks this before any connector tool that sends,
replies, forwards, posts or sends an invitation.

It acts only when a recipient is a person on a tracked project. Then it records a would-have-sent
record in that project's ledger and denies the call, because every project runs in dry run. Any
other call gets no decision, so the person's own use of Gmail, Slack or a calendar is untouched.
Full gateway decisions on connector sends come with real sending, which is not built yet.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select

from groundwork.db import models as m
from groundwork.db.session import owner_session
from groundwork.ledger import append
from groundwork.local.home import me

OUTBOUND = re.compile(r"(send|reply|forward|post|invite|respond|create_event|update_event)", re.IGNORECASE)
OWN_TOOLS = "mcp__plugin_groundwork_"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _subject(tool_input: dict[str, Any]) -> str:
    for k in ("subject", "title", "summary", "name"):
        v = tool_input.get(k)
        if isinstance(v, str) and v:
            return v[:200]
    return ""


def check(hook: dict[str, Any]) -> dict[str, Any]:
    """Hook output for one PreToolUse call: empty means no decision (the call proceeds)."""
    tool = str(hook.get("tool_name", ""))
    if tool.startswith(OWN_TOOLS) or not tool.startswith("mcp__") or not OUTBOUND.search(tool.rsplit("__", 1)[-1]):
        return {}
    tool_input = hook.get("tool_input") or {}
    addresses = {a.lower() for a in EMAIL.findall(json.dumps(tool_input))}
    who = me()
    addresses.discard(who.email if who else "")
    if not addresses:
        return {}
    with owner_session() as s:
        hits = s.execute(
            select(m.Person, m.Site)
            .join(m.SiteParty, m.SiteParty.party_id == m.Person.party_id)
            .join(m.Site, m.Site.id == m.SiteParty.site_id)
            .where(m.Person.email.in_(addresses))
        ).all()
        if not hits:
            return {}
        seen: dict[str, tuple[Any, list[str]]] = {}
        for person, site in hits:
            seen.setdefault(site.key, (site, []))[1].append(person.name)
        records = []
        for site, names in seen.values():
            row = append(
                s,
                "outbound_held",
                {
                    "tool": tool,
                    "recipients": sorted(set(names)),
                    "subject": _subject(tool_input),
                    "reason": "dry run: a connector call addressed to a party on this project was recorded, not sent",
                },
                org_id=site.org_id,
            )
            records.append(f"{site.name} (record #{row.seq})")
    reason = (
        f"Groundwork: this goes to someone on {', '.join(records)}. That project is in dry run, so the "
        "send was recorded in its ledger and not sent. Propose follow-ups through Groundwork's "
        "play_message or propose_plan instead."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
