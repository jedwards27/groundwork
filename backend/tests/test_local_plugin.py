"""The Claude plugin's local runtime: tools, the web app on this computer, mandate drafts, routing
and the guard.

Claude proposes through the tools; only the named person, in the web app, approves or confirms.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from groundwork.agent.simulated import load_plans
from groundwork.agent.wire import from_plan
from groundwork.api.auth import mint
from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session, owner_session
from groundwork.ingest import load_site
from groundwork.local import drafts, guard, tools
from groundwork.local.home import local_secrets, write_port
from groundwork.policy.terms import MandateTerms
from groundwork.schemas.plan import Report
from tests.conftest import FIXTURE

pytestmark = pytest.mark.db


ORIGIN = {"origin": "http://127.0.0.1:8765"}


@pytest.fixture()
def local(migrated_db, tmp_path, monkeypatch):
    """Only the demo project, a fresh home folder, the local runtime's settings, and no API key."""
    monkeypatch.setenv("GROUNDWORK_HOME", str(tmp_path))
    monkeypatch.setenv("GROUNDWORK_LOCAL", "true")
    get_settings.cache_clear()
    with owner_session() as s:
        for org in s.execute(select(m.Org)).scalars().all():
            repo.delete_org_data(s, org.id)
            s.delete(org)
        repo.seed_bundle(s, load_site(FIXTURE))
        s.execute(text("DELETE FROM daily_usage"))
    write_port(8765)
    yield tmp_path
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.fixture()
def page(local):
    """The web app as the plugin serves it, opened from Claude's link (which sets the cookie)."""
    from groundwork.api.server import create

    client = TestClient(create(local=True), base_url="http://127.0.0.1:8765")
    base = f"/p/{local_secrets()['page_token']}"
    opened = client.get(f"{base}/", follow_redirects=False)
    assert opened.status_code == 303 and opened.headers["location"] == "/"
    return client, base


