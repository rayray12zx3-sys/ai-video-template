# Legacy Import / Mapping Contract v0.1

## Purpose

Define the repository-safe boundary for importing the legacy production record into Template v2 without treating legacy status files as canonical truth, silently dropping unknown information, or weakening the generic schema-migration contract.

Parent phase: I6 — Legacy migration and replay.

This contract follows the replay fixtures and current schema, State Engine, and validator contracts.

## Boundary decision

legacy import is **external legacy import**, not a fake older Template-v2 schema migration.

A legacy input is external source material and may be incomplete or contradictory. It cannot override canonical state. Therefore:

- do not assign the source an invented `schema_version: 1.x`
- do not register legacy project as a `MigrationStep` in `src/aivideo/migration.py`
- do not relax the adjacent schema-migration rule to allow arbitrary field rewriting
- the importer produces a **current-schema candidate + import report** from a sanitized external fixture
- dry-run import never mutates canonical state
- canonical adoption is a later, separate State-Engine-controlled operation (I6c)
- if I6c finds no suitable State Engine adoption primitive, it must introduce an explicit import/adoption contract rather than bypassing the State Engine or disguising the import as schema migration

Generic schema migration remains reserved for older canonical Template-v2 documents whose `schema_version` is explicitly supported.

## Authority rules

### Canonical candidates

Legacy information may become current v2 canonical state only when the sanitized source contains enough evidence to support the mapped assertion.

### Supporting evidence only

Legacy documents that described work but were not authoritative at the time (for example stale STATUS/TASK_STATE files, run sheets, or manual notes) may become provenance/supporting evidence, but must not override stronger source material.

### Unresolved

Conflicting, missing, ambiguous, private-only, or unverifiable legacy facts stay explicit in the import report. They are never guessed.

Every recognized source field must end in exactly one disposition:

- `MAPPED`
- `EVIDENCE_ONLY`
- `UNRESOLVED`
- `REDACTED`

No recognized field may disappear silently.

## Repository-safe fixture format

Checked-in fixtures use a normalized external format named:

`legacy-project-sanitized-v1`

Illustrative shape:

```json
{
  "format": "legacy-project-sanitized-v1",
  "fixture_id": "legacy-project-representative",
  "project": {
    "legacy_project_id": "legacy-project",
    "mode_hint": "NEW_PRODUCTION",
    "workflow_status_hint": "COMPLETE"
  },
  "assets": [],
  "shots": [],
  "approvals": [],
  "legacy_records": [],
  "unknown_fields": {}
}
```

The fixture may contain only deterministic repository-safe values. It must not contain:

- credentials, OAuth tokens, cookies, signed URLs
- account/workspace identifiers
- private/company media
- absolute Windows/macOS/Linux paths
- personal names or private account data not needed by the replay
- provider secrets
- live provider URLs whose access depends on private authorization

A fixture may use synthetic identifiers, hashes of synthetic fixture bytes, relative fixture paths, and sanitized prose derived from the already checked-in audit/replay documents.

## Asset mapping

| Legacy concept | v2 destination | Disposition / rule |
| --- | --- | --- |
| reference master / source media | `assets[]` | Map identity, role, media type, origin and provenance |
| legacy SHA-256 | `assets[].sha256` | Map only when source evidence is explicit and the sanitized fixture represents the same bytes |
| candidate asset | `assets[]` | Preserve as a distinct asset; do not collapse candidates into the selected asset |
| selected asset | `assets[].selected` and/or `selections` | Map only when the legacy selection is unambiguous |
| approved/final asset | lifecycle + evidence | Promote to `APPROVED`/`FINAL` only when the fixture has the evidence/materialization required by current validators; otherwise keep the strongest supportable lower lifecycle and emit an unresolved approval/materialization item |
| real UI recording | asset with `origin=REAL_UI`, video/image media type, `content_role=UI` where applicable | Preserve as source media; never convert into an AI-generation requirement |
| archive/location data | `locators` or report | Only project-relative repository-safe locators may enter fixtures; absolute/private paths are REDACTED and reported |
| provider output without trustworthy historical receipt identity | asset/provenance + unresolved report | Do not invent provider task/workspace/receipt fields |

## Shot / storyboard mapping

Legacy frame-based storyboard facts map into `shots[]` and, where useful, the top-level `storyboard` object.

Common mappings:

- legacy shot ID -> `shot.id`
- frame/timeline duration -> `duration_frames`
- creative intent -> `intent`
- approved input/reference relationships -> `input_asset_ids`
- production method -> `production_method` when explicit and current vocabulary supports it
- no-new-media intent -> `new_media_required=false`
- editorial-only intent -> `editorial_only=true`
- revision failure owner -> `error_owner`
- semantic/camera/motion/structure requirements -> `requirements`
- exact text / interaction / spatial restrictions / must-not conditions -> `constraints`

Provider-specific historical command text is not copied into shot semantics unless it represents a provider-neutral creative requirement.

## Representative replay mappings

### Example A — exact diegetic text + hand contact

Map provider-neutral facts only:

- exact text `SAMPLE` -> `constraints.exact_text`
- hand/contact relation -> interaction/spatial constraints
- high semantic / interaction precision -> requirements
- reference-first/composite preference may be represented by supported canonical production facts

Do not add case-specific runtime branches; the current router should reach the appropriate route from the facts.

