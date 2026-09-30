# Generation Ticket Contract v0.3

Supersedes v0.2 for implementation.

Each executable ticket binds:
- project state revision/dependency hashes
- candidate ID
- execution surface/backend
- provider runtime snapshot
- technical capability snapshot
- account entitlement snapshot where paid
- expected workspace ID
- prompt transformation policy
- input asset IDs and provider-ready derivative hashes
- expected output ID
- QC profile
- spend approval

## Provider idempotency / trace

When the exact installed PixVerse backend/help confirms support:
- use provider idempotency key
- use trace/attempt identifier
- persist both before submission

Provider-side idempotency supplements the local submission journal; it does not replace it.

## Ambiguous outcomes

If exact operation/backend has verified provider idempotency, reconciliation may reuse the SAME idempotency key according to adapter policy.

If support is absent/unknown, do not automatically resubmit an ambiguous paid request.

Never create a new key merely to retry an ambiguous request.

## Execution claim

Before paid submission, State Engine holds a claim for the ticket/candidate/surface, preventing simultaneous Web/Plugin/CLI generation of the same intended candidate.

## Prompt/input provenance

Persist:
- source prompt
- compiled prompt
- enhanced/effective prompt
- transform policy
- optimizer/plugin version when available
- provider-ready derivative actually uploaded

## Spend attribution

Use ticket quote/receipt/task data. Shared-account balance deltas are not authoritative project spend.

## Output approval

Before APPROVED/FINAL, materialize to durable project-controlled storage and hash it.

## PixVerse shared workspace / Canvas

- explicit workspace ID
- no ambient workspace-switch dependency
- re-read Canvas graph/edit_version before mutation
- rebuild stale patch
- preserve dispatch/task/version IDs
