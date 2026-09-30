# Phase I4 — QC, failure ownership, and stop-loss

I4 defines how review results classify a candidate, assign a failure to the
stage that can fix it, and stop unproductive retries. It follows the frozen
QC Contract v0.1 and does not add provider-specific shot semantics.

The runtime contract is implemented in `src/aivideo/qc.py`. The QC report is
an assessment; it cannot rewrite prompts, create
media, submit provider work, approve spend, or mutate canonical project state.

## QC layers

Each applicable dimension has one of `PASS`, `FAIL`, `NOT_APPLICABLE`, or
`NOT_REVIEWED`. A result may be `CONDITIONAL_PASS` only with an explicit
justification. Do not infer a pass for an unreviewed or inapplicable dimension.

| Layer | Scope | Evidence authority |
| --- | --- | --- |
| Q0 Technical file | File exists and is readable; codec, resolution, frame rate, frame count, duration, audio presence, and color metadata | Deterministic file/metadata checks |
| Q1 Visual and temporal technical | Identity, anatomy, props, exact text, geometry, camera, motion, temporal consistency, artifacts, continuity, flicker/morphing, unwanted motion, and edit handles | Machine checks may report observable facts; visual review may assist; human review resolves judgment |
| Q2 Creative | Expression, energy, composition, art direction, storytelling, performance, pacing, and emotional intent | Human creative judgment; AI review is advisory |
| Q3 Delivery | Timeline/master specifications, audio, captions, clean versions, logo/safe area, and required deliverables | Deterministic checks where possible, with human acceptance where judgment is required |

Technical acceptance (Q0/Q1) and creative acceptance (Q2) stay separate. A
successful file probe does not imply visual or creative acceptance.

## Profiles and applicability

A QC profile selects applicable dimensions for a type of shot or delivery. It
must not hard-code project shot
IDs or paths. Unselected dimensions are explicitly `NOT_APPLICABLE`; dimensions
that should be checked but lack review remain `NOT_REVIEWED`.
Q1 requires a shot whose fingerprint matches the QC binding. Canonical
`exact_text`, `interaction`, `spatial_relations`, and `must_preserve` constraints
cannot be marked `NOT_APPLICABLE`.

The implemented profiles are `CHARACTER_LOCKED_LOW_MOTION`, `REAL_UI`,
`STRUCTURE_HEAVY`, and `DELIVERY_MASTER`. The caller supplies the stop-loss
threshold, whose default is three distinct candidates under one strategy.
Profiles should focus review on the actual requirements: for example, a
locked-property revision checks what must remain unchanged, while an exact-text
shot compares expected and observed semantic content. Q3 applies to delivery
readiness; it does not replace shot-level Q0–Q2 review.

## Failure ownership and return route

Every critical failure records the observation, interpretation, owner, reason
code(s), and recommended action. Ownership names the production area to
remediate; it does not assign blame to an individual or provider.

| Owner | Typical failure | Return route |
| --- | --- | --- |
| `STORY` | Intent, beat, or requirement is unclear or inconsistent | Revise story/shot specification |
| `SOURCE` | Required source capture or supplied media is wrong or incomplete | Repair or replace source media |
| `REFERENCE` | Identity, costume, environment, prop design, or composition reference is wrong | Return to reference selection/approval |
| `PREVIS` | Geometry, blocking, scale, or camera plan is wrong | Revise previs before generation |
| `GENERATION` | Motion, expression, temporal behavior, or generated detail fails against valid inputs | Replan or revise the generation hypothesis |
| `POST` | Timing, local repair, composite, or delivery assembly is defective | Repair in post or delivery workflow |

Reference errors return to reference/previs work; repeated prompting must not
be used to conceal a bad reference. The QC assessor recommends the route but
does not execute it. Route selection remains provider/model neutral and follows
the router and current project evidence.

## Stop-loss

Repeated occurrences of the same structured failure across distinct candidates
under the same report-bound strategy count toward the supplied threshold. New
Generation Tickets may seal an explicit stable `strategy_id`; manual QC bindings
must supply one. Evaluation requires an injected trusted strategy verifier for
the current and historical candidates. A ticket without that field cannot be
used for stop-loss evaluation until the strategy is established in trusted
supporting evidence.
Identity includes
project, shot, layer, dimension, owner, and reason codes. At threshold, report
`REPLAN_REQUIRED` and stop acquiring another candidate under the unchanged
hypothesis. Replanning may change owner, route, references, previs, constraints,
or fallback as appropriate.

Stop-loss is a production control, not permission to submit another paid
request. Existing I2 guards, approval bindings, and I3 submission/reconciliation
rules remain authoritative. In particular, an ambiguous submission remains
`UNKNOWN_SUBMISSION` and must not be automatically retried.

## Human override

A human may record an override with the actor, decision, reason, and scope in
project history. Preserve the original observations and failed dimensions;
an override records an explicit decision and must not rewrite deterministic
facts or fabricate a technical `PASS`. It also does not implicitly grant spend,
provider, replacement, or destructive-action permission. Any canonical QC or
approval transition must use the State Engine with the required revision/hash
checks and recoverable transaction; a report or override note alone is not a
canonical write.
Q2 reviewed dimensions and conditional passes require a named review record,
timestamp, evidence reference, and an injected trusted human verifier. A
`HUMAN` label in a dimension is insufficient by itself. The verifier must also
cover each failed dimension proposed for conditional acceptance.

## Reports, canonical state, and G6

QC summaries, findings, dimension statuses, stop-loss counts, and recommended
routes are derived assessment output. They are not an independent source of
project truth and must not be edited as if they were canonical state. Supporting
evidence may be referenced or recorded through the existing evidence model;
canonical state and its history change only through the State Engine.

I2 G6 remains the final gate: it requires separate technical `PASS` and
creative `APPROVED` states, human `FINAL_QC_APPROVAL`, required delivery assets,
and preceding gates. A QC report, Q3 result, or human override alone does not
satisfy G6. QC does not weaken the Action Guard or turn gate readiness into
authorization to spend.

## Implementation boundary

I4 supplies QC classification, profile-aware applicability, failure ownership,
and stop-loss decisions for later orchestration. Q0 consumes supplied metadata;
external probing remains an adapter boundary. Q3 checks durable delivery
records against required delivery asset IDs read from a revision/hash-matched
State Engine snapshot, while I2 validators
verify local materialized bytes. Check helpers receive the media origin/stage so
that source, generation, and post defects route to the correct owner. Overrides return
audit payloads for future State Engine integration; they do not write events.
No provider calls or architecture changes are introduced.
