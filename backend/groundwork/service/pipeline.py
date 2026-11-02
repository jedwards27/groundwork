"""The run pipeline: what happens when an event is played.

Phases (each commits, so a crash leaves a truthful partial record):
  1. apply the event's delays (schedule changes only)
  2. acknowledgments stop here: linked to pending asks for display, state unchanged
  3. informed-arm plan (Claude when configured and under the daily cap, else simulated)
  4. resolve, classify and decide every action; record proposed and decided entries
  5. execute auto actions in dry run
  6. differential (computed by the scheduler)
  7. post-execution report from the ledger, and the honesty check
  -> the run is done (the stream ends here)
  8. blind arm, trailing: same event, no mandate in the prompt; decided and recorded, never executed
"""

from __future__ import annotations

import traceback
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundwork.agent.base import PlannerError, PlannerResult
from groundwork.agent.reporter import SimulatedReporter
from groundwork.agent.simulated import SimulatedPlanner, load_plans
from groundwork.approvals import action_hash
from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session
from groundwork.executors import ExecutorDisabled, execute
from groundwork.ledger import append
from groundwork.policy.gateway import SPEND_KINDS
from groundwork.schemas.action import Autonomy
from groundwork.schemas.plan import Arm, Plan
from groundwork.service import actions as actions_svc
from groundwork.service import planctx
from groundwork.service.decisions import decide_plan, intent_check
from groundwork.service.honesty import check_report
from groundwork.service.state import SiteState


# --- helpers -----------------------------------------------------------------------------------
def step(s: Session, run_id: uuid.UUID, kind: str, text: str, **extra: Any) -> None:
    run = s.get(m.Run, run_id)
    assert run is not None
    summary = dict(run.summary or {})
    steps = list(summary.get("steps", []))
    steps.append(
        {"i": len(steps) + 1, "kind": kind, "text": text, "at": datetime.now(UTC).isoformat(), **extra}
    )
    summary["steps"] = steps
    run.summary = summary


def set_summary(s: Session, run_id: uuid.UUID, **values: Any) -> None:
    run = s.get(m.Run, run_id)
    assert run is not None
    run.summary = {**(run.summary or {}), **values}


def _site(s: Session, run: m.Run) -> tuple[m.Site, m.Event]:
    site, event = s.get(m.Site, run.site_id), s.get(m.Event, run.event_id)
    assert site is not None and event is not None
    return site, event


def ledger_tail(s: Session, limit: int = 20) -> list[dict[str, Any]]:
    rows = list(
        s.execute(
            select(m.LedgerEntry)
            .where((m.LedgerEntry.arm.is_(None)) | (m.LedgerEntry.arm == "informed"))
            .order_by(m.LedgerEntry.seq.desc())
            .limit(limit)
        ).scalars()
    )
    out = []
    for r in reversed(rows):
        p = r.payload
        out.append(
            {
                "seq": r.seq,
                "type": r.entry_type,
                "ref": p.get("ref"),
                "title": p.get("title"),
                "decision": p.get("decision"),
                "reason": p.get("reason"),
                "verdict": p.get("verdict"),
            }
        )
    return out


def local_day(recorded_at: str, tz_name: str) -> date:
    """The site-local calendar day of a ledger timestamp (stored in UTC)."""
    from zoneinfo import ZoneInfo

    return datetime.fromisoformat(recorded_at).astimezone(ZoneInfo(tz_name)).date()


def spent_today(s: Session, tz_name: str) -> int:
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(tz_name)).date()
    total = 0
    for r in s.execute(
        select(m.LedgerEntry).where(m.LedgerEntry.entry_type == "decided", m.LedgerEntry.arm == "informed")
    ).scalars():
        p = r.payload
        if (
            p.get("decision") == "auto"
            and p.get("kind") in [k.value for k in SPEND_KINDS]
            and local_day(r.recorded_at, tz_name) == today
        ):
            total += int(p.get("amount_cents") or 0)
    return total


