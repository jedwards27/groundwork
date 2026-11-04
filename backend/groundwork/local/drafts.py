"""Drafts: what Claude prepares and only a named person makes real.

A draft is a new project, a mandate version or a set of date changes from a message. It is a file
under ``~/.groundwork/drafts`` until the person confirms or rejects it in the Groundwork app; the
confirmation, not the draft, is what lands in the ledger.
"""

from __future__ import annotations

import fcntl
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Literal

from groundwork.local.home import _read, _write, home

Kind = Literal["project", "mandate", "facts", "links", "people", "steps", "project_edit", "archive", "delete"]


def _dir():  # type: ignore[no-untyped-def]
    d = home() / "drafts"
    d.mkdir(exist_ok=True)
    return d


def create(kind: Kind, project: str, title: str, payload: dict[str, Any]) -> dict[str, Any]:
    doc = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "project": project,
        "title": title,
        "payload": payload,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
    }
    _write(_dir() / f"{doc['id']}.json", doc)
    return doc


def get(draft_id: str) -> dict[str, Any]:
    doc = _read(_dir() / f"{draft_id}.json")
    if doc is None:
        raise KeyError(draft_id)
    return doc


def pending(project: str | None = None, kind: Kind | None = None) -> list[dict[str, Any]]:
    out = []
    for path in sorted(_dir().glob("*.json")):
        doc = json.loads(path.read_text())
        if doc["status"] != "pending":
            continue
        if (project is None or doc["project"] == project) and (kind is None or doc["kind"] == kind):
            out.append(doc)
    return sorted(out, key=lambda d: d["created_at"])


def resolve(
    draft_id: str, status: Literal["confirmed", "rejected", "superseded"], by: str, **extra: Any
) -> dict[str, Any]:
    doc = get(draft_id)
    if doc["status"] != "pending":
        raise ValueError(f"draft {draft_id} is already {doc['status']}")
    doc.update(status=status, resolved_by=by, resolved_at=datetime.now(UTC).isoformat(), **extra)
    _write(_dir() / f"{draft_id}.json", doc)
    return doc


@contextmanager
def one_at_a_time() -> Iterator[None]:
    """Confirming and rejecting run one at a time on this computer, across threads and processes.
    A draft confirmed twice (a double click, two tabs) is applied once: the second waits, then
    finds it already confirmed. The lock is released if the process dies."""
    with open(_dir() / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
