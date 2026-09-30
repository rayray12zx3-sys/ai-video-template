# QC Contract v0.1

QC must answer not only whether something failed, but where the failure belongs and where production should return.

## Layers

### Q0 Technical File QC
Deterministic checks:
- exists/readable
- codec
- resolution
- fps/frame count
- duration
- audio presence
- color metadata

### Q1 Visual / Temporal Technical QC
- identity
- anatomy
- prop correctness
- exact text
- geometry
- camera
- motion
- temporal consistency
- artifacts
- continuity

### Q2 Creative QC
- expression
- energy
- composition
- art direction
- storytelling
- performance
- pacing
- emotional intent

### Q3 Delivery QC
- timeline/master specs
- audio
- captions
- clean versions
- logo/safe area
- required deliverables

## Dimension status

- PASS
- FAIL
- NOT_APPLICABLE
- NOT_REVIEWED

Overall may also be CONDITIONAL_PASS when explicitly justified.

## Failure contract

Every critical FAIL records:
- observation
- interpretation
- owner
- reason code(s)
- recommended route/action

Owners:
STORY / SOURCE / REFERENCE / PREVIS / GENERATION / POST

QC itself does not rewrite prompts or regenerate media.

## Review authority

Machine: deterministic file/metadata facts.

AI reviewer: assistance for drift, artifacts, obvious text/continuity issues.

Human: creative direction, performance, emotion, final visual acceptance.

## Shot-aware QC

QC profiles avoid forcing every dimension on every shot.

Examples:
- CHARACTER_LOCKED_LOW_MOTION
- REAL_UI
- STRUCTURE_HEAVY
- DELIVERY_MASTER

Exact-text shots can check expected vs observed semantic content. Interaction-heavy shots can check structured relations such as hand CONTACT sample_object.

Locked-property QC checks what must remain unchanged during revision.

## Temporal/editability checks

- flicker/morphing
- identity/background drift
- object disappearance
- unwanted camera/body motion
- clean start/end handles
- transition safety

## Stop-loss integration

Repeated same failure across candidates increments a structured failure count. At threshold, return REPLAN_REQUIRED rather than generating another candidate.

## Evidence and override

QC may attach contact sheets, keyframes, ffprobe reports and review notes as evidence.

Human override is allowed but must record actor, decision and reason in project history.
