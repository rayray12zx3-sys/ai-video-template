# SPEC_V2_BASELINE_1

Date: 2026-09-22
Status: FROZEN_FOR_IMPLEMENTATION

This baseline marks the end of the architecture-design phase for AI Video Template v2.

## Scope frozen by this baseline

The following design layers are accepted as the implementation baseline:

- Legacy Project Audit v1
- Conversation Audit v1
- Canonical Data Model v0.2
- Shot Router v0.1
- Validator & Gate System v0.1
- Generation Ticket Contract v0.1
- QC Contract v0.1
- Provider Boundaries v0.1
- Criticality Vocabulary v0.1
- Dependency & Impact Semantics v0.1
- Ticket Retention Policy v0.1
- Provider Capability Schema v0.1
- Asset Locator Contract v0.1
- Legacy Full Replay v0.1
- ADR decisions recorded in docs/decisions

## Replay status

Representative legacy cases:
- Exact-text interaction
- Scale, camera, and motion complexity
- Revision reference recovery
- Recorded interface source media
- Editorial cut without new media

All passed without shot-ID-specific logic.

The five replay interface gaps are now covered by dedicated interface specifications:
1. criticality/readiness vocabulary
2. typed dependency impact propagation
3. ticket/receipt retention
4. normalized provider capability snapshots
5. storage-independent asset locators

## Architecture invariants

1. One canonical current state.
2. One append-only event history.
3. Derived views are never authoritative.
4. Shot semantics are provider/model neutral.
5. Provider capability is refreshed at execution time.
6. Error ownership is explicit.
7. Reference errors return to reference/previs.
8. Technical and creative QC are separate.
9. Revision is a first-class lane.
10. Non-complete projects expose a next_action.
11. Paid generation is guarded by human approval by default.
12. Executed paid work is durably recorded.
13. Asset identity is storage-independent.
14. Dependency invalidation is typed, not global.
15. No project-specific shot names/paths belong in validator source code.

## What is NOT frozen

Implementation details may evolve without breaking this baseline:

- programming language choice
- exact module/package layout
- CLI UX
- generated report formatting
- GitHub Actions structure
- adapter internals
- local config file naming
- caching strategy
- optional UI/dashboard
- open-media integration details

Any implementation choice that changes the architecture invariants requires a new ADR and a post-baseline design revision.

## Implementation phases

### Phase I0 — Repository foundation
- runtime folder layout
- schema skeleton
- sample project
- local config boundaries
- test fixtures

### Phase I1 — Canonical state
- project schema
- event record schema
- asset/shot/dependency models
- state revision support

### Phase I2 — Validation and gates
- schema validator
- integrity/readiness/policy validators
- gate evaluator
- action guards

### Phase I3 — Router and tickets
- production plan
- provider-neutral route selection
- normalized capability snapshots
- generation ticket compiler
- idempotency and receipts

### Phase I4 — QC
- Q0-Q3 contracts
- QC profiles
- failure ownership
- stop-loss logic

### Phase I5 — Provider adapters
Priority:
1. PixVerse capability/account read-only adapter
2. PixVerse ticket compilation / guarded execution
3. Flow manual-Web ticket compiler
4. Premiere/AE post-route adapters or instructions

### Phase I6 — Legacy migration
- legacy project migration tooling/fixture
- replay against migrated state
- compare reconstructed state to legacy audit

### Phase I7 — Hardening
- tests
- docs
- examples
- safe defaults
- GitHub Actions validation

## First implementation rule

Before any paid PixVerse generation support is enabled, validate the PixVerse CLI read-only path:
- CLI availability
- OAuth login
- correct account/workspace
- account info
- slots
- capabilities
- JSON output shape

This must not spend credits.

## Change control

After this baseline:
- architecture changes require ADR
- provider changes usually require adapter/capability updates, not shot-schema edits
- project-specific exceptions are presumed design smells until proven otherwise
- newly discovered tools are pilot candidates, not automatic dependencies

## Baseline verdict

READY FOR CODEX IMPLEMENTATION.
