# Ledger format and verification

Every proposal, decision, approval, execution, report and mandate change is an entry in an append-only, per-org hash chain (`ledger_entry`). This page is enough to write an independent verifier.

**Entry hash.** SHA-256, lowercase hex, over the RFC 8785 canonical JSON of exactly these fields:

```
org_id, seq, prev_hash, entry_type, run_id, action_id, arm, recorded_at, payload
```

`org_id`, `run_id` and `action_id` are lowercase UUID strings or null. `seq` starts at 1 and is contiguous. `prev_hash` of the first entry is 64 zeros. `recorded_at` is the exact RFC 3339 string the writer hashed (`YYYY-MM-DDTHH:MM:SS.ffffffZ`). Payloads use integers for money (cents) and days; floats are rejected. For bodies like these, RFC 8785 is the same as JSON with sorted keys, no whitespace and UTF-8 output.

**Test vector.** This body must hash to `6bc8d240cfd8e2cf7a929221d00f98f3c8a4d9161f96483bd20112792de3f4d2`:

```json
{"org_id": "00000000-0000-0000-0000-000000000001", "seq": 1, "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000", "entry_type": "decided", "run_id": null, "action_id": null, "arm": "informed", "recorded_at": "2026-11-02T14:12:00.000000Z", "payload": {"decision": "auto", "amount_cents": 1850000, "reason": "Within the $50,000 limit", "title": "Café test ✓"}}
```

**Verification.** Walk entries by `seq`: check contiguity from 1, that each `prev_hash` equals the previous entry's `hash`, and that each recomputed hash matches. `GET /sites/{site}/ledger/verify` and `verify_chain()` do this.

**What protects it.** Appends for one org take a transaction-scoped advisory lock, so concurrent writers cannot fork the chain, and `(org_id, seq)` is unique. The app role has only SELECT and INSERT. A trigger rejects UPDATE, DELETE and TRUNCATE even for the table owner, who must disable it deliberately. Editing, deleting or reordering an entry is then detected by verification (`make demo` shows it). Rewriting the whole chain from genesis is not detectable from the chain alone, which is why the attestation carries the head hash for comparison with a copy published earlier.

**Entry types.** `mandate_issued`, `plan_received`, `planner_fallback`, `proposed`, `decided`, `intent_delta`, `execution_requested`, `executed`, `execution_failed`, `approval`, `report`, `report_mismatch`, `message_received`. Blind-arm entries carry `arm: "blind"` and are excluded from approvals, spend headroom and the forecast.
