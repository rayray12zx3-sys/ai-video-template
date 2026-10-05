# Phase I2 — validators, gates, and action guards

I2 is read-only. `StateEngine.begin_transaction` remains the only ordinary writer of
`project.yaml` and `events.jsonl`. `StateEngine.inspect_consistency` and
`inspect_history` reject a pending journal and never recover or write it.

## Canonical I2 fields

The existing `2.0` project schema gains optional top-level objects `brief`,
`storyboard`, `animatic`, `generation_plan`, `final_qc`, an `evidence` array, and
`workflow_status`. Existing I0/I1 projects remain loadable. The gate profile
requires these objects only when the corresponding gate is evaluated.

Assets use stable `id`, `lifecycle`, and `criticality`. An `APPROVED` or `FINAL`
asset requires `sha256`, provenance, and an available non-provider locator.
Provider outputs additionally require `media_metadata`, `provider_task_id`, and
`lineage`. Available project-relative `LOCAL` locators are checked against the
recorded SHA-256. An asset without explicit `external_processing` is treated as
`REVIEW_REQUIRED`. Upload also requires its provider in `allowed_providers`.
`selections` maps group names to existing nonempty asset IDs; malformed or
dangling selections fail validation. An asset's `selected` flag, when present,
must be boolean.

Shots use `id`, `readiness`, `intent`, `duration_frames`, `production_method`,
`generation_ready`, and `input_asset_ids`. A required shot's generation readiness
needs bound `GENERATION_READINESS` evidence. Dependency edges use `source`,
`target`, and typed `impact` values from the frozen interface.

Evidence records use `id`, `kind`, `subject`, `subject_hash`, `status`,
`actor_type`, and `state_revision`. `subject` is `project:<field>`, `asset:<id>`,
or `shot:<id>`. `subject_hash` is the SHA-256 of deterministic UTF-8 JSON over
that subject (`validators.fingerprint`). `dependency_hashes` maps each relevant
subject reference to the same fingerprint. An approval is current only when
its subject and all recorded dependency hashes match, its revision is not in
the future, and `expires_at` has not passed. Gate-specific required bindings
prevent a missing dependency hash from bypassing stale detection. New evidence
is written through a State Engine transaction with its final subject content.

## Interfaces

- `validators.validate_project(engine)` returns a `ValidationResult` with
  `snapshot`, structured `findings`, and `ok`. It checks schema/history,
  canonical references, asset materialization, evidence bindings, and typed
  dependency invalidation. It reports missing propagation; it does not mark
  downstream items stale. State Engine rejects an upstream edit with dependents
  unless the transaction declares affected dimensions, and rejects intersecting
  changes unless the dependent is marked stale. Adding, removing, or changing
  an edge to an existing dependent needs `dependency_changes` audit metadata
  and invalidates that dependent. Remediation of a stale dependent needs a
  later audited approval transition.
- `gates.evaluate_gates(engine, approval_verifier=trusted_verifier)` derives G0–G6 with `PASS`, `FAIL`, `BLOCKED`,
  or `NOT_APPLICABLE`, blocking/nonblocking findings, required evidence, and the next
  remediation. The output is a report, not canonical state.
- `guards.guard_action(engine, ActionRequest(...))` returns `ALLOW` or `DENY`.
  Every action binds expected revision and project hash. It checks concrete
  permission independently from gate readiness.

## Gate profile

| Gate | Direct requirements |
| --- | --- |
| G0 BRIEF_LOCK | Nonempty brief and human `BRIEF_LOCK` evidence |
| G1 MASTER_ASSETS_APPROVED | `REQUIRED_FOR_STORYBOARD` assets approved and materialized with human `ASSET_APPROVAL` |
| G2 STORYBOARD_APPROVED | Storyboard, complete required shots, human `STORYBOARD_APPROVAL` bound to required shots; omissions need human approval |
| G3 STATIC_ANIMATIC_APPROVED | Animatic, human `ANIMATIC_APPROVAL` bound to storyboard and required animatic assets |
| G4 GENERATION_READY | Required generative shots (`AUTO`, `AI_IMAGE`, `AI_VIDEO`, explicit generation substeps, and unresolved required/conditional lip-sync), machine `GENERATION_READINESS` bound to their input assets, approved inputs, upload policy readiness, and required generation assets |
| G5 BATCH_GENERATION_ALLOWED | Generation plan and human `BATCH_APPROVAL` bound to required shots |
| G6 FINAL_QC_APPROVED | Separate technical PASS and creative APPROVED states, human `FINAL_QC_APPROVAL`, and required delivery assets |

Each gate also requires its preceding gates. Global canonical validation errors
block every gate. G4/G5 return `NOT_APPLICABLE` for projects without required
generative shots; this does not authorize a paid action. G4 and G5 are never
spend authorization.

## Action permissions

| Action | Additional conditions |
| --- | --- |
| `EXTERNAL_UPLOAD` | Approved input, explicit provider/workspace, policy ALLOWED or human action/provider/workspace-bound review approval; FORBIDDEN always denies |
| `PAID_GENERATION` | G4; exact shot/input, ticket/candidate, quote/budget, current human `SPEND_APPROVAL` bound to ticket, candidate, shot, action, provider, workspace, cost, and revision; fresh trusted preflight and CLEAR submission state |
| `BATCH_GENERATION` | Same as paid generation plus G5 |
| `REPLACE_ASSET` | Human action-bound approval if target is selected, approved, or final |
| `DESTRUCTIVE_OPERATION` | Human action-bound approval for the target |

The I2 guard obtains preflight only through an injected `preflight_verifier`.
The verifier returns facts bound to provider, workspace, revision, and project
hash; a caller-supplied `ActionRequest` cannot claim preflight readiness.
Human authorization for guarded actions also needs an injected
`approval_verifier` that checks the identity/provenance of the canonical record.
Without these trusted verifiers, paid actions deny by default. I3 must supply
the verifiers from a trusted runtime/approval boundary and implement the full
Generation Ticket/receipt protocol. A mere `actor_type: HUMAN` string is not
identity proof. No I2 API submits to a provider or spends credits.

## Tests

`python -B -m unittest discover -s tests -v` uses temporary projects. It does
not mutate checked-in examples or contact providers.

## Audit hardening

Every human gate requires a verifier of the exact matching evidence/snapshot, with no default trust. Guard callbacks support both gate `(evidence, snapshot)` and action `(kind, subject, request, snapshot)` calls. The verifier may be platform-attested or Ed25519-backed, but its trust configuration must be injected outside canonical state. Platform-attested support remains deployment-blocked until the hosting runtime exposes a real immutable explicit-user attestation. See [trusted human approval](../governance/trusted-operator-approval-v1.md) and [composite generation contracts](../governance/composite-generation-contract-v1.md). Old unsigned evidence is never silently adopted.
