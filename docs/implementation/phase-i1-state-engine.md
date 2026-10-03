# Phase I1 State Engine

The State Engine is the sole canonical writer. `project.yaml` remains UTF-8
JSON syntax, a YAML 1.2 subset. SHA-256 covers exact file bytes, including
formatting and newline. Callers supply a complete next document, the expected
revision/hash, and a unique transaction ID. The engine enforces one revision
increment and validates `next_action` as a nonempty string.

## Revision-zero bootstrap

`StateEngine.bootstrap(initial_document, *, handoff_base=None)` is the public
path for creating a new canonical project. Supply a complete current-schema
document with `state_revision == 0`, valid project identity, modes, collections
and a nonempty `next_action`. Do not manually create/copy canonical files or
use an import/migration transaction to manufacture an initial snapshot. The
engine preserves the supplied document; it adds no approval, evidence or
provider metadata and performs no provider or network execution.

Revision 0 is the **genesis snapshot**. Its `events.jsonl` is zero bytes. There
is no `-1 -> 0` event, no invented pre-state hash and no transaction journal
for bootstrap. The first ordinary transaction creates the `0 -> 1` event,
binding the exact genesis project hash as its before-hash.

Under the existing project-local OS writer lock, bootstrap:

1. validates the candidate before creating canonical files;
2. refuses any pending journal (without recovery), nonempty history, malformed
   or conflicting canonical files, and canonical file symlinks/directories;
3. verifies explicit bootstrap handoff evidence when `repo` is configured;
4. atomically materializes empty `events.jsonl` if absent;
5. atomically materializes the validated revision-zero `project.yaml`;
6. re-reads and runs canonical consistency checks before returning a snapshot.

An absent project with absent or zero-byte history is uninitialized. A process
crash between steps 4 and 5 therefore leaves a safely retryable prepared state.
A crash after step 5 already leaves consistent genesis. Retry the same public
bootstrap call, including its original Git evidence when applicable.

If the project already exists, only an exact retry succeeds: current schema,
revision zero, present zero-byte history and exact project bytes equal to the
engine's deterministic serialization of the requested initial document. Key
order in the input dictionary does not matter; existing formatting/newline
differences do. Exact retry returns the existing snapshot without canonical
writes (lock metadata is still updated). All other initialized projects are
preserved and rejected, including an exact project with missing history, later
revisions, older/newer schemas, different candidates and pending transactions.

For a complete API example, see [Create a new project safely](../../README.md#create-a-new-project-safely).

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

For the empty canonical lifecycle, use `capture_bootstrap_base(repo_root,
project_dir)` after fetching `origin`, then pass that evidence as
`handoff_base` to `bootstrap`. Capture and verification require an attached
branch, actual Git worktree root, remote URL fingerprint, local HEAD equal to
the fetched `origin/<branch>`, and neither canonical file present in the
committed base. Evidence also binds the repository-relative project location.
The working project must be absent and history absent or zero bytes at capture;
verification permits a matching genesis snapshot only for exact retry. A
competing initialization, pending journal, changed identity/branch/HEAD or
different fetched remote base fails closed. Deleting canonical files locally
does not make an occupied committed base eligible for bootstrap.

Retain the original bootstrap evidence for retries; do not capture new empty-base
evidence after genesis exists. Commit/push genesis and fetch before capturing
ordinary `capture_handoff_base` evidence for the first Git-backed transaction.
This preserves the existing ordinary committed-base anchor. Bootstrap handoff
also retains ordinary exact-byte requirements: commit `project.yaml -text` and
`events.jsonl -text` patterns in the repository's `.gitattributes` before
bootstrap to preserve canonical bytes when Git's `core.autocrlf` is enabled.
Git text conversion can otherwise make the post-checkpoint ordinary handoff
fail closed; bootstrap does not configure Git or normalize canonical bytes.
The Git regression fixture enables `core.autocrlf=true` and commits this policy
before testing genesis and the first ordinary transaction. Bootstrap handoff
uses local Git reads only: an **unfetched** remote advance cannot be detected,
and capture is not a reservation or remote lock. The single-active-workstation
and operator-fetch rules still apply.

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