# --- planner selection -------------------------------------------------------------------------
class Tools:
    def __init__(self, site_key: str, live: bool, note: str):
        cfg = get_settings()
        self.live, self.note = live, note
        self.simulated = SimulatedPlanner(
            load_plans(cfg.groundwork_fixtures_dir / site_key / "simulated_plans.yaml")
        )
        self.sim_reporter = SimulatedReporter()
        self.planner: Any = self.simulated
        self.reporter: Any = self.sim_reporter
        self.classifier: Any = None
        if live:
            from groundwork.agent.claude import ClaudeClassifier, ClaudePlanner, ClaudeReporter, make_client

            client = make_client(cfg.anthropic_api_key)
            self.planner = ClaudePlanner(client, cfg.groundwork_planner_model)
            self.reporter = ClaudeReporter(client, cfg.groundwork_report_model)
            self.classifier = ClaudeClassifier(client, cfg.groundwork_classifier_model)


def choose_tools(s: Session, site_key: str, force_simulated: bool = False) -> Tools:
    cfg = get_settings()
    if force_simulated or not cfg.anthropic_api_key:
        return Tools(site_key, False, "No ANTHROPIC_API_KEY: the simulated planner wrote this plan by hand.")
    # Counted across every org (each hosted visitor has their own), so the cap bounds total spend.
    if not repo.claim_daily("live_runs", cfg.groundwork_daily_live_run_cap):
        return Tools(
            site_key,
            False,
            f"Daily cap of {cfg.groundwork_daily_live_run_cap} live plans reached: simulated planner.",
        )
    return Tools(site_key, True, "")


# --- phases ------------------------------------------------------------------------------------
def _record_plan(
    s: Session, run: m.Run, arm: Arm, result: PlannerResult, planner_label: str | None = None
) -> m.Plan:
    row = m.Plan(
        org_id=run.org_id,
        run_id=run.id,
        arm=arm.value,
        planner=planner_label or result.planner,
        model_id=result.model_id,
        prompt_hash=result.prompt_hash,
        content=result.plan.model_dump(mode="json"),
        usage=result.usage,
    )
    s.add(row)
    s.flush()
    append(
        s,
        "plan_received",
        {
            "arm": arm.value,
            "planner": row.planner,
            "model_id": result.model_id,
            "prompt_hash": result.prompt_hash,
            "assessment": result.plan.assessment,
            "actions": len(result.plan.actions),
            "usage": result.usage,
            "request_id": result.request_id,
        },
        run_id=run.id,
        arm=arm.value,
    )
    return row


def plan_phase(org_id: uuid.UUID, run_id: uuid.UUID, arm: Arm, tools: Tools) -> uuid.UUID:
    with org_session(org_id) as s:
        run = s.get(m.Run, run_id)
        assert run is not None
        site, event = _site(s, run)
        state = repo.load_state(s, site.key)
        mandate = repo.active_mandate(s, site.id)
        ctx = planctx.build(state, mandate, state.event(event.key), arm, ledger_tail(s))
    planner = tools.planner if (tools.live or arm == Arm.informed) else None
    if planner is None:
        raise PlannerError("no planner for this arm")
    try:
        result = planner.plan(ctx)
        fallback_error = None
    except PlannerError as exc:
        if arm == Arm.blind:
            raise
        result, fallback_error = tools.simulated.plan(ctx), str(exc)
    with org_session(org_id) as s:
        run = s.get(m.Run, run_id)
        assert run is not None
        if fallback_error:
            append(
                s,
                "planner_fallback",
                {"error": fallback_error, "used": "simulated"},
                run_id=run_id,
                arm=arm.value,
            )
            step(
                s,
                run_id,
                "fallback",
                f"The live planner failed ({fallback_error}); the simulated plan was used instead.",
            )
        row = _record_plan(s, run, arm, result)
        label = "simulated planner" if row.planner == "simulated" else row.model_id
        step(
            s,
            run_id,
            "plan",
            f"{arm.value.capitalize()} arm: {label} proposed {len(result.plan.actions)} actions",
            arm=arm.value,
            planner=row.planner,
            model_id=row.model_id,
        )
        if arm == Arm.informed:
            set_summary(
                s,
                run_id,
                planner=row.planner,
                model_id=row.model_id,
                simulated_note=tools.note if row.planner == "simulated" else "",
            )
        return row.id


