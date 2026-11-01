# 0004. Postgres only; runs are rows; no queue library in v1

**Status:** accepted. Settles the queue part of ARCHITECTURE §3.

**Context.** The original sketch had Postgres plus Redis for a job queue. v1 has one kind of background work (playing an event: plan, decide, record, execute in dry run, recompute) and one process.

**Options.** (a) Redis + a Python queue (arq is in maintenance-only mode; SAQ and taskiq are alternatives). (b) A Postgres-backed queue library (Procrastinate is seeking maintainers). (c) A `run` table and an in-process background task. (d) Temporal from the start.

**Decision.** (c). `POST /sites/{site}/events` commits a `run` row and returns its id; the pipeline runs as a background task and appends progress steps; `GET /runs/{id}/stream` is a server-sent-events stream that resumes from `Last-Event-ID`; a startup sweep marks runs left behind by a restart as failed (`run_aborted`). Docker compose runs Postgres only.

**Consequences.** One fewer service to run, secure and explain. A deploy can interrupt a run; the sweep makes that truthful rather than silent. When a second process or durable timers are needed (approvals that wait days, escalation on an SLA), Temporal (self-hosted, MIT) replaces the background task and consumes the same `run` rows; its history is orchestration state, never the ledger. A `SELECT … FOR UPDATE SKIP LOCKED` worker over the same table is the intermediate step if needed sooner.
