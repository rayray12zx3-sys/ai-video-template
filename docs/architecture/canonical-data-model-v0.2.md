# Canonical Data Model v0.2

## Core principle

Single Source of Truth does not mean one file owns every kind of information. It means each fact has exactly one authority.

Proposed runtime authorities:

- `project.yaml` — current project truth
- `events.jsonl` — append-only history
- evidence files — immutable supporting evidence
- Git — file/version history

Generated STATUS/TODO/queues are derived and must never be edited as authoritative state.

## Core entities

### Project
Contains identity, mode, interaction mode, timeline, workflow, provider availability, budget and next_action.

Modes:
- NEW_PRODUCTION
- REVISION

Interaction modes:
- DISCOVERY
- PRODUCTION
- PRODUCTION_FAST

### Asset
Stable ID independent of filename.

Lifecycle:
EXPECTED → RECEIVED → IMPORTED → REVIEWED → APPROVED

Other states:
REJECTED / SUPERSEDED / MISSING / STALE

Approved assets require provenance and SHA-256.

### Shot
A shot owns:
- intent
- requirements
- constraints
- key states
- inputs
- dependencies
- previs requirement
- production method
- evidence references
- QC state
- status

Shots specify what must be true, not which current model should be used.

### Requirements vs Constraints

Requirements tell the router what is difficult/important:
- identity
- structure
- motion
- expression
- camera
- continuity

Constraints tell generation/QC what must literally hold:
- exact semantic text
- spatial relations
- interactions
- camera/lens details
- must_preserve
- must_not

### Semantic content roles
- DIEGETIC
- OVERLAY
- UI
- BRAND
- CAPTION

### Production methods
- AUTO
- AI_IMAGE
- AI_VIDEO
- SOURCE_IMAGE
- SOURCE_VIDEO
- STATIC
- PREMIERE
- AFTER_EFFECTS
- COMPOSITE
- DERIVED
- NO_NEW_MEDIA

Production method and approval evidence are independent.

### Evidence
Evidence answers: "why is this state/asset/shot considered valid?"

Examples:
- HUMAN_APPROVAL
- QC_REPORT
- CONTACT_SHEET
- REFERENCE_IMAGE
- SOURCE_FRAME
- PREVIS_FRAME
- REVIEW_NOTE
- HASH_VERIFICATION
- PROVIDER_RECEIPT

### Key states
Complex motion can define start / event / end truths without embedding them only in a prompt.

### Lineage and dependencies
Assets and shots may depend on other assets/shots. Superseding an upstream dependency makes downstream artifacts STALE through impact analysis.

### Selection groups
Candidate assets remain ordinary Assets and share a `selection_group`; the project records which asset is selected.

## Pressure-test result

v0.2 represents without project-specific exceptions:
- Exact-text interaction with a hand-contact constraint
- Camera and motion complexity with structural transitions
- Revision with locked properties, lineage, and stop-loss
- Recorded interface source media
- Editorial match cut without new media
