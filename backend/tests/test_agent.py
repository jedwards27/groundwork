"""The Claude-backed planner, classifier and reporter, against a fake client (no network)."""

from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from groundwork.agent.base import PlanContext, PlannerError, PlannerRefused
from groundwork.agent.claude import ClaudeClassifier, ClaudePlanner, ClaudeReporter, ContentVerdict
from groundwork.agent.prompt import build_prompt
from groundwork.agent.simulated import load_plans
from groundwork.agent.wire import WirePlan, from_plan
from groundwork.config import REPO_ROOT
from groundwork.ingest import load_site
from groundwork.schemas import ContentClass, Report
from groundwork.schemas.plan import Arm
from groundwork.service import planctx
from groundwork.service.state import SiteState

PLANS = load_plans(REPO_ROOT / "fixtures" / "lake-mariner" / "simulated_plans.yaml")


def usage(**kw):
    return SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        cache_read_input_tokens=kw.get("read", 0),
        cache_creation_input_tokens=kw.get("write", 0),
    )


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(response=None, error=None):
    msgs = FakeMessages(response, error)
    return SimpleNamespace(messages=msgs, beta=SimpleNamespace(messages=msgs)), msgs


def ctx(arm=Arm.informed) -> PlanContext:
    st = SiteState.from_bundle(load_site(REPO_ROOT / "fixtures" / "lake-mariner"))
    st.event_status["event-a"] = "applied"
    return planctx.build(st, st.initial_mandate(), st.event("event-a"), arm, [])


def test_planner_returns_validated_plan_and_usage():
    resp = SimpleNamespace(
        stop_reason="end_turn",
        parsed_output=from_plan(PLANS["event-a"]),
        usage=usage(read=4000),
        model="claude-opus-5-5",
        stop_details=None,
    )
    client, msgs = fake_client(resp)
    r = ClaudePlanner(client, "claude-opus-5-5").plan(ctx())
    assert r.plan.actions[0].ref == "a1" and r.usage["cache_read_input_tokens"] == 4000
    call = msgs.calls[0]
    assert call["output_format"] is WirePlan and call["fallbacks"] == "default"
    assert r.plan == PLANS["event-a"]  # the wire form maps back to the same domain plan
    assert call["betas"] == ["server-side-fallback-2026-07-01"] and call["output_config"] == {
        "effort": "high"
    }
    assert r.prompt_hash.startswith("sha256:")


def test_planner_refusal_and_empty_output():
    refused = SimpleNamespace(
        stop_reason="refusal",
        parsed_output=None,
        usage=usage(),
        model="m",
        stop_details=SimpleNamespace(category="cyber", explanation="x"),
    )
    with pytest.raises(PlannerRefused, match="cyber"):
        ClaudePlanner(fake_client(refused)[0], "m").plan(ctx())
    empty = SimpleNamespace(
        stop_reason="max_tokens", parsed_output=None, usage=usage(), model="m", stop_details=None
    )
    with pytest.raises(PlannerError, match="max_tokens"):
        ClaudePlanner(fake_client(empty)[0], "m").plan(ctx())


def test_planner_api_error_becomes_planner_error():
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    with pytest.raises(PlannerError):
        ClaudePlanner(fake_client(error=err)[0], "m").plan(ctx())


def test_classifier_fails_closed():
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    cls, why, _ = ClaudeClassifier(fake_client(error=err)[0], "h").classify("hello")
    assert cls == ContentClass.unknown and "error" in why
    refused = SimpleNamespace(stop_reason="refusal", parsed_output=None, usage=usage())
    assert ClaudeClassifier(fake_client(refused)[0], "h").classify("x")[0] == ContentClass.unknown
    good = SimpleNamespace(
        stop_reason="end_turn",
        usage=usage(),
        parsed_output=ContentVerdict(content_class=ContentClass.commits_money, reason="fee"),
    )
    assert ClaudeClassifier(fake_client(good)[0], "h").classify("pay")[0] == ContentClass.commits_money


def test_reporter_receives_plan_and_entry_types():
    rep = Report(did=["a1"], summary="s")
    resp = SimpleNamespace(stop_reason="end_turn", parsed_output=rep, usage=usage(), stop_details=None)
    client, msgs = fake_client(resp)
    out, _ = ClaudeReporter(client, "h").report(
        PLANS["event-a"], {"a1": ["proposed", "decided:auto", "executed"]}
    )
    assert out == rep and "ledger_entry_types" in msgs.calls[0]["messages"][0]["content"]


def test_prompt_shape_caching_and_data_boundary():
    system, messages = build_prompt(ctx(Arm.informed))
    content = messages[0]["content"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert [("cache_control" in b) for b in content] == [True, True, False, False]
    text = system[0]["text"] + "".join(b["text"] for b in content)
    assert "@" not in text and ".example" not in text  # no email addresses anywhere in the prompt
    assert "[address withheld]" in content[3]["text"]
    assert "mandate (grant of authority)" in content[2]["text"]
    _, blind = build_prompt(ctx(Arm.blind))
    assert "not shown your principal's mandate" in blind[0]["content"][2]["text"]
    assert "May act alone" not in "".join(b["text"] for b in blind[0]["content"])
    # The cached prefix is identical across arms, so the blind arm reads the informed arm's cache.
    assert content[0]["text"] == blind[0]["content"][0]["text"]


def test_prompt_prefix_is_byte_stable():
    a = build_prompt(ctx())[1][0]["content"][0]["text"]
    b = build_prompt(ctx())[1][0]["content"][0]["text"]
    assert a == b and len(a) > 2000  # well above the 512-token cache minimum


def test_simulated_plans_exist_for_both_events_and_the_demo():
    assert set(PLANS) == {"event-a", "event-b", "demo-monday"}
    assert Path(REPO_ROOT / "fixtures" / "lake-mariner" / "simulated_plans.yaml").exists()
