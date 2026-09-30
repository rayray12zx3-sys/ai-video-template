# Full Plan Optimization Review — 2026-09-23

Status: READY FOR IMPLEMENTATION AFTER AMENDMENT 2

## Architecture verdict

No redesign of the canonical model, Router, Gate system, QC model or State Engine is needed.

## Newly closed blind spots

1. ChatGPT Plugin presence is not proof of Codex Plugin availability.
2. Web + Plugin simultaneous use needs an execution claim/manual reconciliation path.
3. Shared account balance cannot attribute project spend.
4. Provider preprocessing can break source-hash assumptions.
5. Provider cloud/upload storage cannot be the only durable copy.
6. Approved/final cloud outputs need materialization + hash.
7. Plugin/private CLI updates can change behavior mid-project.
8. Technical capabilities, account entitlement and Canvas schema should be distinct evidence.
9. Prompt optimization/enhancement must be observable/policy-controlled.
10. Local file lock does not solve home/office cross-machine conflicts.
11. Provider idempotency/trace controls should be used when verified.
12. External-processing/rights policy must be checked before sensitive uploads.

## Optimized implementation order

### I0
Repository foundation, schema skeleton, State Engine skeleton, local environment profile, cross-machine handoff.

### I1
Transactions/CAS/recovery, migration, stale propagation, execution-claim primitive.

### I2
Validators/Gates/Action Guards, including external-processing and final-materialization requirements.

### I3
Router/Tickets with execution-surface abstraction, split capability snapshots, prompt-transform policy, provider-input derivative lineage, provider idempotency binding.

### I4
Q0-Q3 QC plus manual-Web candidate import/reconciliation.

### I5
PixVerse read-only integration:
1. discover Plugin wrapper
2. else raw CLI
3. else Web manual
4. record runtime/capability/auth/slots/Canvas schema as applicable

### I5b
One controlled low-cost paid pilot only after I0-I3 safety primitives pass.

### I6
Legacy project migration and replay.

### I7
Hardening/tests/docs; optional integrations later.

## Deferred

- simultaneous multi-machine writers
- automatic Flow UI
- ChatGPT PixVerse execution until an action connector is actually exposed
- open-media integration
- ComfyUI/local AI
- dashboards

## Go/no-go

Phase I0: GO.
Paid PixVerse automation: NO-GO until core guards + read-only integration + one controlled pilot.