def decide_phase(org_id: uuid.UUID, run_id: uuid.UUID, plan_id: uuid.UUID, tools: Tools) -> None:
    with org_session(org_id) as s:
        run = s.get(m.Run, run_id)
        plan_row = s.get(m.Plan, plan_id)
        assert run is not None and plan_row is not None
        site, _ = _site(s, run)
        state: SiteState = repo.load_state(s, site.key)
        mandate = repo.active_mandate(s, site.id)
        plan = Plan.model_validate(plan_row.content)
        arm = plan_row.arm
        spent = spent_today(s, state.timezone) if arm == "informed" else 0
        decided = decide_plan(state, mandate, plan, spent_today_cents=spent, classifier=tools.classifier)
        for d in decided:
            a = d.action
            row = m.Action(
                org_id=run.org_id,
                run_id=run.id,
                plan_id=plan_row.id,
                arm=arm,
                ref=a.ref,
                title=a.title,
                executor=a.executor.value,
                recipient=a.recipient,
                asks_party=a.asks_party,
                params=a.params.model_dump(mode="json", exclude_none=True),
                effect=a.effect.model_dump(mode="json"),
                proposed_autonomy=a.proposed_autonomy.value,
                rationale=a.rationale,
                evidence=list(a.evidence),
                action_hash="",
            )
            row.action_hash = action_hash(row)
            s.add(row)
            s.flush()
            append(
                s,
                "proposed",
                {
                    "ref": a.ref,
                    "title": a.title,
                    "executor": a.executor.value,
                    "recipient": a.recipient,
                    "asks_party": a.asks_party,
                    "proposed_autonomy": a.proposed_autonomy.value,
                    "rationale": a.rationale,
                    "effect": row.effect,
                    "action_hash": row.action_hash,
                },
                run_id=run.id,
                action_id=row.id,
                arm=arm,
            )
            dec = d.decision
            approvers = mandate.approvers_for(dec.kind) if dec.decision == Autonomy.ask else []
            context = {
                **d.resolved.details,
                "approvers": approvers,
                "classifier_reason": d.classifier_reason,
                "missing_params": list(d.resolved.ctx.missing_params),
            }
            s.add(
                m.Decision(
                    org_id=run.org_id,
                    action_id=row.id,
                    mandate_version=mandate.version,
                    decision=dec.decision.value,
                    reason=dec.reason,
                    rule=dec.rule,
                    delta=dec.delta,
                    kind=dec.kind.value,
                    effect_class=dec.effect_class.value,
                    channel=dec.channel.value,
                    record_bearing=dec.record_bearing,
                    content_class=d.resolved.details["content_class"],
                    classifier=d.resolved.ctx.classifier,
                    amount_cents=dec.amount_cents,
                    context=context,
                )
            )
            append(
                s,
                "decided",
                {
                    "ref": a.ref,
                    "title": a.title,
                    "decision": dec.decision.value,
                    "reason": dec.reason,
                    "rule": dec.rule,
                    "delta": dec.delta,
                    "kind": dec.kind.value,
                    "record_bearing": dec.record_bearing,
                    "content_class": context["content_class"],
                    "classifier": d.resolved.ctx.classifier,
                    "amount_cents": dec.amount_cents,
                    "mandate_version": mandate.version,
                    "path": context["path"],
                    "effect_allowed": context["effect_allowed"],
                    "approvers": approvers,
                },
                run_id=run.id,
                action_id=row.id,
                arm=arm,
            )
        ic = intent_check(plan, decided)
        append(s, "intent_delta", ic, run_id=run.id, arm=arm)
        n = {k: sum(1 for d in decided if d.decision.decision.value == k) for k in ("auto", "ask", "refuse")}
        held = sum(1 for d in decided if d.decision.held)
        step(
            s,
            run_id,
            "decided" if arm == "informed" else "blind_decided",
            f"{arm.capitalize()} arm, gateway under mandate v{mandate.version} ({mandate.preset}): {n['auto']} run alone, "
            f"{n['ask']} ask a person, {n['refuse']} refused; {held} held (proposed more autonomy than allowed)",
            arm=arm,
            counts=n,
            held=held,
        )


