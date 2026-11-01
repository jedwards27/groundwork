# 0003. The forecast is deterministic code; recovered days are computed, not estimated

**Status:** accepted. Settles ARCHITECTURE §2.3.

**Context.** The countdown, the gating item and the "days recovered" bars are the numbers a project manager will check first. If a model writes them, they change between runs and can be moved by text in a document.

**Options.** (a) Ask the model for dates. (b) Deterministic critical path plus reference classes, with the model writing explanations only. (c) A learned forecaster.

**Decision.** (b). `groundwork.core.cpm.schedule` runs a forward pass from the as-of date (incomplete work cannot happen in the past; not-started items respect their planned start and every link) and a backward pass from the milestone's target date, on the site's working calendar. Events add delays as ranges; the forecast reports low, midpoint and high. A reference class adjusts an estimate only with at least five single observations; ranges and secondary figures are displayed with their provenance and never applied (the Lake Mariner fixture has none that qualify, and the gating item shows "no comparable items yet"). In slice 2 a mitigation proposes an *effect* on a named item (shorter duration, shorter lag, overlap); the same engine computes the days, and effects that depend on a counterparty's response are credited only as "if they agree", not on send. The engine also reports holidays that fall inside critical-path waits, which is how the fixture surfaces Thanksgiving inside the transmission owner's witness-test notice.

**Consequences.** Forecasts are reproducible and testable (`tests/test_fixture.py` asserts the computed gate and both events' ranges). The forecast is only as good as the schedule's durations and lags, which is why every duration in the fixture carries provenance and the practitioner questions exist. A learned forecaster is a later rung, gated on real history.
