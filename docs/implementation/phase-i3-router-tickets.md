# Phase I3 — Router, tickets, and execution contracts

I3 is offline and does not submit provider requests. `router.route_shot` returns a
provider-neutral, deterministic route report with reasons, error owner, previs
recommendation, and a proven normalized operation where available. It never
approves spend. A missing capability leaves a proposed AI route unresolved.

`tickets.compile_ticket` seals the exact intent as canonical UTF-8 JSON bytes and
uses their SHA-256 as the ticket ID. It binds the project revision/hash for audit,
shot and input subject fingerprints for scoped staleness, applicable dependency
edges, canonical and provider-ready input hashes, prompts, transformation policy,
provider/runtime/entitlement snapshot IDs, workspace, surface, quote, external
processing decision, approvals, model settings, expected output, and QC profile.
An optional explicit `strategy_id` is sealed with the ticket for I4 stop-loss;
it stays stable across per-attempt seed changes and does not authorize retries.
It also binds full snapshot content hashes so reusing an ID with changed
capabilities or entitlement is rejected at submission.
`ticket_staleness` tolerates unrelated canonical edits but reports changed bound
subjects or edges. Paid tickets require current technical and entitlement
snapshots; capability evidence is never inferred from an account balance.

`execution.ExecutionLedger` is a local SQLite supporting record, ignored by Git.
It uses an atomic unique index over project/shot/candidate to arbitrate surfaces
on one machine. `prepare` runs the existing I2 Action Guard with injected trusted
verifiers under the State Engine local writer lock, then persists a `PREPARED`
claim. A future adapter must persist a request fingerprint and local key while
moving to `SUBMITTING` before issuing a provider command. When the exact backend
and operation prove support, the provider idempotency key and trace ID must also
be persisted at this transition. The submission transition rechecks the original
action kind, canonical state, ticket, runtime evidence, and Action Guard. An ambiguous result
must move to `UNKNOWN_SUBMISSION`; only a trusted reconciliation callback can
resolve it. An unresolved or submitted intent cannot acquire another claim.
The local key is not treated as provider idempotency; exact operation/backend
support must be present in technical capability evidence. A provider key is unique
across claims within the same provider/workspace/backend scope.

Receipts bind a claim and sealed ticket, including actual provider upload IDs and
hashes for each source or provider-ready derivative. They are stored once, with
integrity hashes. A receipt is supporting evidence, never asset approval or a canonical
write. Provider output approval/materialization still passes through State Engine
and I2 validators. `manual_web_import` builds an `EXTERNAL_EXECUTION / WEB_MANUAL`
record with explicit `UNKNOWN` for missing provenance. The caller must pass that
record to `ExecutionLedger.import_manual_web` to persist a cross-surface claim.

The ledger is local, not a multi-machine coordination mechanism. Before I5 paid
adapters, add durable export/retention and crash recovery integration for the
execution ledger, a trusted provider preflight/reconciliation implementation,
and explicit provider submission handling. The checked-in I3 tests use only
test-only verifier callbacks and temporary projects.