def execute_actions(s: Session, actions: list[m.Action], run_id: uuid.UUID) -> list[str]:
    """Execute (dry run) the given informed actions. Returns refs that executed."""
    cfg = get_settings()
    done = []
    for row in actions:
        key = f"{run_id}:{row.ref}"
        append(
            s,
            "execution_requested",
            {"ref": row.ref, "title": row.title, "idempotency_key": key, "dry_run": cfg.dry_run},
            run_id=row.run_id,
            action_id=row.id,
            arm=row.arm,
        )
        try:
            if action_hash(row) != row.action_hash:
                raise ExecutorDisabled("action content no longer matches its recorded hash")
            pa = actions_svc.proposed_from_row(row)
            result = execute(pa, dry_run=cfg.dry_run, idempotency_key=key)
            append(
                s,
                "executed",
                {
                    "ref": row.ref,
                    "title": row.title,
                    "external_ref": result.external_ref,
                    "detail": result.detail,
                    "dry_run": cfg.dry_run,
                },
                run_id=row.run_id,
                action_id=row.id,
                arm=row.arm,
            )
            done.append(row.ref)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded as such
            append(
                s,
                "execution_failed",
                {"ref": row.ref, "title": row.title, "error": f"{type(exc).__name__}: {exc}"},
                run_id=row.run_id,
                action_id=row.id,
                arm=row.arm,
            )
    return done


def execute_phase(org_id: uuid.UUID, run_id: uuid.UUID, plan_id: uuid.UUID) -> None:
    with org_session(org_id) as s:
        rows = list(
            s.execute(
                select(m.Action).where(m.Action.plan_id == plan_id).order_by(m.Action.created_at)
            ).scalars()
        )
        auto = []
        for row in rows:
            latest = (
                s.execute(
                    select(m.Decision)
                    .where(m.Decision.action_id == row.id)
                    .order_by(m.Decision.created_at.desc())
                )
                .scalars()
                .first()
            )
            if latest is not None and latest.decision == "auto":
                auto.append(row)
        done = execute_actions(s, auto, run_id)
        step(s, run_id, "executed", f"Executed {len(done)} action(s) in dry run: {', '.join(done) or 'none'}")


def report_phase(org_id: uuid.UUID, run_id: uuid.UUID, plan_id: uuid.UUID, tools: Tools) -> None:
    with org_session(org_id) as s:
        run = s.get(m.Run, run_id)
        plan_row = s.get(m.Plan, plan_id)
        assert run is not None and plan_row is not None
        site, _ = _site(s, run)
        state = repo.load_state(s, site.key)
        pv = actions_svc.plan_view(s, state, plan_row)
        set_summary(s, run_id, differential=pv["differential"])
        d = pv["differential"]
        if d:
            step(
                s,
                run_id,
                "differential",
                f"Delivery: unmitigated {d['unmitigated']}; with what ran {d['now']}; if you approve the queue "
                f"{d['if_approved']}; if the counterparties agree {d['if_they_agree']} "
                f"({d['recovered_if_they_agree']} days recovered)",
                differential=d,
            )
        plan = Plan.model_validate(plan_row.content)
        entries = {
            a["ref"]: [
                t["type"] if t["type"] != "decided" else f"decided:{a['decision']}" for t in a["ledger"]
            ]
            for a in pv["actions"]
        }
        reporter = tools.reporter if plan_row.planner != "simulated" else tools.sim_reporter
        try:
            report, usage = reporter.report(plan, entries)
            reporter_name = getattr(reporter, "model", "simulated")
        except PlannerError as exc:
            report, usage = tools.sim_reporter.report(plan, entries)
            reporter_name = f"simulated (live reporter failed: {exc})"
        append(
            s,
            "report",
            {**report.model_dump(), "reporter": reporter_name, "usage": usage},
            run_id=run_id,
            arm=plan_row.arm,
        )
        check = check_report([a.ref for a in plan.actions], entries, report)
        if not check.ok:
            append(s, "report_mismatch", check.as_dict(), run_id=run_id, arm=plan_row.arm)
        set_summary(s, run_id, report=report.model_dump(), report_check=check.as_dict())
        step(
            s,
            run_id,
            "report",
            "Report matches the ledger"
            if check.ok
            else f"Report disagrees with the ledger: {check.as_dict()}",
            report_ok=check.ok,
        )


