# Execution Surface & Reconciliation Contract v0.1

Initial surfaces:
- CODEX_PLUGIN
- RAW_CLI
- WEB_MANUAL
- CANVAS_WEB
- CHATGPT_ACTION
- OTHER_MANUAL

Availability is environment-specific.

## Execution claim

Before starting a paid candidate, State Engine creates an execution claim containing:
- ticket_id
- shot_id
- candidate_id
- provider
- expected workspace
- execution_surface
- actor
- state_revision
- claimed_at

Only one active claim may exist for the same candidate intent.

A second surface must reconcile/close the first claim before creating another paid attempt.

## Manual Web reconciliation

If the user creates a candidate manually on PixVerse Web:
1. register EXTERNAL_EXECUTION / WEB_MANUAL
2. capture provider task/asset ID when available
3. capture actual model/mode/settings/prompt when known
4. mark unknown provenance fields UNKNOWN
5. register output asset/locator
6. run normal QC/selection

Never fabricate missing settings.

## Shared account accounting

Project spend ledger uses ticket/execution receipts.
Account balance snapshots are reconciliation evidence only when unrelated activity may exist.

## Future ChatGPT actions

A future PixVerse action connector is just another execution surface and must obey the same State Engine claim, Action Guard, workspace, receipt and provenance rules.
