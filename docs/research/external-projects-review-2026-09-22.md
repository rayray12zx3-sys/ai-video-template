# External Projects Review — 2026-09-22

## Core architecture references

### CineCrew
High-value reference for a shared machine-readable film representation, asset/memory/clip structure and reviewer feedback that can update durable production rules.

Use: data-model inspiration.
Do not: copy the entire research stack.

### OpenMontage
High-value reference for declarative pipeline stages, checkpoints, human approvals, provider abstraction and budget/action controls.

Use: orchestration and gate concepts.
Do not: inherit unnecessary provider breadth.

### ai-video-pipeline
Useful lightweight reference for file-driven state/gates and agent-oriented execution.

Use: reminder to keep v2 small and inspectable.

### take
Useful reference for a Codex/agent-friendly, file-first script → beats → shots → storyboard → media workflow.

Use: file-native workflow principles.

## Previs

### open-media / Shot Composer
Browser-based 3D shot composition/previs with camera, pose and motion concepts and agent/MCP potential.

Use: optional risk-based previs for complex blocking/camera shots.

Concern: browser-local persistence/pre-1.0 behavior means it must not own canonical project state.

## Generation/consistency research

### MultiShotMaster
Useful multi-shot consistency/control ideas. Treat as research inspiration rather than required local deployment.

### MV-S2V
Supports the value of multi-view character masters; reinforces the legacy six-view reference approach.

### Memento
Useful long-form/multi-shot research concepts, but heavy research infrastructure makes it unsuitable for the critical path.

## QC/revision research

### MuSS
Useful taxonomy/benchmark inspiration for cross-shot identity, grounding, motion and non-copy behavior.

### LiveEdit / retake-style systems
Useful conceptual support for local revision instead of whole-clip regeneration.

## General adoption policy

A new open-source project enters the production dependency graph only after:
1. a concrete unmet requirement exists,
2. a small pilot demonstrates value,
3. maintenance/security/portability costs are acceptable.

Otherwise borrow architecture/methods without integrating the project.
