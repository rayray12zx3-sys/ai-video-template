# Generation Ticket Retention Policy v0.1

Purpose: preserve paid/executed history without turning Git into a dump of regenerated draft tickets.

## Durable tickets

The following MUST be retained:

- any ticket that reached APPROVED for spend
- any ticket that was SUBMITTED
- any ticket with a provider receipt
- any paid FAILED execution
- any candidate referenced by selection/QC evidence
- any ticket required to explain a final asset's lineage

Suggested path:

```text
records/generation/YYYY-MM/<shot>/<ticket-id>.yaml
records/receipts/YYYY-MM/<ticket-id>.json
```

## Ephemeral tickets

These may be regenerated and do not require permanent Git history:

- DRAFT tickets never approved
- preflight drafts invalidated before spend approval
- derived previews of provider-specific commands
- queue views

Suggested working location:

```text
generated/tickets/
```

and excluded or periodically cleaned according to implementation policy.

## Redaction

Never persist:
- OAuth tokens
- API secrets
- browser session cookies
- private credentials

Receipts may persist provider task IDs, workspace aliases, credit accounting and timestamps but not secrets.

## Immutability

Executed durable tickets and receipts are append-only records. Corrections are made by adding a correction event or superseding record, not rewriting execution history.

## Idempotency retention

The idempotency key of every submitted ticket remains durable for at least as long as the provider receipt is retained, preventing accidental duplicate paid submission after restart/resume.

## Git policy

Textual ticket/receipt records may live in Git.

Large generated videos/images do not need to be committed; their asset records retain URI/locator, hash and lineage.

## Invariants

- If money/credits were spent, preserve the record.
- If an output participates in a final/approved lineage, preserve the record.
- If nothing was executed and no approval depended on it, the ticket may be regenerated.
