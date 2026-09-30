# Criticality Vocabulary v0.1

Purpose: give gates and validators a reusable way to decide what must exist before a stage can advance without hard-coding asset or shot names.

## Principle

Criticality describes **when the project depends on an item**, not whether the item is creatively important in general.

## Standard values

### OPTIONAL
May be absent without blocking any default gate.

### REQUIRED_FOR_STORYBOARD
Must be approved before storyboard approval can be considered complete.

Typical examples:
- primary character identity master
- mandatory world/environment master
- critical prop whose design affects shot composition

### REQUIRED_FOR_ANIMATIC
May be unresolved during early storyboard work, but must be approved before static animatic approval.

Typical examples:
- shot-specific visual anchor
- blocking/previs evidence for a complex shot

### REQUIRED_FOR_GENERATION
Must be approved before a generation ticket can become executable.

Typical examples:
- selected first frame
- required reference pack
- source motion clip
- exact UI/source capture

### REQUIRED_FOR_DELIVERY
May not block generation, but must exist before final delivery.

Typical examples:
- final logo package
- captions
- legal/brand asset
- final audio stem

## Shot readiness tags

Shots may separately expose:
- REQUIRED
- OPTIONAL
- OMITTED_BY_DESIGN

`OMITTED_BY_DESIGN` requires evidence/approval; it is not equivalent to missing.

## Gate mapping

Default profile:
- G1 MASTER_ASSETS_APPROVED → all REQUIRED_FOR_STORYBOARD items approved
- G2 STORYBOARD_APPROVED → all REQUIRED shots structurally complete and required storyboard evidence approved
- G3 STATIC_ANIMATIC_APPROVED → all REQUIRED_FOR_ANIMATIC items approved
- G4 GENERATION_READY → required generation inputs can be resolved
- G6 FINAL_QC_APPROVED → all REQUIRED_FOR_DELIVERY items resolved

Profiles may narrow or expand these mappings, but may not introduce project-specific asset IDs into validator source code.

## Invariants

- Criticality is data, not code.
- Criticality does not imply provider choice.
- Changing an item to a weaker criticality is an auditable state transition.
- A missing required item produces NOT_READY, not a provider/generation failure.
