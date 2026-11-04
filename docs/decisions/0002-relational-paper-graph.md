# 0002. The paper graph is relational; graph algorithms live in code

**Status:** accepted.

**Context.** The "paper graph" is items (permits, studies, deliveries, tests), the parties who own and perform them, and dependencies between items. A site has tens to hundreds of items. The system's hardest requirements are auditability and multi-org isolation, not graph traversal at scale.

**Options.** (a) A graph database. (b) Postgres tables with the graph built in memory per request. (c) Postgres with recursive SQL for paths.

**Decision.** (b). Tables in `backend/groundwork/db/models.py`; the critical path, float and gating item are computed by `groundwork.core.cpm.schedule` over an in-memory networkx graph built from the rows. Building the graph for one site takes milliseconds. Every org-scoped table carries `org_id` under row-level security; `org` is the customer boundary and is never called a tenant, because in this industry a tenant is a lessee, which is a party role.

**Consequences.** Relational integrity, foreign keys and row-level security come for free, and the ledger (slice 2) can live in the same transaction as the decisions it records. A portfolio-wide query ("every item gated by the same transmission owner across all sites") is a SQL join, not a graph query. If a single site ever reached tens of thousands of items (a transmission line with per-parcel easements), the engine would need incremental recomputation; that is a later concern.
