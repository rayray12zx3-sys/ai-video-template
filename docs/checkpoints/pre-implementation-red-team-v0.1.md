# Pre-Implementation Red-Team v0.1 — 2026-09-22

Status: PASS_AFTER_P0_AMENDMENTS

Scope was intentionally bounded to risks likely to force architectural rework. No new provider/tool discovery was pursued.

## P0 findings

### P0-1 — Paid direct-create crash window
Risk:
A paid command may reach the provider but Codex/process may crash before storing the returned task ID. Local ticket idempotency cannot prove that re-running will not spend again.

Finding:
PixVerse Canvas documents patch idempotency/edit-version controls, but current official docs do not document equivalent provider-side idempotency for ordinary direct `create video/image/etc.` commands.

Fix:
Generation Ticket v0.2 adds PREPARED/SUBMITTING/UNKNOWN_SUBMISSION and a durable submission journal. UNKNOWN_SUBMISSION never auto-retries.

Verdict: CLOSED BY DESIGN.

### P0-2 — project.yaml race / lost update
Risk:
Two agents can read revision 42 and both write revision 43.

Fix:
Only a State Engine may mutate canonical state. Writes use expected revision + expected hash, exclusive writer lock and compare-and-swap semantics.

Verdict: CLOSED BY DESIGN.

### P0-3 — project.yaml/events.jsonl half-commit
Risk:
Crash between updating current state and append-only history leaves inconsistent control files.

Fix:
Durable pending transaction + atomic state replace + event append + deterministic startup recovery.

Verdict: CLOSED BY DESIGN.

### P0-4 — Shared PixVerse workspace race
Risk:
Using `workspace switch` as ambient mutable state allows another shell/agent to redirect a paid action.

Finding:
PixVerse CLI exposes per-command `--workspace-id`.

Fix:
Automated account/paid commands must use explicit expected workspace ID. Never depend on global workspace switch state.

Verdict: CLOSED BY DESIGN.

### P0-5 — PixVerse Canvas concurrent edits
Risk:
Another editor/agent changes Canvas after a patch was prepared.

Official behavior:
Canvas graph exposes `edit_version`; patch input carries `base_edit_version`. If it changed, official guidance is to re-read and rebuild the patch rather than replacing only the version. Patch dry-run/apply derives stable idempotency for unchanged input; dispatch/reconcile requires current edit_version.

Fix:
Canvas adapter treats provider edit_version as its own concurrency domain in addition to project state_revision.

Verdict: CLOSED BY DESIGN.

### P0-6 — Schema evolution
Risk:
Codex implementation evolves the schema and later opens an older/newer project with incompatible semantics.

Fix:
Explicit versioned migration chain, dry-run, validation, backup/checkpoint, migration event and refusal to write unknown newer versions.

Verdict: CLOSED BY DESIGN.

## P1 findings

### P1-1 — External upload/data classification
Before real company media is sent to any external provider, project policy should classify an asset as external-upload allowed/blocked/review-required. Phase I0 does not need provider Terms automation, but paid/provider execution guards should eventually enforce this.

Recommended field/policy:
`external_processing: ALLOWED | REVIEW_REQUIRED | FORBIDDEN`

Status: implementation issue; not Phase I0 blocker.

### P1-2 — Tool/version drift
Capture versions for:
- Codex
- Node/npm
- PixVerse CLI
- schema/template
- Premiere/AE where production depends on them

Do not auto-update PixVerse/Adobe during an active production without explicit change control.

Status: covered by environment snapshot requirement; implementation issue.

### P1-3 — No-admin Windows portability
Core Phase I0-I4 should not require administrator privileges. Prefer user-space/node/repo tooling. Optional Adobe/open-media/provider installations are separate.

Status: implementation acceptance criterion.

### P1-4 — MVP creep
Do not implement everything at once.

MVP implementation scope:
1. canonical state + State Engine
2. events/transaction recovery
3. validators/gates
4. router/ticket compiler
5. QC contract/profile data
6. read-only PixVerse capability/account adapter

Deferred:
- paid PixVerse execution
- Canvas writer/dispatch
- Flow automation
- Gemini API video
- Adobe automation
- open-media integration
- local AI
- UI/dashboard

Status: CLOSED by scope decision.

## P2 / monitor

- large events.jsonl growth: not currently a blocker
- provider capability churn: handled by snapshots/adapters
- Drive locator access changes: handled by availability/integrity states
- Git merge conflicts in code/docs: normal Git workflow; runtime state remains single-writer

## Final red-team verdict

No architecture-breaking issue remains after the P0 amendments.

Phase I0 may start.

Paid provider writes remain disabled until:
- State Engine/recovery exists
- action guards exist
- provider read-only preflight passes
- UNKNOWN_SUBMISSION recovery path is tested
