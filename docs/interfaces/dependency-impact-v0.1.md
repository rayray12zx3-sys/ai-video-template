# Dependency & Impact Semantics v0.1

Purpose: invalidate only the downstream artifacts that are genuinely affected by an upstream change.

## Dependency edge

Each dependency is typed:

```yaml
depends_on:
  - target: asset:SUBJECT_MASTER
    impact: IDENTITY
```

Supported impact classes:

- IDENTITY
- APPEARANCE
- STRUCTURE
- COMPOSITION
- CAMERA
- MOTION
- TIMING
- SEMANTIC_CONTENT
- AUDIO
- BRAND
- TECHNICAL_FORMAT
- DELIVERY_ONLY
- GENERIC

## Change declaration

A state transition that changes an upstream entity records affected dimensions, for example:

```yaml
change:
  target: asset:SUBJECT_MASTER
  dimensions:
    - APPEARANCE
```

## Propagation rule

A downstream entity becomes STALE only when:

1. it depends on the changed upstream entity, and
2. at least one dependency impact class intersects the changed dimension set.

Unknown/legacy edges use `GENERIC`, which conservatively invalidates downstream dependents.

## Examples

Character face texture changes:
- reference depending on APPEARANCE → STALE
- subtitle depending only on TIMING → unchanged

Storyboard timing changes:
- animatic timing approval → STALE
- immutable approved character master → unchanged

Final logo changes:
- delivery composite depending on BRAND → STALE
- upstream generated shot candidate → unchanged

## Propagation levels

- DIRECT — immediate dependent is stale
- TRANSITIVE — stale artifacts may invalidate their dependents using the same typed-edge rules
- REVIEW_ONLY — downstream item stays valid but receives a review warning

## Approval handling

An approval bound to a dependency set becomes STALE when a required dependency becomes stale or changes in an intersecting dimension.

## Invariants

- No "invalidate everything" default for typed edges.
- No silent re-approval after a dependency change.
- Propagation is performed by the state transition engine; the validator only reports inconsistencies.
- Impact analysis output is auditable and can be surfaced before applying a revision.
