"""The eval harness runs end to end on the simulated planner, which must score zero hard violations."""

from evals.run import build_dataset, make_task, summarize


def test_simulated_planner_passes_the_harness():
    report = build_dataset().evaluate_sync(make_task(live=False, model=None), progress=False)
    s = summarize(report)
    for arm in ("informed", "blind"):
        m = s["arms"][arm]
        assert m["hard_violations"]["mean"] == 0
        assert m["report_matches_ledger"]["mean"] == 1
        assert m["no_fabrication_when_withheld"]["mean"] == 1
        assert m["resisted_injection"]["mean"] == 1
        assert m["counterparties_valid"]["mean"] == 1
    assert s["usd"] == 0
