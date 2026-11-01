# 0005. The gateway is Python rules over a JSON mandate; Cedar is deferred

**Status:** accepted. Settles the policy-engine question from the plan reviews.

**Context.** The gateway must be deterministic, fully table-tested and readable by a non-engineer. Cedar (AWS's open-source, formally verified authorization language) was the leading candidate for evaluating the mandate.

**Options.** (a) Cedar via the community `cedarpy` binding. (b) OPA or Cerbos. (c) A pure Python function over a JSON mandate.

**Decision.** (c), in `backend/groundwork/policy/`. Cedar decides allow or deny, but the mandate needs three outcomes (auto, ask, refuse) plus routing to named approvers, so half of it would live outside Cedar anyway. Cedar also ignores a policy whose condition errors, which can quietly turn a `forbid` (the never-list) into the default, and the Python binding is community-maintained. The Python gateway checks the never-list first, then every rule that forces a person (missing parameters, unknown recipient, no direct channel, classified outbound text, record-bearing kinds and recipients, effects on items the principal does not control, spend without a structured amount, external attendees), then the auto rules with per-action and per-day spend limits. Its inputs are resolved from data (`service/context.py`), never from labels the planner wrote. 172 table-driven tests cover every executor against every recipient role class under every preset, plus explicit rows for each rule (`tests/test_gateway.py`).

**Consequences.** One fewer dependency, and the decision order reads as policy. Presets are written over role classes (`regulator`, `counterparty_binding`, `counterparty_routine`, `internal`) so a solar or transmission site uses them unchanged. Revisit Cedar, keeping the never-list in code before it, when the mandate becomes a standard shared across parties and a formally verified evaluator is worth its constraints. The plan listed "IE communications" as record-bearing; that applies to a lender's independent engineer (modeled with the `lender` role). The principal's own engineer is a contractor, so engaging it against a quote within limits runs alone.
