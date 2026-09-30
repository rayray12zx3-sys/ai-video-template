# Generation Ticket Contract v0.1

A Generation Ticket is an executable artifact compiled from canonical project state + Production Plan + current provider capability evidence. It is not a source of project truth.

## Completeness goal

A human or executor receiving a ready ticket should not need to infer:
- which assets to upload
- which slots/roles they occupy
- which prompt is active
- which mode/parameters to use
- what output to create
- what success/failure means
- what happens after failure

## Required fields

- ticket ID/version
- shot ID
- state revision
- intent summary
- route: platform / execution / mode / model
- explicit inputs with asset IDs and hashes
- active prompt reference + compiled text
- parameters
- constraints
- provider capability requirements
- spend policy/approval
- expected output asset ID + role
- QC profile
- fallback
- status

## Execution types

### WEB_MANUAL
Provides explicit ordered manual steps: open provider, select mode, upload each asset to a named role, paste prompt, set parameters, generate.

### CLI
Compiles canonical input roles into provider-specific arguments. Credentials/tokens are never stored in the ticket.

## State binding

Tickets bind to a project state revision and relevant dependencies. When relevant state changes, the ticket becomes STALE.

## Spend safety

Paid tickets include estimated cost, candidate number and human approval by default.

Shared-account preflight verifies the intended PixVerse workspace before execution.

## Output / receipt

A completed execution records:
- provider task/job ID
- submission/completion timestamps
- charged/refunded credits
- output URI
- SHA-256
- media metadata
- status

## Idempotency

Every executable ticket has an idempotency key. An existing receipt for the same key blocks duplicate submission after restart/resume.

A real new candidate is a new ticket, not a resubmission of the same one.

## Retry hypothesis

Each retry records the main changed variable and expected effect. One retry = one primary hypothesis.

## Lifecycle

DRAFT
→ READY_FOR_PREFLIGHT
→ READY_FOR_APPROVAL
→ APPROVED
→ SUBMITTED
→ COMPLETED

Other states:
BLOCKED / STALE / FAILED / CANCELLED / SUPERSEDED
