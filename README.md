# AI Video Template v2

Provider-neutral AI video production template: design baseline, implementation, validation, routing, execution contracts, QC, and provider adapters.

<!-- PROJECT_PROGRESS:START -->
## Development progress

**Current phase:** I8 — Controlled Provider Execution ([#4](https://github.com/rayray12zx3-sys/ai-video-template/issues/4))<br>
**Completed baseline:** I0–I7; I6 4/4 COMPLETE; I7 remains complete<br>
**Current gate:** Gate B BLOCKED — execution contract unresolved ([#5](https://github.com/rayray12zx3-sys/ai-video-template/issues/5))<br>
**Active path:** B1-alt no-spend equivalence investigation ([#13](https://github.com/rayray12zx3-sys/ai-video-template/issues/13)) returned BLOCKED; direct managed CLI is not approved for production<br>
**Current blockers:** nine safety-relevant equivalence UNKNOWN controls; maintained Plugin source/deployment unresolved; B2 spend and receipt evidence remain unresolved<br>
**Next action:** obtain exact-runtime transport/receipt/parameter evidence or establish the maintained Plugin path; do not start live adapter or paid smoke<br>
**Verification:** 15 local offline diagnostics/contracts PASS on Python 3.12.14; 11 final read-only probe processes; these do not establish B1 equivalence or GitHub Actions PASS<br>
**Last verified:** 2026-10-01

```text
✅ I0–I5a  Baseline / validation foundation
⏹ I5b     Closed (not_planned)
✅ I6      Legacy migration & replay  4/4 COMPLETE
   ├─ ✅ I6a  Mapping contract
   ├─ ✅ I6b  Importer + dry-run
   ├─ ✅ I6c  Safe canonical adoption
   └─ ✅ I6d  Replay verification
✅ I7      Hardening / release readiness  COMPLETE
⏳ I8      Controlled provider execution
   ├─ ⛔ Gate B  Workspace / spend / receipt contracts unresolved
   ├─ ⛔ B1-alt Direct managed CLI equivalence not proven (#13)
   ├─ ✅ Output closure  Provider-neutral preparation merged (#6 / PR #9)
   └─ ⏸ Live adapter / paid smoke  Await approved contracts
```

Detailed tree, scope and evidence: [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md)
<!-- PROJECT_PROGRESS:END -->

Current status: `SPEC_V2_BASELINE_1 + Amendments 1-2 / I0-I7 complete / public canonical repository active / GitHub automation foundation active / AUTOMATED_ROUTER_READY`

Phase I0 foundation lives in `src/aivideo`, `schemas`, and `examples/minimal-project`.
Canonical project truth is `project.yaml`; `events.jsonl` is its append-only event history.
`project.yaml` uses JSON syntax (a YAML 1.2 subset), so Python's standard library
can read and write it without a package install. The I1 State Engine owns canonical
writes and recovery. See `docs/implementation/phase-i1-state-engine.md` for the
transaction protocol, crash matrix, API, and Windows durability limits.

## Public development boundary

This repository documents a provider-neutral implementation baseline across phases I0–I7.

Repository-visible content must be safe for public disclosure. Credentials, OAuth sessions, cookies, signed URLs, real provider account/workspace identifiers, private/company/customer media, machine-specific private state, raw private session archives, and unreleased private production material stay outside GitHub.

Private/local provider execution may return only sanitized evidence to the repository. Public pull-request CI remains deterministic and must not perform live authentication, paid generation, or execute untrusted fork code with privileged credentials.

See:
- `SECURITY.md`
- `CONTRIBUTING.md`
- `docs/governance/public-private-boundary-v0.1.md`

## Publication provenance

Public distribution must use a **clean repository initialized from the sanitized current tree with fresh Git history**. Private/archive Git history, historical branches, pull requests, issues, Actions runs, and private-only metadata must not be imported into the public canonical repository.

This is a permanent publication safety invariant, not a temporary migration note. A clean current tree does not make inherited private history safe to publish.

## Local development (Windows, no administrator rights)

Requires Python 3.11+ and Git. From the repository root:

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/capture_environment.py
git diff --check
```

If Windows provides the Python launcher but no `python` command, use
`py -3 -B -m unittest discover -s tests -v` and
`py -3 -B scripts/capture_environment.py` instead.

Tests use only the Python standard library and do not contact or invoke providers.
`scripts/capture_environment.py` prints an allowlisted tool-version snapshot. To keep
it locally, redirect output to `environment-snapshot.local.json`, which Git ignores.
Unavailable tools appear as `null`; they do not need installation for I1.

`examples/minimal-project/project.yaml` is a checked-in sample, not a working
production project. Keep machine paths and capabilities in a project-local
`local-profile.json` based on `examples/local-profile.example.json`. It is ignored
by Git and never enters the canonical project hash. Do not put credentials in it.
`capture_handoff_base` records a remote URL fingerprint, branch, base commit,
state revision, and project hash. State Engine writes configured with `repo`
require this evidence and compare it to the local HEAD and fetched
`origin/<branch>` ref.
The operator must fetch before cross-machine handoff; a local tracking ref
cannot prove live remote freshness.

I2 adds read-only validators, G0–G6 gate evaluation, and action guards. See
`docs/implementation/phase-i2-validation-gates.md` for the fields, evidence
binding, APIs, and action permissions. I3 adds offline Router/Ticket/provider
execution contracts; see `docs/implementation/phase-i3-router-tickets.md`.
I4 adds read-only QC, failure routing, stop-loss and override audit payloads;
see `docs/implementation/phase-i4-qc.md`. I5a adds read-only PixVerse execution-surface discovery;
see `docs/implementation/phase-i5a-pixverse-discovery.md`. None of I0-I5a submits paid work.

Repository CI lives in `.github/workflows/ci.yml` and runs the offline regression suite on pull requests, `main`, manual dispatch, and a low-frequency drift check. Public CI is intentionally provider-offline and uses read-only repository permissions.

Development routing is intentionally tool-neutral:
- repository coordination/review stays in GitHub/general orchestration
- bounded repository-only implementation may use a cloud coding agent
- private media, local Windows state, provider authentication/account state, paid execution, and high-risk local validation stay in the local execution lane

CI passing is necessary but not sufficient for semantic acceptance. Auto-merge remains disabled during initial public operation.

Start here:

1. `AGENTS.md` — execution boundaries and implementation rules
2. `docs/baselines/SPEC_V2_BASELINE_1.md` — frozen architecture baseline
3. `docs/checkpoints/post-baseline-readiness-audit-2026-09-22.md`
4. `SECURITY.md`
5. `CONTRIBUTING.md`
6. `docs/governance/public-private-boundary-v0.1.md`

Large production media, private session archives, credentials, OAuth tokens, and company-sensitive assets are intentionally excluded from Git.


## License

Licensed under the **Apache License 2.0**. See [LICENSE](LICENSE).

This repository currently does not bundle third-party code or assets that require a separate NOTICE file. Third-party components introduced in the future retain their own license and attribution requirements.
