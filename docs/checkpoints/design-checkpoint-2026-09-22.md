# Design Checkpoint — 2026-09-22

Status: `DESIGN_IN_PROGRESS`

This checkpoint captures architecture decisions that are stable enough to survive chat/session changes, but are not yet the final v2 specification.

## Stable decisions

1. Runtime current truth will be one canonical machine-readable project state.
2. Runtime history will be append-only events.
3. README/STATUS/TODO/tickets are derived views or execution artifacts, never competing sources of truth.
4. Shots describe intent, requirements and constraints; model names are not part of shot identity.
5. Provider/mode/model selection is resolved at execution time from fresh capability snapshots.
6. Error ownership is explicit: STORY / SOURCE / REFERENCE / PREVIS / GENERATION / POST.
7. Reference errors must not be fixed by repeated video prompting.
8. Technical QC and Creative QC are separate.
9. NEW_PRODUCTION and REVISION are distinct workflows.
10. Non-complete projects require a machine-readable next_action.
11. Asset lifecycle includes EXPECTED → RECEIVED → IMPORTED → REVIEWED → APPROVED.
12. Production method and approval evidence are separate concepts.
13. PixVerse: CLI-first when verified; Web fallback; Canvas remains a Web workspace unless official CLI support is verified.
14. Flow: image + video + revision provider; Whisk is not a required dependency.
15. open-media / Shot Composer is optional previs, not a core dependency.
16. ComfyUI/local video generation remains fallback-only.
17. Paid generation requires human approval by default.
18. Batch review and PRODUCTION_FAST interaction mode are supported.
19. Prompts are execution artifacts derived from structured shot intent/constraints.
20. Every paid generation route needs fallback and stop conditions.

## Not frozen yet

- Final JSON/YAML schema
- Provider adapter interface
- Migration tooling
- Repository runtime layout
- Full legacy replay result

## Freeze rule

Do not create `SPEC_V2_BASELINE_1` until Canonical Model, Router, Validator/Gates, Generation Ticket, QC Contract and Legacy Replay all pass without project-specific exceptions.