def decide(client, draft: str, verdict: str = "confirm") -> dict:
    r = client.post(f"/api/drafts/{draft}", json={"verdict": verdict}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()


def _project_draft() -> tools.ProjectDraft:
    return tools.ProjectDraft(
        name="Kitchen remodel",
        location="Oakland, CA",
        as_of=date(2026, 11, 2),
        finish_label="Kitchen usable",
        finish_item="final",
        finish_target=date(2027, 2, 1),
        parties=[
            tools.PartyIn(key="gc", name="Bayside Builders", role="contractor", people=[tools.PersonIn(name="Bob Ruiz", email="bob@bayside.test")]),
            tools.PartyIn(key="city", name="Oakland Planning & Building", role="ahj", people=[tools.PersonIn(name="Permit desk", email="permits@oakland.test")]),
        ],
        items=[
            tools.ItemIn(key="design", title="Design approved", kind="approval", owner="you", status="done", finish=date(2026, 10, 1)),
            tools.ItemIn(key="permit", title="Building permit issued", kind="permit", owner="city", status="in_progress", finish=date(2026, 12, 1), depends_on=["design"]),
            tools.ItemIn(key="cabinets", title="Cabinets delivered", kind="delivery", owner="gc", status="not_started", finish=date(2027, 1, 5)),
            tools.ItemIn(key="install", title="Cabinets installed", kind="milestone", owner="gc", status="not_started", finish=date(2027, 1, 20), depends_on=["permit", "cabinets"]),
            tools.ItemIn(key="final", title="Final inspection passed", kind="inspection", owner="city", status="not_started", finish=date(2027, 1, 28), depends_on=["install"]),
        ],
    )


def test_projects_and_status_use_the_product_words(local):
    tools.setup("Jude Test", "jude@example.test")
    listing = tools.projects()
    assert [p["project"] for p in listing["projects"]] == ["lake-mariner"]
    assert listing["you"]["name"] == "Jude Test"
    st = tools.status("lake-mariner")
    assert st["sets_the_date"]["item"] == "to_accept"
    assert any(msg["message"] == "demo-monday" and msg["scripted_demo"] for msg in st["messages_not_played"])
    assert st["mandate"]["template"] == "Standard" and st["mandate"]["dry_run"] is True


def test_the_scripted_demo_plays_through_the_tools_and_waits_for_a_person(page):
    client, base = page
    result = tools.play_message("lake-mariner", "demo-monday")
    decisions = {a["ref"]: a["decision"] for a in result["actions"]}
    assert decisions == {"a1": "allow", "a2": "ask", "a3": "deny"}
    a2 = next(a for a in result["actions"] if a["ref"] == "a2")
    assert a2["route"] == ["Anthropic", "Fluidstack", "TeraWulf (Lake Mariner Data LLC)"]
    assert "direct counterparties only" in a2["clause"]
    assert result["report_check"]["ok"] is True
    assert [a["ref"] for a in tools.pending()["asks"]] == ["a2"]

    # In the app, you approve as the demo's lead, the one approver its mandate names.
    ask = client.get("/api/home").json()["asks"][0]
    assert ask["ref"] == "a2" and ask["can_approve"] and ask["approvers"] == ["Dana Ortiz"]
    assert ask["route"] == ["Anthropic", "Fluidstack", "TeraWulf (Lake Mariner Data LLC)"]
    action_id = _action_id("a2")
    assert client.get("/p/not-the-token/").status_code == 404
    approve = {"verdict": "approve", "idempotency_key": "k1"}
    assert client.post(f"/api/actions/{action_id}/approvals", json=approve).status_code == 403  # no Origin
    with owner_session() as s:
        sam = s.execute(select(m.Person).where(m.Person.key == "sam")).scalar_one()
        sam_token = mint(sam.id, sam.org_id, secret=get_settings().groundwork_dev_hmac_secret, ttl_hours=1)
    viewer = TestClient(client.app, base_url="http://127.0.0.1:8765")
    assert viewer.post(f"/api/actions/{action_id}/approvals", json=approve, headers={"authorization": f"Bearer {sam_token}"}).status_code == 403
    r = client.post(f"/api/actions/{action_id}/approvals", json=approve, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["executed"] == ["a2"]
    with org_session(_org("lake-mariner")) as s:
        approval = s.execute(select(m.Approval)).scalar_one()
        action = s.get(m.Action, approval.action_id)
        assert action is not None
        assert approval.action_hash == action.action_hash and approval.mandate_version == 1
        types = [e.entry_type for e in s.execute(select(m.LedgerEntry).where(m.LedgerEntry.action_id == action.id)).scalars()]
    assert "approval" in types and "executed" in types
    assert tools.pending()["asks"] == []


def test_a_plan_written_in_the_app_goes_through_the_gateway_and_its_report_is_checked(local):
    out = tools.play_message("lake-mariner", "event-a")
    assert out["needs_plan"] is True and "Rules:" in out["instructions"]
    plan = from_plan(load_plans(FIXTURE / "simulated_plans.yaml")["event-a"])
    result = tools.propose_plan("lake-mariner", "event-a", plan, "claude-test-model")
    assert result["status"] == "waiting_model"
    by = {a["ref"]: a for a in result["actions"]}
    assert all(a["decision"] in ("allow", "ask", "deny") and a["clause"] for a in by.values())
    did = [r for r, a in by.items() if a["state"] == "executed"]
    asked = [r for r, a in by.items() if a["state"] == "pending"]
    refused = [r for r, a in by.items() if a["decision"] == "deny"]

    # A report that claims an action still waiting for a person already ran is caught.
    assert asked, "event A's plan leaves at least one ask waiting"
    wrong = tools.submit_report(result["run"], Report(did=did + asked[:1], asked=asked[1:], refused=refused, summary="all done"))
    assert wrong["report_matches_ledger"] is False
    with pytest.raises(tools.ToolError):
        tools.submit_report(result["run"], Report(did=did, asked=asked, refused=refused, summary="again"))
    with org_session(_org("lake-mariner")) as s:
        plan_row = s.execute(select(m.Plan)).scalars().first()
        assert plan_row is not None and plan_row.model_id == "claude-test-model (self-reported)"
        assert s.execute(select(m.LedgerEntry).where(m.LedgerEntry.entry_type == "report_mismatch")).first()


def test_an_honest_report_matches(local):
    plan = from_plan(load_plans(FIXTURE / "simulated_plans.yaml")["event-a"])
    result = tools.propose_plan("lake-mariner", "event-a", plan, "claude-test-model")
    by = {a["ref"]: a for a in result["actions"]}
    report = Report(
        did=[r for r, a in by.items() if a["state"] == "executed"],
        asked=[r for r, a in by.items() if a["state"] == "pending"],
        refused=[r for r, a in by.items() if a["decision"] == "deny"],
        summary="What the gateway decided.",
    )
    assert tools.submit_report(result["run"], report)["report_matches_ledger"] is True


def test_a_mandate_drafted_in_plain_words_changes_nothing_until_the_person_confirms(page):
    client, base = page
    tools.setup("Jude Test", "jude@example.test")
    tools.play_message("lake-mariner", "demo-monday")  # leaves a2 waiting
    words = "Let it ask TeraWulf through Fluidstack on its own, and never commit money."
    terms = MandateTerms(template="auto", also_never=["commit"])
    out = tools.draft_mandate("lake-mariner", words, terms)
    assert out["version"] == 2 and out["changes"]["added"]
    with org_session(_org("lake-mariner")) as s:
        site = s.execute(select(m.Site)).scalar_one()
        assert repo.active_mandate(s, site.id).version == 1  # a draft is not a mandate
    decide(client, out['draft'])
    with org_session(_org("lake-mariner")) as s:
        site = s.execute(select(m.Site)).scalar_one()
        current = repo.active_mandate(s, site.id)
        issued = list(s.execute(select(m.LedgerEntry).where(m.LedgerEntry.entry_type == "mandate_issued").order_by(m.LedgerEntry.seq)).scalars())[-1]
        redecided = [
            e.payload for e in s.execute(select(m.LedgerEntry).where(m.LedgerEntry.entry_type == "decided")).scalars()
            if e.payload.get("redecided")
        ]
    assert current.version == 2 and current.preset == "autonomous" and "commit" in [k.value for k in current.never]
    assert issued.payload["words"] == words
    assert [p["ref"] for p in redecided] == ["a2"] and redecided[0]["decision"] == "auto"
    assert drafts.get(out["draft"])["status"] == "confirmed"


def test_tools_cannot_approve_confirm_or_issue(local):
    import asyncio

    from groundwork.local.mcp_server import server

    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {
        "setup", "projects", "status", "play_message", "propose_plan", "submit_report", "record_message",
        "check_overdue", "change_links", "add_people", "move_message", "draft_mandate", "start_project",
        "pending", "ledger", "verify_record",
    }
    assert not any(w in n for n in names for w in ("approve", "confirm", "issue", "grant"))


def test_a_new_project_routes_its_own_mail_and_dates_move_only_when_confirmed(page):
    client, base = page
    tools.setup("Jude Test", "jude@example.test")
    out = tools.start_project(_project_draft())
    assert out["project"] == "kitchen-remodel" and out["sets_the_date"]
    assert "kitchen-remodel" not in tools._index()  # a draft until confirmed
    decide(client, out['draft'])
    assert "kitchen-remodel" in tools._index()
    st = tools.status("kitchen-remodel")
    assert st["mandate"]["template"] == "Supervised"

    rec = tools.record_message(
        subject="Cabinet delivery slipping",
        body="Our supplier says cabinets ship two to three weeks late.",
        received_at="2026-11-05T09:00:00-08:00",
        from_email="Bob Ruiz <bob@bayside.test>",
        to_emails=["jude@example.test"],
        thread_id="t-100",
        kind="schedule_change",
        date_changes=[tools.DateChange(item="cabinets", low_days=14, high_days=21, why="ship two to three weeks late")],
    )
    assert rec["recorded"] and rec["project"] == "kitchen-remodel"
    assert tools.status("kitchen-remodel")["as_of"] == "2026-11-05"
    before = tools.status("kitchen-remodel")["finish"]["forecast"]
    decide(client, rec['to_confirm']['draft'])
    plan = tools.play_message("kitchen-remodel", rec["message"])
    assert plan["needs_plan"] is True

    # A reply on the same thread routes by thread even from an unknown sender.
    again = tools.record_message("Re: Cabinet delivery", "Update.", "2026-11-06T10:00:00Z", "someone@else.test", [], thread_id="t-100")
    assert again["project"] == "kitchen-remodel"
    # A stranger with no thread is not filed anywhere.
    stray = tools.record_message("Newsletter", "Hi", "2026-11-06T10:00:00Z", "news@letter.test", ["jude@example.test"])
    assert stray["recorded"] is False and stray["candidates"] == []
    moved = tools.move_message("kitchen-remodel", again["message"], "lake-mariner")
    assert moved["moved"]
    with org_session(_org("kitchen-remodel")) as s:
        types = [e.entry_type for e in s.execute(select(m.LedgerEntry).order_by(m.LedgerEntry.seq)).scalars()]
    assert {"project_created", "message_recorded", "facts_confirmed", "message_moved", "clock_advanced"} <= set(types)
    assert before is not None


def test_the_guard_holds_mail_to_project_parties_and_leaves_everything_else(page):
    client, base = page
    tools.setup("Jude Test", "jude@example.test")
    out = tools.start_project(_project_draft())
    decide(client, out['draft'])
    send = {"tool_name": "mcp__gmail__send_message", "tool_input": {"to": ["bob@bayside.test"], "subject": "Cabinets?"}}
    held = guard.check(send)
    assert held["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Kitchen remodel" in held["hookSpecificOutput"]["permissionDecisionReason"]
    assert client.post(f"{base}/guard", json=send).json()["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert guard.check({"tool_name": "mcp__gmail__send_message", "tool_input": {"to": ["friend@else.test"]}}) == {}
    assert guard.check({"tool_name": "mcp__gmail__create_draft", "tool_input": {"to": ["bob@bayside.test"]}}) == {}
    assert guard.check({"tool_name": "mcp__plugin_groundwork_groundwork__record_message", "tool_input": {"from_email": "bob@bayside.test"}}) == {}
    with org_session(_org("kitchen-remodel")) as s:
        held_rows = list(s.execute(select(m.LedgerEntry).where(m.LedgerEntry.entry_type == "outbound_held")).scalars())
    assert len(held_rows) >= 2 and held_rows[0].payload["recipients"] == ["Bob Ruiz"]


def test_a_receipt_verifies_in_the_app_and_a_forged_copy_does_not(page):
    client, _ = page
    tools.play_message("lake-mariner", "demo-monday")
    rows = client.get("/api/sites/lake-mariner/ledger?arm=").json()["entries"]
    copy = next(r for r in rows if r["seq"] == 8)
    check = "/api/sites/lake-mariner/ledger/verify-entry"
    assert client.post(check, json={"seq": 8, "entry": copy}, headers=ORIGIN).json()["match"] is True
    copy["payload"] = {**copy["payload"], "decision": "auto"} if "decision" in copy["payload"] else {**copy["payload"], "x": 1}
    assert client.post(check, json={"seq": 8, "entry": copy}, headers=ORIGIN).json()["match"] is False
    assert tools.verify_record("lake-mariner", 8, copy)["match"] is False


def _org(project: str):
    return tools._ref(project).org_id


def _action_id(ref: str):
    with owner_session() as s:
        return s.execute(select(m.Action.id).where(m.Action.ref == ref, m.Action.arm == "informed")).scalar_one()


def test_settings_point_at_the_test_database(local):
    assert "groundwork_test" in get_settings().database_url


def test_the_guard_script_asks_the_running_page_and_does_nothing_without_it(page, tmp_path):
    import json
    import os
    import subprocess
    import time
    import urllib.request

    from groundwork.config import REPO_ROOT
    from groundwork.local.mcp_server import start_page

    client, base = page
    tools.setup("Jude Test", "jude@example.test")
    out = tools.start_project(_project_draft())
    decide(client, out['draft'])
    script = str(REPO_ROOT / "plugin" / "hooks" / "outbound-guard.sh")

    def hook(home: str, to: str) -> subprocess.CompletedProcess[str]:
        call = {"tool_name": "mcp__gmail__send_message", "tool_input": {"to": to}}
        env = {"GROUNDWORK_HOME": home, "PATH": "/usr/bin:/bin"}
        return subprocess.run([script], input=json.dumps(call), capture_output=True, text=True, env=env)

    nothing = tmp_path / "no-groundwork-here"
    nothing.mkdir()
    quiet = hook(str(nothing), "bob@bayside.test")
    assert quiet.returncode == 0 and quiet.stdout == ""

    port = start_page()
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            break
        except OSError:
            time.sleep(0.05)
    home = os.environ["GROUNDWORK_HOME"]
    assert json.loads(hook(home, "bob@bayside.test").stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert json.loads(hook(home, "friend@else.test").stdout) == {}


# --- batch 1: safety, errors and the page ----------------------------------------------------------
def _created(client, base, draft=None) -> str:
    tools.setup("Jude Test", "jude@example.test")
    out = tools.start_project(draft or _project_draft())
    decide(client, out["draft"])
    return out["project"]


def test_a_stale_project_draft_can_never_replace_a_project(page):
    client, base = page
    tools.setup("Jude Test", "jude@example.test")
    first = tools.start_project(_project_draft())
    second = tools.start_project(_project_draft())
    assert second["replaced_drafts"] == [first["draft"]]
    assert drafts.get(first["draft"])["status"] == "superseded"
    stale = decide(client, first["draft"])["message"]
    assert "already superseded" in stale and "kitchen-remodel" not in tools._index()
    decide(client, second['draft'])
    tools.record_message("Note", "hello", "2026-11-03T09:00:00Z", project="kitchen-remodel", source="note")
    with org_session(_org("kitchen-remodel")) as s:
        before = s.execute(select(m.LedgerEntry)).scalars().all()
    # Even a draft written before the project existed cannot reload it over the top.
    sneaky = drafts.create("project", "kitchen-remodel", "again", {"folder": drafts.get(second["draft"])["payload"]["folder"]})
    msg = decide(client, sneaky["id"])["message"]
    assert "already exists" in msg
    with org_session(_org("kitchen-remodel")) as s:
        assert len(s.execute(select(m.LedgerEntry)).scalars().all()) == len(before)


def test_claude_sees_groundworks_own_error_messages(local):
    import asyncio

    from mcp.server.mcpserver.exceptions import ToolError as McpToolError

    from groundwork.local.mcp_server import server

    with pytest.raises(McpToolError) as exc:
        asyncio.run(server.call_tool("play_message", {"project": "lake-mariner", "message": "nope"}))
    assert "Record new mail with record_message first" in str(exc.value)
    assert str(exc.value) != "Error executing tool play_message"  # the generic text, with nothing to act on


def test_a_run_with_no_plan_has_nothing_to_report_and_says_so(local):
    tools.record_message(
        "Approved, please proceed", "Approved.", "2026-11-02T12:00:00Z", project="lake-mariner", kind="acknowledgment", source="note"
    )
    msg = next(m_["message"] for m_ in tools.status("lake-mariner")["messages_not_played"] if m_["title"] == "Approved, please proceed")
    out = tools.play_message("lake-mariner", msg)
    assert out["actions"] == [] and "changes nothing" in out["note"]
    assert tools.submit_report(out["run"], Report(summary="nothing"))["report_matches_ledger"] is None


def test_home_says_what_needs_you_what_ran_and_what_would_have_been_sent(page):
    client, _ = page
    tools.play_message("lake-mariner", "demo-monday")
    home = client.get("/api/home").json()
    assert [a["ref"] for a in home["asks"]] == ["a2"] and home["asks"][0]["text"]
    assert home["runs"][0]["counts"] == {"allow": 1, "ask": 1, "deny": 1} and home["runs"][0]["report_ok"] is True
    assert [p["project"] for p in home["projects"]] == ["lake-mariner"]
    ledger = client.get("/api/sites/lake-mariner/ledger").json()["entries"]
    sent = [e for e in ledger if e["type"] == "executed"]
    assert sent and all(e["dry_run"] for e in sent) and any(e["text"] for e in sent)
    assert any(a["outcome"].startswith("would have run") for a in tools._run_result(_org("lake-mariner"), _run_id())["actions"] if a["state"] == "executed")


def test_one_browser_sees_every_project_here_and_each_runs_in_its_own_org(page):
    client, _ = page
    _created(client, "")
    home = client.get("/api/home").json()
    assert {p["project"] for p in home["projects"]} == {"lake-mariner", "kitchen-remodel"}
    assert client.get("/api/sites/kitchen-remodel/me").json()["person"] == "me"
    assert client.get("/api/sites/lake-mariner/me").json()["person"] == "dana"  # the demo's lead
    assert client.get("/api/sites/nowhere/chain").status_code == 404
    drafts_home = client.get("/api/home").json()["drafts"]
    assert drafts_home == []  # the confirmed project draft is no longer waiting


def test_the_app_on_this_computer_answers_only_to_this_computers_names(page):
    client, base = page
    from groundwork.api.server import create

    elsewhere = TestClient(create(local=True), base_url="http://evil.example")
    assert elsewhere.get(f"{base}/").status_code == 421
    assert client.get("/api/home").status_code == 200
    assert TestClient(create(local=True), base_url="http://127.0.0.1:8765").get("/api/home").status_code == 401


def test_drafts_show_in_the_app_as_lines_to_confirm(page):
    client, _ = page
    tools.setup("Jude Test", "jude@example.test")
    tools.start_project(_project_draft())
    d = client.get("/api/home").json()["drafts"][0]
    assert d["kind"] == "project" and any("Final inspection" in x["text"] or "target" in x["text"] for x in d["lines"])
    assert client.post(f"/api/drafts/{d['id']}", json={"verdict": "confirm"}).status_code == 403  # cookie without Origin
    assert decide(client, d["id"], "reject")["message"].startswith("Rejected")
    assert client.post("/api/drafts/../secrets", json={"verdict": "confirm"}, headers=ORIGIN).status_code == 404


def _run_id():
    with owner_session() as s:
        return s.execute(select(m.Run.id)).scalars().first()


def test_pending_changes_show_as_a_forecast_beside_the_confirmed_one(page):
    client, base = page
    _created(client, base)
    rec = tools.record_message(
        "Cabinets late", "Two to three weeks late.", "2026-11-05T09:00:00Z", "bob@bayside.test", ["jude@example.test"],
        kind="schedule_change", date_changes=[tools.DateChange(item="cabinets", low_days=30, high_days=45, why="a month or more late")],
    )
    st = tools.status("kitchen-remodel")
    assert st["if_pending_confirmed"]["drafts"] == 1
    assert st["if_pending_confirmed"]["forecast"] > st["finish"]["forecast"]
    decide(client, rec['to_confirm']['draft'])
    after = tools.status("kitchen-remodel")
    assert after["if_pending_confirmed"] is None


# --- batch 2: progress, the clock, links, people and portals ---------------------------------------
def test_progress_from_a_message_marks_items_done_once_confirmed_and_gets_a_plan(page):
    client, base = page
    _created(client, base)
    before = tools.status("kitchen-remodel")
    rec = tools.record_message(
        "Permit issued", "Your building permit was issued today.", "2026-11-20T10:00:00-08:00",
        project="kitchen-remodel", source="portal", kind="acknowledgment",
        progress=[tools.Progress(item="permit", status="done", date=date(2026, 11, 20), why="permit was issued today")],
    )
    assert rec["kind"] == "progress"  # a completion is progress, not an acknowledgment
    assert any(i["item"] == "permit" for i in tools.status("kitchen-remodel")["waiting_on"])  # not done until confirmed
    decide(client, rec['to_confirm']['draft'])
    st = tools.status("kitchen-remodel")
    assert all(i["item"] != "permit" for i in st["waiting_on"])
    assert st["as_of"] == "2026-11-20" and before["as_of"] == "2026-11-02"
    plan = tools.play_message("kitchen-remodel", rec["message"])
    assert plan["needs_plan"] is True and "close-out" in plan["next"]
    with owner_session() as s:
        row = s.execute(select(m.Event).where(m.Event.key == rec["message"])).scalar_one()
        assert row.provenance == "public" and row.source == "portal"


def test_the_clock_finds_overdue_work_and_records_a_message_to_plan_chases_on(page):
    client, base = page
    _created(client, base)
    quiet = tools.check_overdue("kitchen-remodel", date(2026, 11, 3))
    assert quiet["overdue"] == []
    late = tools.check_overdue("kitchen-remodel", date(2027, 1, 10))
    assert late["project_date"] == "2027-01-10"
    assert {o["item"] for o in late["overdue"]} == {"permit", "cabinets"}
    plan = tools.play_message("kitchen-remodel", late["message"])
    assert plan["needs_plan"] is True and "past their planned date" in str(plan["message"])
    # The clock never runs backwards.
    assert tools.check_overdue("kitchen-remodel", date(2026, 12, 1))["project_date"] == "2027-01-10"


def test_inferred_links_are_flagged_and_change_only_when_confirmed(page):
    client, base = page
    d = _project_draft()
    d.items[-1].assumed_depends_on = ["cabinets"]  # final inspection waits on cabinets: inferred, not stated
    d.items[2].finish = date(2027, 1, 27)  # late cabinets put that link on the critical path
    _created(client, base, d)
    st = tools.status("kitchen-remodel")
    assert st["assumed_links"] == [
        {"before": "Cabinets delivered", "after": "Final inspection passed", "keys": ["cabinets", "final"], "on_critical_path": True}
    ]
    out = tools.change_links("kitchen-remodel", "The final doesn't need the cabinets", remove=[tools.Link(before="cabinets", after="final")])
    assert tools.status("kitchen-remodel")["assumed_links"]  # still there until confirmed
    decide(client, out['draft'])
    assert tools.status("kitchen-remodel")["assumed_links"] == []
    with pytest.raises(tools.ToolError):
        tools.change_links("kitchen-remodel", "again", remove=[tools.Link(before="cabinets", after="final")])


def test_people_on_your_side_route_their_mail_to_the_project(page):
    client, base = page
    _created(client, base)
    stray = tools.record_message("Tile choice", "Let's pick the green.", "2026-11-06T10:00:00Z", "sam@home.test", ["jude@example.test"])
    assert stray["recorded"] is False
    out = tools.add_people("kitchen-remodel", "you", [tools.PersonIn(name="Sam", email="sam@home.test")], "my partner")
    decide(client, out['draft'])
    routed = tools.record_message("Tile choice", "Let's pick the green.", "2026-11-06T10:00:00Z", "sam@home.test", ["jude@example.test"])
    assert routed["project"] == "kitchen-remodel"
    with org_session(_org("kitchen-remodel")) as s:
        sam = s.execute(select(m.Person).where(m.Person.email == "sam@home.test")).scalar_one()
        assert sam.approver is False
