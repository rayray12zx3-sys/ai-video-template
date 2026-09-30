# State Transaction & Concurrency Contract v0.1

## Purpose

Prevent two agents/processes from silently overwriting canonical state and guarantee recoverable project-state transitions after crashes.

## Single-writer rule

Agents and helper scripts MUST NOT edit `project.yaml` or append `events.jsonl` directly.

All canonical state mutation goes through one State Engine API/CLI.

Reads may be concurrent. Writes are serialized.

## Optimistic concurrency

Every mutation request carries:

- expected_state_revision
- expected_project_hash
- transaction_id

The State Engine rejects the mutation if the current revision/hash differs.

Result:
`STATE_CONFLICT`

The caller must re-read current state and recompute the transition. It may not simply increment the revision number.

## Local writer lock

The State Engine uses a project-local exclusive write lock around commit/recovery operations.

Lock metadata may include:
- process/session identifier
- acquired_at
- transaction_id

Stale lock recovery must be explicit and must first inspect the pending transaction journal.

The lock is implementation coordination, not canonical project truth.

## Crash-consistent transaction protocol

A state transition updates both current state and event history. Because two files cannot be assumed to update atomically together, use a recoverable write-ahead transaction.

Proposed protocol:

1. Read and validate current revision/hash.
2. Compute new project state and event record in memory.
3. Write a durable pending transaction record containing:
   - transaction_id
   - before_revision/hash
   - after_revision/hash
   - event payload
   - transition metadata
4. Atomically replace `project.yaml` using temp-file + rename/replace.
5. Append the event with the same transaction_id to `events.jsonl`.
6. Verify both sides.
7. Mark/remove the pending transaction as committed.

## Startup recovery

Before any write, State Engine checks for pending transactions.

Possible recovery:
- neither state nor event applied → safely abort/retry transition
- state applied, event missing → append the recorded event
- event applied, state missing/old → apply recorded new state after verifying before/after hashes
- conflicting external modification → stop with RECOVERY_CONFLICT; do not guess

Recovery is deterministic from the pending transaction record.

## Event identity

Every event includes:
- transaction_id
- state_revision_before
- state_revision_after
- timestamp
- actor
- event_type

Duplicate transaction IDs in event history are invalid.

## Git interaction

Git is version history, not the runtime locking mechanism.

Concurrent feature branches may change schemas/code, but runtime project-state writes should not be hand-merged casually.

When a canonical project file changes outside State Engine, the expected project hash detects it before the next write.

## Invariants

- one writer at a time
- compare-and-swap before write
- no direct Agent edits of canonical state
- no silent last-writer-wins behavior
- every committed state revision has a matching event
- crashes are recoverable without inventing history