### Example B — scale / camera / motion complexity

Map:

- camera angle / lens sensitivity -> camera requirements
- high motion complexity -> `requirements.motion_complexity=HIGH`
- structural/scale relation -> structure sensitivity and spatial constraints
- key-state intent -> provider-neutral shot requirements/constraints

No fixture-specific runtime branch is allowed.

### Example C — revision / reference-first recovery

Map the current reconstructed revision facts:

- project/fixture mode may resolve to `REVISION` where the imported fixture represents the revision state
- affected shot -> shot entity
- reference vs generation ownership -> `error_owner`
- locked properties / allowed motion / forbidden expression/body motion -> requirements/constraints

Historical attempts and the sequence of changing failure owners are supporting evidence/history. Do not flatten all historical states into simultaneous canonical truth.

### Example D — real UI source video

Map:

- real UI recording -> REAL_UI/source asset
- shot production method -> `SOURCE_VIDEO`
- no AI route is inferred
- approval/QC facts become evidence when representable

### Example E — editorial / no new media

Map:

- `new_media_required=false`
- editorial intent / match-cut semantics
- `production_method=PREMIERE` or supported no-new-media representation according to the fixture's explicit fact

Provider capability/ticket requirements must not be invented.

## Legacy status / manifest mapping

Legacy records may duplicate or stale current-state information. Treat them as follows:

| Legacy source | Rule |
| --- | --- |
| TASK_STATE / STATUS / README status | Evidence-only unless independently corroborated; never authoritative by file name alone |
| shot_manifest / run sheets | Map stable shot facts when corroborated; TBD, rewrite_required, DO NOT SUBMIT and stale execution planning become warnings/unresolved items |
| WORKLOG / revision notes | Supporting provenance/history; may support revision reconstruction but cannot overwrite stronger current facts |
| empty/pending provider job logs | Never infer that generation did or did not occur solely from absence; conflicting completed-film evidence becomes an explicit unresolved/history item |
| approvals | Map to v2 evidence only when subject, status, actor type and binding can be reconstructed safely |
| receipts | Historical provider-native evidence remains immutable; if required identity fields are unavailable, retain supporting reference/unresolved status rather than fabricating a current `ProviderReceipt` |

## Import report

Every dry-run produces a deterministic report with at least:

```json
{
  "source_format": "legacy-project-sanitized-v1",
  "source_fingerprint": "<sha256>",
  "target_schema_version": "2.0",
  "mapped_items": [],
  "evidence_only_items": [],
  "warnings": [],
  "unresolved_items": [],
  "redactions": []
}
```

Recommended item fields:

- stable `code`
- source location/key
- target location when mapped
- disposition
- message/reason
- `blocking` boolean for unresolved items

The importer must account for all recognized top-level fixture data. Unknown keys go to `unresolved_items` (or a deterministic nested unknown-field record) unless the mapping contract explicitly classifies them.

## Information-loss rule

Import is information-preserving at the sanitized-fixture boundary.

This does **not** mean every legacy field becomes canonical v2 state. It means every sanitized source fact is either:

- represented in canonical candidate state,
- retained as supporting evidence/report information,
- explicitly unresolved, or
- explicitly redacted by repository-safety policy.

Lossy normalization requires a future reviewed contract/ADR.

## Approval / lifecycle rule

Legacy labels such as "approved" are not automatically trusted as current v2 approvals.

An approval may become v2 `APPROVED` evidence only when the sanitized fixture can reconstruct the current evidence bindings required by the validator. Otherwise the importer preserves the legacy approval as supporting evidence and records why it cannot be promoted.

Likewise, an asset must not be marked `APPROVED`/`FINAL` when current materialization/hash/provenance requirements cannot be satisfied.

## Canonical adoption rule

I6b is dry-run only.

I6c must preserve these properties:

- State Engine remains the only canonical writer
- source fingerprint and import-report identity are bound to the adoption
- checkpoint/backup exists before canonical replacement/adoption
- revision/hash conflicts fail closed
- interruption does not leave a half-adopted canonical state
- duplicate adoption is rejected or deterministically recognized
- unresolved items marked blocking prevent adoption

I6c must not weaken `src/aivideo/migration.py` to achieve these properties.

## Deterministic replay rule

I6d uses five repository-safe fixtures that cover distinct production and revision behaviors.

Replay assertions must be based on canonical facts and generic router/validator behavior. A test may name a replay fixture/case, but production implementation must not branch on those case IDs.

Any mismatch between reconstructed v2 state and the checked-in legacy audit/replay expectation becomes:

1. a deterministic failing assertion when the expected behavior is already specified, or
2. an explicit follow-up Issue when the legacy fact remains genuinely unresolved.

## Local/private evidence boundary

If later local inspection of the source archive reveals additional private-only facts:

- do not commit the private source
- create a sanitized minimal reproduction when possible
- update this mapping contract only for generalizable rules
- record project-specific unresolved cases explicitly
- use a local implementation task only when the evidence cannot be reproduced safely in CI

## I6 implementation sequence

- I6b: pure deterministic importer + dry-run report
- I6c: checkpoint/backup/canonical State Engine adoption
- I6d: representative sanitized replay fixtures and comparison

The importer, adoption path, and replay suite remain separate implementation scopes with explicit prerequisites.
