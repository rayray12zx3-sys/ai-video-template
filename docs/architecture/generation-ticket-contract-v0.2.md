# Generation Ticket Contract v0.2

Supersedes `generation-ticket-contract-v0.1.md`.

A Generation Ticket is an executable artifact compiled from canonical project state + Production Plan + current provider capability evidence. It is not a source of project truth.

## Completeness goal

A ready ticket must identify:
- shot/state revision
- exact approved inputs and hashes
- platform/execution surface/mode
- prompt and parameters
- hard constraints
- provider capability snapshot
- expected workspace/account scope
- spend approval
- expected output asset
- QC profile
- fallback/stop condition

## State binding

Tickets bind to:
- state_revision
- relevant dependency hashes/IDs
- provider capability snapshot ID
- expected workspace ID where applicable

Relevant changes make the ticket STALE.

## Paid submission journal

Local ticket idempotency is NOT assumed to be provider-side idempotency.

Before any paid provider command:

1. persist a durable submission record in state `PREPARED`
2. include ticket ID, local idempotency key, provider, workspace ID, cost estimate and exact command/request fingerprint
3. immediately before execution move to `SUBMITTING`
4. execute once
5. persist provider task/job/dispatch ID and receipt as soon as returned

## Ambiguous submission

If the executor crashes, times out, loses stdout, or receives an ambiguous transport failure after entering `SUBMITTING` and no provider job ID/receipt was durably captured:

`UNKNOWN_SUBMISSION`

Rules:
- NEVER automatically rerun the paid command
- reconcile provider task/asset/history/account usage first
- if existence cannot be proven or disproven, require human review
- a new paid attempt requires a new candidate/ticket or explicit resolution of the unknown submission

This rule is especially important for direct PixVerse `create ...` commands because current official CLI documentation does not document provider-side idempotency for ordinary create operations.

## PixVerse Canvas exception / stronger guarantees

Canvas patch workflows expose provider-side controls:
- `base_edit_version`
- stable patch idempotency for unchanged patch inputs
- explicit `edit_version` on dispatch/reconcile
- dispatch plans/rebind

Adapter rules:
- always re-read graph/edit_version before patching
- if edit_version changed, re-read and rebuild the patch; never just replace the version number
- use patch dry-run before apply
- dispatch only explicit executable node IDs
- preserve provider dispatch plan/task IDs as receipts
- treat partial/failed dispatch as failure, not success

## Shared PixVerse workspace safety

Automation MUST pass `--workspace-id <expected_id>` (or equivalent explicit request scope) on account-sensitive and paid commands.

Do not rely on mutable global `workspace switch` state for automation.

Before spend:
- verify returned/current workspace ID matches ticket expected workspace ID
- verify credits/subscription/slots
- bind receipt to workspace ID

## Output/receipt

Durably record:
- provider task/job/dispatch ID
- submission/completion timestamps
- workspace/account alias/ID (non-secret)
- charged/refunded credits when available
- output locator
- hash/media metadata
- status

## Retry

A new paid candidate is a new ticket.

One retry = one primary hypothesis/change.

Repeated same failure reaches REPLAN_REQUIRED according to policy.

## Lifecycle

DRAFT
→ READY_FOR_PREFLIGHT
→ READY_FOR_APPROVAL
→ APPROVED
→ PREPARED
→ SUBMITTING
→ SUBMITTED
→ COMPLETED

Exceptional:
- BLOCKED
- STALE
- FAILED
- CANCELLED
- SUPERSEDED
- UNKNOWN_SUBMISSION

## Invariants

- approval does not equal submission
- SUBMITTING is durable before invoking a paid provider
- ambiguous paid submission is never automatically retried
- provider receipt/job ID is written immediately when known
- workspace scope is explicit for shared PixVerse accounts
