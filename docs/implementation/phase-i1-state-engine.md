# Phase I1 State Engine

The State Engine is the sole canonical writer. `project.yaml` remains UTF-8
JSON syntax, a YAML 1.2 subset. SHA-256 covers exact file bytes, including
formatting and newline. Callers supply a complete next document, the expected
revision/hash, and a unique transaction ID. The engine enforces one revision
increment and validates `next_action` as a nonempty string.

## Write protocol

1. Acquire the project-local OS byte-range lock. Windows uses
   `msvcrt.locking`; POSIX uses `flock`. The ignored lock file persists.
   An active OS lock refuses a second writer. After a process exit, the OS
   releases the lock; old metadata remains for diagnosis. Recovery runs under
   the newly acquired lock before any write.
2. Recover any journal, validate the project/event chain, reject duplicate
   transaction IDs, compare expected revision and exact-byte hash, and check
   explicit Git handoff evidence when `repo` is configured.
3. Validate the next project and event in memory. Write a same-directory temp
   journal, flush and `fsync` it, then `os.replace` the pending journal.
4. Write and `fsync` a same-directory temp project, then `os.replace`
   `project.yaml`.
5. Append one JSONL event with the same transaction ID, before/after revisions
   and hashes. Flush it with `fsync`.
6. Re-read state and history, verify matching revision/hash, then remove the
   journal. The journal remains if any earlier stage raises.

Journal content includes exact target project text and the full event. Recovery
never derives an event from current state. A partial final event line is
completed by appending the missing suffix only after the state and prior
history prove the journal's after-state path. Conflicts leave original bytes
untouched.

## Recovery matrix

| Observed state | Recovery result | Test |
| --- | --- | --- |
| No journal, consistent project/history | `NO_PENDING` | `test_no_pending_and_prepared_abort_and_duplicate_recovery` |
| Journal prepared, old project, event absent | `ABORTED_PREPARED`; old state stays | same test |
| New project, event absent | `EVENT_REPLAYED` | `test_state_applied_event_missing` |
| Old project, event present | `STATE_REPLAYED` | `test_event_applied_state_old` |
| New project, event present, stale journal | `ALREADY_COMMITTED` | `test_committed_with_stale_journal` |
| Repeated recovery | `NO_PENDING` | `test_state_applied_event_missing` |
| Unexpected project/history change | `RECOVERY_CONFLICT` | `test_external_state_or_history_change_conflicts` |
| Partial pending event append | `EVENT_REPLAYED` | `test_partial_pending_event_tail_recovers` |
| Malformed pending journal or duplicate event | `RECOVERY_CONFLICT` | `test_malformed_journal_conflicts`, `test_duplicate_event_and_broken_history_conflict` |
| Stale revision/hash | `STATE_CONFLICT` | `test_cas_revision_hash_and_duplicate` |
| Reused transaction ID | `DUPLICATE_TRANSACTION` | same test |
| Active lock / released OS lock with stale metadata | refuse / recover under new lock | `test_active_and_stale_lock` |

The selected protocol writes state before event. Event-present/old-state is
unreachable in normal execution, but recovery accepts it when the journal
proves the exact state/event pair.

## Migration and handoff

Current schema `2.0` is writable. Older versions require an explicitly
provided migration chain with a source validator and pure transform; no
historical transforms are registered in I1. I1 only permits changes to
`schema_version`; substantive field conversions need a separately reviewed
implementation and migration fixtures. A dry run returns changed fields,
warnings, and unresolved items. A migration commits as one `MIGRATION` event
with report metadata. The source bytes are backed up under ignored
`.migration-backups/` before canonical replacement. Unknown newer versions
refuse writes.

For Git-backed projects, construct `StateEngine(project_dir, repo=repo_root)`,
fetch `origin`, capture handoff evidence, and pass it on the
`TransactionRequest`. The engine compares remote identity fingerprint,
branch, local HEAD, tracked `origin/<branch>` commit, state revision, and hash.
Only one workstation may be the writer. A local OS lock does not serialize
other machines, and a stale tracking ref cannot detect an unfetched remote
advance. Handoff requires an operator checkpoint, push, fetch, and exact base
verification. There is no remote distributed lock in I1.

## Durability limits

The temp files and event file are `fsync`ed. POSIX directory entries are
also `fsync`ed where supported. Python's standard library does not expose
a portable Windows directory flush; after sudden power loss, an `os.replace`
or journal deletion may not be durable even when file contents were flushed.
Windows `os.replace` is a same-volume replacement attempt and can fail if
another process opens the target without delete sharing. Such failures leave
the pending journal for retry/recovery when its directory entry survived.
These are process-crash guarantees, not an unconditional power-loss guarantee.
The local lock does not defend against direct external edits or simultaneous
writers on separate machines.
