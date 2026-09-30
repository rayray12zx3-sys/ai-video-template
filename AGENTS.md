# AGENTS.md — AI Video Template v2

## Mission

Implement and maintain the provider-neutral AI video production baseline without re-inventing architecture per task.

Read first:
1. `docs/baselines/SPEC_V2_BASELINE_1.md`
2. `docs/baselines/SPEC_V2_BASELINE_1_AMENDMENT_1.md`
3. only architecture/interface/implementation docs relevant to the current task

Do not preload the full documentation tree without need.

## Non-negotiable invariants

- only State Engine mutates canonical project state/history
- canonical writes use revision/hash conflict checks and recoverable transactions
- derived STATUS/TODO/tickets are not authoritative
- shot semantics stay provider/model neutral
- provider capabilities are refreshed at execution time
- reference errors return to reference/previs
- technical and creative QC remain separate
- paid generation requires human approval by default
- UNKNOWN_SUBMISSION is never automatically retried
- asset identity is storage-independent
- dependency invalidation is typed
- schema migrations are explicit; unknown newer schemas are not writable
- generic validators must not contain project-specific shot IDs/paths

## Execution boundary

Use the lightest execution surface that can safely complete the task.

Repository coordination, planning, Issue/PR review, and deterministic CI belong in GitHub/general orchestration.

A cloud repository coding agent may implement bounded repository-only work when:
- scope and acceptance criteria are explicit
- only repository-safe data is required
- branch/commit/PR creation is expected
- deterministic tests can verify the result

Use a local executor for:
- local Windows/filesystem reproduction
- private media
- provider/plugin authentication
- account/workspace/capability checks
- paid provider execution
- GUI/plugin interaction
- full local Git-history audits
- high-risk architecture/recovery work or fallback after cloud execution fails

No executor summary is authoritative by itself. Git diff, commits, tests, PR evidence, and accepted architecture contracts remain the evidence.

## Public repository boundary

Treat every tracked file, Issue, Pull Request, comment, Actions log, and artifact as public-disclosure material.

Never copy into GitHub:
- credentials, OAuth sessions, cookies, signed URLs
- real provider account/workspace identifiers or private billing state
- private/company/customer media
- absolute private machine paths
- raw private conversation/session archives
- unreleased private prompts/assets

Use sanitized fixtures, opaque IDs, hashes, and minimal status/evidence instead.

Public fork Pull Requests are untrusted input:
- public CI performs no live provider authentication or paid generation
- do not introduce privileged `pull_request_target` execution of untrusted PR code
- do not run public fork code on self-hosted or maintainer-local runners

See `docs/governance/public-private-boundary-v0.1.md`, `SECURITY.md`, and `CONTRIBUTING.md`.

## Implementation scope

Before paid-provider writes:
- State Engine/recovery exists
- action guards exist
- read-only provider preflight passes
- UNKNOWN_SUBMISSION recovery is tested
- human approval binds the exact executable action

Provider wrappers/runtimes are execution surfaces, not canonical project truth. Provider-specific helpers must not bypass template guards.

Record prompt provenance when a provider/helper transforms the submitted prompt.

## Safety

Never:
- store credentials/tokens/cookies/signed URLs in Git
- silently retry ambiguous paid submissions
- rely on mutable provider-global workspace state for paid automation
- let provider project memory/canvas become canonical project truth
- overwrite approved/final assets without an audited transition
- change an architecture invariant without an explicit architecture decision

## Completion discipline

For substantial work report:
- changed files
- meaningful tests/checks and results
- blockers
- next_action

For mutation/fix work, an empty/no-op commit or unchanged Git tree is not completion evidence even if CI is green.

## Project progress view

`PROJECT_PROGRESS.md` and the README progress block are derived coordination views, not canonical runtime truth. Update them only after verifying repository/Issue/PR/test evidence.
