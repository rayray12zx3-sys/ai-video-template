# Legacy Workflow Audit v1

This document preserves reusable architecture lessons from a completed legacy AI-video workflow. Project identity, customer/company context, raw production assets, and private provider/account details are intentionally omitted.

## What worked

- Reference-first identity control with approved masters and SHA-256 provenance.
- Frame-based storyboard as a strong timing source of truth.
- Clear distinction between candidate / selected / approved assets.
- Formal approvals, receipts, QC evidence, and archive discipline.
- Static animatic before bulk generation.
- Limited candidate budget and a fallback ladder.
- Main editorial work separated from targeted repair/composite work.
- Real source UI retained as source media rather than recreated when fidelity mattered.

## Structural problems

### State fragmentation

Current state was duplicated across status files, manifests, logs, and planning documents. Several became stale while production moved on.

### Validator overfitting

The legacy validator hard-coded project IDs, shot exceptions, exact paths, and literal approval phrases. This demonstrated the value of validation but not a reusable implementation pattern.

### Premature generation planning

Provider run sheets were prepared before upstream timing/reference decisions were locked, creating unnecessary rewrite/TBD states.

### Formal pipeline vs actual production

Real production used revision, emergency, and manual branches that were not fully represented by the formal provider-job model.

### Technical gates stronger than creative acceptance

Technical correctness did not guarantee creative acceptance. Technical QC and creative QC therefore remain separate.

## Failure-routing lesson

General routing rule:

- identity / costume / composition / environment error -> REFERENCE
- motion / expression error with correct reference -> GENERATION
- timing / local repair -> POST
- story error -> STORYBOARD

This routing principle is represented in the provider-neutral architecture rather than through project-specific shot IDs.

## Keep / generalize / simplify

Keep:
- reference masters + hashes
- frame-based storyboard
- approvals/evidence
- candidate limits
- fallback ladder
- modular post pipeline

Generalize:
- gates
- provider capability snapshots
- asset/evidence registry
- revision lane

Rewrite:
- validator
- current-state handling
- provider routing

Simplify:
- prompt-version sprawl
- per-item blind review where risk is low
- duplicate status documents
