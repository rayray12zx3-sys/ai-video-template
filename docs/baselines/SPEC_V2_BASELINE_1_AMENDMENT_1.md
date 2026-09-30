# SPEC_V2_BASELINE_1 — Amendment 1

Date: 2026-09-22
Reason: bounded pre-implementation red-team

This amendment refines execution safety without changing the baseline's provider-neutral architecture.

## Added mandatory implementation contracts

1. `docs/interfaces/state-transaction-concurrency-v0.1.md`
2. `docs/interfaces/schema-migration-v0.1.md`
3. `docs/architecture/generation-ticket-contract-v0.2.md`
4. `docs/checkpoints/pre-implementation-red-team-v0.1.md`

## New mandatory rules

- canonical project state is mutated only through a State Engine
- canonical writes use compare-and-swap revision/hash checks
- current state + event history updates use a recoverable transaction journal
- ambiguous paid submissions enter UNKNOWN_SUBMISSION and are never automatically retried
- PixVerse automation passes explicit workspace ID on account-sensitive/paid commands
- PixVerse Canvas concurrency uses provider edit_version/base_edit_version in addition to local state_revision
- older schemas migrate explicitly; unknown newer schemas are read/write blocked according to migration policy
- Phase I0-I4 do not require administrator privileges
- MVP excludes paid/provider writers and optional integrations until core safety primitives are tested

## Baseline status

`SPEC_V2_BASELINE_1 + Amendment 1`

Status: READY FOR PHASE I0 IMPLEMENTATION.
