# Composite generation contract

G4/G5 apply to required `AUTO`, `AI_IMAGE`, `AI_VIDEO` shots and any required shot with `generation_required=true`. Final compositing method does not waive generation readiness, input approval, external-processing review, spend or execution guards.

Required/conditional `lip_sync.status` conservatively activates G4/G5 unless a validated non-generative source contract exists. This closes implicit lip-sync/base-plate generation hidden inside composite shots without adding project-specific IDs to generic code.

Three supported contracts:

1. `production_method=COMPOSITE`, `generation_required=true`, `base_plate_policy=GENERATIVE`: generation inputs/readiness bind the entire canonical shot. Providers still need exact action/ticket/input and cost approval. Do not call composite routing as a hidden generation adapter. A future separately named sub-shot is possible only through an explicit audited State Engine transaction with its typed dependency edges.
2. `generation_required=false`, `base_plate_policy=APPROVED_SOURCE`, `base_plate_asset_id=<id>`: the referenced video must be a canonical approved/final source input, not a provider output; materialization/hash/provenance validation remains mandatory. For required/conditional lip-sync, also declare `lip_sync_execution=SOURCE_ALREADY_SYNCHRONIZED` and obtain trusted `SOURCE_SYNC_APPROVAL` over the shot, source asset and typed incoming dependencies. G2 enforces this human review. Actual provider or lip-sync generation invalidates this route and must return to contract review.

Declaring a source plate does not create/approve one. No provider/paid action is authorized by G4 `NOT_APPLICABLE`. Readiness findings and human gates remain independent. New fields are additive in schema 2.0; conflicting or malformed values fail validation. Every COMPOSITE shot requires an explicit boolean generation flag and base policy; old implicit composites fail closed until reviewed. Plain NO_NEW_MEDIA editorial shots remain non-generative.

3. `generation_required=false`, `base_plate_policy=DETERMINISTIC`: only local typography/graphics or existing non-generative compositing. Active lip-sync still activates G4/G5; this field cannot waive that work. It does not grant source, claim or creative approval.

Supported lip-sync statuses are NONE, REQUIRED, CONDITIONAL, PARTIAL and AVOIDABLE. All except NONE conservatively require the generative or explicitly approved synchronized-source path; unknown values/types fail validation. AVOIDABLE describes a potential framing choice, not an already-approved omission.