def acknowledgment_phase(org_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """A message that says 'approved' changes nothing. It is linked to pending asks for display."""
    with org_session(org_id) as s:
        run = s.get(m.Run, run_id)
        assert run is not None
        site, event = _site(s, run)
        pending = []
        for row in s.execute(select(m.Action).where(m.Action.arm == "informed")).scalars():
            latest = (
                s.execute(
                    select(m.Decision)
                    .where(m.Decision.action_id == row.id)
                    .order_by(m.Decision.created_at.desc())
                )
                .scalars()
                .first()
            )
            approved = s.execute(select(m.Approval).where(m.Approval.action_id == row.id)).first()
            if latest is not None and latest.decision == "ask" and approved is None:
                party = latest.context.get("recipient_party")
                if party == event.from_party or event.from_party in (latest.context.get("path") or []):
                    pending.append(row.ref)
        append(
            s,
            "message_received",
            {
                "event": event.key,
                "kind": event.kind,
                "title": event.title,
                "from": event.from_party,
                "linked_pending_asks": sorted(set(pending)),
                "effect": "none: an approval is a typed action by a named person; messages are evidence",
            },
            run_id=run_id,
        )
        step(
            s,
            run_id,
            "acknowledgment",
            f"'{event.title}' from {event.from_party}: linked to {len(set(pending))} pending ask(s) for display. "
            "No action changed state. Approvals come only from a named approver in Groundwork.",
            linked=sorted(set(pending)),
        )


# --- entry point -------------------------------------------------------------------------------
def execute_run(org_id: uuid.UUID, run_id: uuid.UUID, *, force_simulated: bool = False) -> None:
    try:
        with org_session(org_id) as s:
            run = s.get(m.Run, run_id)
            assert run is not None
            run.status, run.started_at = "running", datetime.now(UTC)
            site, event = _site(s, run)
            site_key, event_key, event_kind = site.key, event.key, event.kind
            step(s, run_id, "running", f"Reading '{event.title}'")
        with org_session(org_id) as s:
            state = repo.load_state(s, site_key)
            before = _milestone(state)
            # Every played event is "applied" (received); only schedule changes carry delays.
            repo.set_event_status(s, state.site_id, event_key, "applied")  # type: ignore[arg-type]
            after = _milestone(repo.load_state(s, site_key))
            set_summary(s, run_id, milestone_before=before, milestone_after=after)
            step(
                s,
                run_id,
                "forecast",
                f"{after['label']}: {before['forecast_finish']} -> {after['forecast_finish']} "
                f"(range {after['forecast_low']} to {after['forecast_high']}); gating item: {after['gate_title']}",
                before=before,
                after=after,
            )
        if event_kind == "acknowledgment":
            acknowledgment_phase(org_id, run_id)
            _finish(org_id, run_id)
            return
        with org_session(org_id) as s:
            tools = choose_tools(s, site_key, force_simulated)
        plan_id = plan_phase(org_id, run_id, Arm.informed, tools)
        decide_phase(org_id, run_id, plan_id, tools)
        execute_phase(org_id, run_id, plan_id)
        report_phase(org_id, run_id, plan_id, tools)
        _finish(org_id, run_id)
        if tools.live:
            try:
                blind_id = plan_phase(org_id, run_id, Arm.blind, tools)
                decide_phase(org_id, run_id, blind_id, tools)
            except Exception as exc:  # noqa: BLE001 - the blind arm is measurement only
                with org_session(org_id) as s:
                    step(
                        s, run_id, "blind_failed", f"Blind arm did not complete: {type(exc).__name__}: {exc}"
                    )
        else:
            with org_session(org_id) as s:
                step(s, run_id, "blind_skipped", "Blind arm skipped: it needs a live model.")
    except Exception as exc:  # noqa: BLE001 - any failure must land on the run row
        with org_session(org_id) as s:
            run = s.get(m.Run, run_id)
            if run is not None:
                message = f"{type(exc).__name__}: {exc}"
                run.status, run.finished_at, run.error = "failed", datetime.now(UTC), message
                step(s, run_id, "failed", message, trace=traceback.format_exc()[-2000:])


def _milestone(state: SiteState) -> dict[str, Any]:
    from groundwork.service import views

    c = views.chain_view(state)
    ms = c.milestone
    return {
        "label": ms.label,
        "forecast_finish": str(ms.forecast_finish),
        "forecast_low": str(ms.forecast_low),
        "forecast_high": str(ms.forecast_high),
        "delta": ms.delta_days,
        "gate": c.gate,
        "gate_title": state.item(c.gate).title if c.gate else "none",
        "critical_path": c.critical_path,
    }


def _finish(org_id: uuid.UUID, run_id: uuid.UUID) -> None:
    with org_session(org_id) as s:
        run = s.get(m.Run, run_id)
        assert run is not None
        run.status, run.finished_at = "done", datetime.now(UTC)
        step(s, run_id, "done", "Run complete")
