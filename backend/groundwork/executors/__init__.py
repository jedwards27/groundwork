"""Executors perform side effects. In v1 every executor is dry run: it describes what it would do,
returns a dry-run reference, and touches no network. This package imports no HTTP or mail client.
Executors only ever receive actions the gateway decided ``auto`` or a named person approved."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from groundwork.schemas.action import NEVER_EXECUTORS, Executor, ProposedAction


class ExecutorDisabled(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    external_ref: str
    detail: str


def _describe(a: ProposedAction) -> str:
    p = a.params
    return {
        Executor.send_email: f"Would email {a.recipient}: '{p.subject}'",
        Executor.request_meeting: f"Would ask {a.recipient} for a meeting: '{p.agenda}'",
        Executor.schedule_internal: f"Would hold {', '.join(p.attendees or [])} from {p.window_start} to {p.window_end}",
        Executor.reserve_slot: f"Would reserve with {a.recipient} from {p.window_start}",
        Executor.commit_spend: f"Would engage {a.recipient} against {p.amount_ref}: {p.scope}",
        Executor.draft_document: f"Drafted '{p.document_title}' for review",
        Executor.file_package: f"Would prepare '{p.package_title}' for a person to submit",
        Executor.escalate_to_owner: "Briefed the principal's team",
        Executor.record_decision: f"Recorded: {p.decision}",
    }.get(a.executor, a.executor.value)


def execute(action: ProposedAction, *, dry_run: bool, idempotency_key: str) -> ExecutionResult:
    if action.executor in NEVER_EXECUTORS:
        # Belt and braces: the gateway refuses these first, so reaching here is a bug.
        raise ExecutorDisabled(f"{action.executor.value} can never be executed")
    if not dry_run:
        raise ExecutorDisabled("live executors are not enabled in v1; set EXECUTORS_DRY_RUN=true")
    ref = "dry-run:" + action.executor.value + ":" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]
    return ExecutionResult(ok=True, external_ref=ref, detail=_describe(action))
