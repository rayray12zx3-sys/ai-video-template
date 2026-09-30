# Legacy Import Adoption Contract v0.1

## Purpose

Define the safe I6c boundary for adopting a reviewed legacy project I6b dry-run result into canonical Template v2 state.

This is an **external-import adoption** contract. It is not generic schema migration and must not be implemented by relaxing `src/aivideo/migration.py`.

## Architecture decision

Current State Engine primitives are not sufficient by themselves:

- `begin_transaction()` can commit a full next document, but ordinary writes run dependency-transition validation and do not create an import checkpoint/backup.
- `migrate()` creates a backup, but is reserved for explicit adjacent schema-version migration and therefore must not be reused for legacy import.
- I6c therefore requires a dedicated State Engine import-adoption path with explicit validation, checkpoint/evidence binding, and recovery semantics.

Because this changes State Engine transaction semantics, implementation requires the project-approved local high-risk workflow.

## Required API boundary

Implementation may choose exact names, but the behavior must be equivalent to:

- a pure/read-only preview/plan step for import adoption
- a dedicated State Engine commit method for `IMPORT_ADOPTION`

The public adoption path must not call generic schema migration.

## Preconditions

Before adoption:

1. Current canonical state is internally consistent and writable.
2. No pending transaction journal exists after normal recovery.
3. Request revision/hash matches the current snapshot.
4. Candidate validates against the current project schema.
5. Candidate `project_id` matches the current canonical project identity.
6. Import report:
   - has expected source format
   - targets the current schema version
   - contains a valid source fingerprint
   - contains no blocking unresolved item
7. Candidate/report identity is deterministic and can be hashed.
8. A duplicate import identity has not already been committed.

Unknown/newer schema states remain fail-closed.

## Candidate normalization

The imported candidate is source material, not an already-committed canonical revision.

The adoption plan must:

- preserve canonical `project_id`
- set the adopted document's `state_revision` to exactly current revision + 1
- otherwise preserve the reviewed candidate semantics
- validate the normalized adopted document before any canonical write

The source candidate revision remains auditable through the import report/source accounting; it does not control canonical revision numbering.

## Import identity

A committed import identity must bind at least:

- source fixture fingerprint
- candidate SHA-256 after repository-safe I6b normalization, before canonical revision rebinding
- import report SHA-256
- target project ID
- expected pre-adoption state revision/hash

A second adoption of the same import identity must fail closed or return an explicit already-adopted result. It must never create a second silent canonical adoption.

## Checkpoint / evidence files

Before canonical replacement, create deterministic transaction-bound artifacts such as:

- `.import-backups/<transaction-hash>.project.yaml`
- `.import-evidence/<transaction-hash>.report.json`

Exact naming may vary, but:

- names must be deterministic from the transaction/import identity
- existing same-name content must match exactly or fail closed
- checkpoint must contain the exact pre-adoption canonical project bytes
- evidence file must contain the reviewed import report
- event metadata must bind paths + SHA-256 values
- source/candidate/report fingerprints must be stored in event metadata

These artifacts are runtime audit evidence; they are not a substitute for the append-only event history.

## State Engine single-writer rule

Only the State Engine may mutate:

- `project.yaml`
- `events.jsonl`
- pending transaction journal

No importer/helper may directly replace canonical state.

The adoption commit must reuse the existing recoverable journal + atomic project replace + append-only event machinery.

## Event semantics

Use a distinct event type such as:

`IMPORT_ADOPTION`

Do not label the event `MIGRATION`.

Transition metadata must include enough information to reconstruct:

- import identity
- source fingerprint
- candidate digest
- report digest
- checkpoint path/digest
- report evidence path/digest
- adoption mode/version

## Dependency-transition semantics

A whole external-import adoption is not an ordinary incremental edit.

Do not force callers to fabricate ordinary dependency invalidation declarations for a full reviewed import.

The dedicated adoption path may bypass ordinary dependency-transition invalidation only when all import-adoption preconditions have passed and the event is explicitly `IMPORT_ADOPTION`.

Ordinary `begin_transaction()` behavior remains unchanged.

## Dry-run / preview

Dry-run must:

- inspect current canonical state
- validate candidate/report and duplicate-import status
- produce the normalized proposed next document and audit metadata
- perform no canonical write
- create no backup/evidence file
- create no pending journal
- append no event

Repeated dry-runs over the same inputs must be deterministic apart from explicitly excluded volatile presentation fields; preferably return fully deterministic plan data.

## Failure and recovery

Required outcomes:

### Failure before journal preparation
Canonical state/history remain unchanged. Deterministic checkpoint/evidence files may exist only if they are complete and hash-bound; retry must verify and reuse or fail closed.

### Failure after journal preparation
Use existing State Engine recovery semantics. Recovery must resolve to the same adopted document/event or safely abort according to the existing journal state machine.

### Failure after canonical commit
Checkpoint and import evidence remain durable and bound in the event.

Do not implement rollback by copying a backup over `project.yaml` outside the State Engine. Any later rollback/reversal must be a new audited canonical transaction.

## Duplicate handling

At minimum test:

- same transaction ID -> existing duplicate transaction protection
- different transaction ID + same committed import identity -> explicit duplicate-import rejection/already-adopted result
- checkpoint/report filename collision with different bytes -> fail closed

## Blocking unresolved items

Any report item with `blocking: true` prevents adoption.

Non-blocking unresolved/evidence-only items may be adopted because their preservation is part of I6b's audited report.

## Required tests

I6c implementation must cover:

- preview/dry-run causes no canonical mutation or evidence-file creation
- successful adoption writes through State Engine only
- canonical revision increments exactly once
- project identity cannot change
- stale expected revision/hash rejected
- source/report/candidate fingerprints bound in event metadata
- checkpoint created before canonical adoption and matches pre-state bytes
- report evidence preserved and hash-bound
- blocking unresolved item rejects adoption
- duplicate import identity rejects or returns explicit already-adopted result
- duplicate transaction ID remains rejected
- checkpoint/evidence collision with different bytes fails closed
- crash/interruption around journal/state/event remains recoverable
- generic `migrate()` behavior remains unchanged
- ordinary dependency-transition checks remain unchanged
- Windows Python 3.11 / 3.14 CI passes

## Scope exclusions

I6c does not include:

- provider execution
- Provider integration changes
- real private source media
- I6d replay fixtures/comparison
- schema-version migration redesign
- automatic rollback that rewrites event history
- paid actions

## Completion evidence

Completion requires:

- bounded PR
- independent diff review
- deterministic test evidence
- Windows Python 3.11 + 3.14 CI green
- post-merge `main` CI green
- Acceptance criteria are checked only after the integrated tree passes the required verification.
