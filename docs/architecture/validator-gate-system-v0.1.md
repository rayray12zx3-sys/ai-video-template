# Validator & Gate System v0.1

## Separate four layers

1. Schema — is the data structurally valid?
2. Validator — is current data internally consistent?
3. Gate evaluator — is the production ready to enter the next stage?
4. Action Guard — may this concrete action run now?

These must not be collapsed into one legacy-style script.

## Validation levels

### L0 Schema
Types, required fields, enums, IDs, timestamps.

### L1 Integrity
References, asset hashes, dependency targets, selections, evidence and timeline consistency.

### L2 Readiness
Can this shot/stage perform the requested next action?

### L3 Policy
Budget, candidate limits, interaction policy, provider snapshot freshness, human-approval requirements.

Validation should be pure/read-only. It reports issues; state transitions happen elsewhere.

Severity:
- ERROR
- WARNING
- INFO

## Stages

- DISCOVERY
- PREPRODUCTION
- REFERENCE
- STORYBOARD
- ANIMATIC
- GENERATION
- POST
- DELIVERY
- REVISION

Stages are not gates.

## Default gates

- G0 BRIEF_LOCK
- G1 MASTER_ASSETS_APPROVED
- G2 STORYBOARD_APPROVED
- G3 STATIC_ANIMATIC_APPROVED
- G4 GENERATION_READY
- G5 BATCH_GENERATION_ALLOWED
- G6 FINAL_QC_APPROVED

G3 blocks bulk paid video generation; small pilots may be allowed.

Gate status:
- NOT_READY
- READY_FOR_REVIEW
- APPROVED
- STALE
- NOT_APPLICABLE

Approvals bind to a state revision/dependency set. Relevant upstream changes make approvals STALE.

## Human authority

Default HUMAN_REQUIRED:
- creative brief lock
- master creative approval
- static animatic
- paid generation
- final creative QC
- delivery approval

Machine/agent checks may approve deterministic technical facts.

## Action Guards

Paid generation checks:
- valid ticket
- shot readiness
- auth/workspace
- subscription/credits/slots
- fresh capabilities
- human spend approval
- candidate limit
- shot/project budgets

Other guards cover destructive overwrite, selected/final replacement and stale-ticket execution.

## Required project behavior

A non-COMPLETE project without `next_action` is an error.

A RECEIVED asset must not be requested again unless explicitly marked REUPLOAD_REQUIRED with a reason.

Only one ACTIVE prompt is allowed per shot/purpose.

Machine-checkable facts and human/creative review must be distinguished.
