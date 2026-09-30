# Architecture Decision Records

## ADR-001 — Single canonical current state
Accepted.

Current state belongs to one machine-readable project state. Human-readable status views are generated. Historical transitions are append-only events.

Reason: legacy state was split across TASK_STATE, STATUS, README and multiple manifests and became stale.

## ADR-002 — Provider-neutral routing
Accepted.

Shots define intent/requirements/constraints. Provider, mode and model are execution-time choices based on capability evidence.

Reason: provider capabilities change too quickly to encode model names into project semantics.

## ADR-003 — Reference-first error ownership
Accepted.

Identity/costume/environment/composition failures return to reference/previs rather than repeated video prompting.

Reason: Revision replay demonstrated that prompt retries cannot reliably repair a wrong visual premise.

## ADR-004 — Human gate for paid generation
Accepted.

Paid generation requires explicit human approval by default. Executors may prepare tickets, preflight accounts and estimate spend without submitting.

Reason: automated providers can consume shared credits and concurrency.

## ADR-005 — Production and revision are distinct lanes
Accepted.

A local revision does not rerun an entire new-production gate chain unless impact analysis proves the upstream state is affected.

Reason: Revision replay was forced through structures designed for new production.

## ADR-006 — Evidence is not production method
Accepted.

Real UI, AI generation, Premiere edits and static holds describe how a shot is produced. Evidence describes why an asset/shot is trusted or approved.

Reason: legacy source-video and editorial examples revealed these concepts were conflated.

## ADR-007 — Canonical state has a single transactional writer
Accepted.

Agents/scripts do not edit project.yaml/events.jsonl directly. State Engine uses optimistic revision/hash checks, a writer lock and recoverable transaction journal.

Reason: state_revision alone cannot prevent simultaneous lost updates or half-written state/history after process crashes.

## ADR-008 — Ambiguous paid submissions are never auto-retried
Accepted.

A durable PREPARED/SUBMITTING record is written before provider invocation. If execution outcome is ambiguous and no provider job/receipt is captured, state becomes UNKNOWN_SUBMISSION and must be reconciled before further spend.

Reason: local idempotency keys do not imply provider-side create idempotency.

## ADR-009 — Provider workspace/concurrency state is explicit
Accepted.

PixVerse automation passes explicit workspace scope on relevant commands and treats Canvas edit_version as a provider concurrency token. It does not depend on mutable workspace-switch state or blindly bump Canvas versions.

Reason: shared-account and concurrent Canvas edits can otherwise route spend or overwrite changes incorrectly.

## ADR-010 — Schema evolution is explicit and forward-safe
Accepted.

Older schemas require versioned migrations before write. Unknown newer schemas refuse write. Migration is validated and audited.

Reason: a reusable template must survive future schema changes without silent information loss.
