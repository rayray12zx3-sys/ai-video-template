# I8 Gate B exact-runtime evidence — 2026-10-01

**RUNTIME_EVIDENCE_PARTIAL — CRITICAL UNKNOWNS REMAIN**

Scope: [Issue #15](https://github.com/rayray12zx3-sys/ai-video-template/issues/15), evidence acquisition only. The ordinary T2V CLI transport can now be traced through the installed bundle, but strict parameter preservation and trusted workspace/task/asset/charged-refunded linkage are not established. This report does not approve direct CLI production execution, live adapter coding or paid smoke. Gate B remains BLOCKED; #5 Decisions A/B/C and the provider-enforced-only spend guard remain unchanged.

## E0 — Baseline and runtime seal

- Fresh canonical repository clone: `rayray12zx3-sys/ai-video-template`, main `ef3353ea5dcc613394d1b27a5fcdbb0de8376628`; clean at intake. The originally open archive-repository worktree was preserved.
- Installed Plugin **1.3.2**, online managed/private CLI **1.4.5**, Node **24.19.0**. Version was confirmed through the installed `scripts/pvx` wrapper. No global PixVerse installation was used.
- Python **3.13.14** ran the local evidence/contract diagnostics; Python **3.12.14** launched the installed wrapper. These are distinct execution tools, not the required repository CI lanes.
- Installed HTTP dependency: **Ky 2.1.0**, external ESM import from this managed CLI's own dependency tree.
- Final wrapper auth-status read: exit 0, `authenticated=true`. All nine final allowlisted read processes exited 0. Account and usage reads were usable. The technical active selector was held in memory; **the intended paid workspace remains unconfirmed**.
- Selected runtime/Plugin hashes and all **3,434 dependency files** were unchanged across the read-only probe, sample follow-up and final seal. A dependency-tree digest is SHA-256 over sorted `relative-path + NUL + leaf-SHA256-hex + LF` entries. It is specific to this digest algorithm; a differently constructed earlier composite digest is not directly comparable.

| Artifact, relative to installed component | SHA-256 |
| --- | --- |
| Node executable | `3602f2bb1a10f2cbab4c36886218a33c1ab3db87290e73b033c46c77147d0237` |
| Plugin metadata | `b4bcb368fb1c2ddb9521c002b1b985cfda0276e0e311dea549e3e61b446ff7ac` |
| Plugin `scripts/pvx` | `da03e3edbe551d6ac558243bcf5dd12e9ed1c7adec0938a716db889b733532af` |
| Plugin `pvx/pixverse.py` | `633a5b94d51376aa797d4648f49aae9d8a019afc45d2040316f70e3597c3a4b1` |
| Plugin `pvx/billing.py` | `d3fe726a4d1ca01c8fb8385941ba70b8c4f9818e60f9f70a01a214d6c17ea76c` |
| Plugin `pvx/shell.py` | `411bd4fbab4517ed6991db7066989c6e0d3992714933308582de2cb2ce2ad61b` |
| Plugin `pvx/cli.py` | `3334294a996137502f7dd1f90ebb812d8353db737e7b5d644d854e436561665d` |
| Plugin `pvx/compatibility.py` | `9d8f10ac8d87369e8bf17c6d3a5141e178abc3c5d92faeb86841edfcba5db93d` |
| CLI `package.json` | `3d74808e318d5db46e15d1c49c6b514a33d43c3a3cf0bca6afc031b8125ba2c8` |
| CLI `dist/index.js` | `663fcad688ec0ea2cefe804f9eb78693f9a3647ed6c0f39303e52c0c9af39fe3` |
| CLI `dist/capabilities.json` | `20f571777d55aace4bf2d7befc78039e97e9b2fffa7013626ce6c71a712a4d51` |
| Managed dependency tree | `6ae7a382e3437e59892726be2a9634fd7c6e8bbe08d9fb4d9291da35bbc439b1` |
| Ky `distribution/core/Ky.js` | `b02f8fda748a2a213bb5f1faccb8831d6c23688b58024c748d17d3c3c7ac8cba` |
| Ky `distribution/utils/normalize.js` | `bedfb35f8fa9316e37157d259d6266f97ac3bb3102af7bf8901bf8174daa89cd` |
| Ky `distribution/utils/timeout.js` | `c0f31d5adc6d4ff35aa5dcbd8584bbdb3ee465662f904c42f8b3b00885a1d19f` |
| Ky `package.json` | `5e1e3cf4e045dc8680122d1cbcb9f11c3e520573d9b51428c57f366da746d422` |

## Evidence references and inspection method

All CLI references below bind to the E0 entrypoint/capability/dependency hashes. Bundle offsets are zero-based JavaScript UTF-16 character offsets in the original installed `dist/index.js`, not offsets in transformed output. No vendor bundle/cache was copied into this repository or report.

The obfuscated string decoder/table/rotation were inspected in place, isolated in a capability-restricted VM with a finite timeout, and used to resolve property names in memory. The full CLI entrypoint and paid callbacks were never executed. Inspection followed actual call expressions and dependency policy; names or help descriptions alone were not treated as execution proof. Results remain scoped to the inspected ordinary T2V path, not every model or provider operation.

- **T1**: CLI `Fl@30046`, `br@32489`, `Rt@36028`, `N@35665`, `vt@665220`, `Nn@665784`; ordinary video callback `@924800–931200`. T2V selects `Nn -> vt -> N -> Rt -> br/Fl -> ky.post`.
- **T2**: installed Ky `utils/normalize.js:3–21`, `core/Ky.js:379–447`, `utils/timeout.js:3–20`, and success-body timeout handling in `core/Ky.js:518–565`.
- **T3**: CLI `ae@134411`, `K@132483`, `sm@131431`, `ri@113620`, `Te@139840`.
- **P1**: CLI `Dt@328899`, `Ae@330938`, `Vi@331551`, ordinary video callback `@924800–931200`, `Gu@664744`, `Ri@51137`; installed `capabilities.json` ordinary video flags/parameter contracts.
- **W1**: CLI `ms@28466`, `he@27353`, `ei@28751`, `Fl@30046`, `vs@38050`; account-info callback `@68000–75000` vicinity.
- **R1**: CLI `ae@134411`, `Pr@145329`, `dm@148379`, `ri@113620`; detail reads use `ke` / `video/list/detail`.
- **Q1**: installed Plugin `pvx/pixverse.py:_run_queue`, especially lines 1917–1928, 1933–2030; `shell.py:run_captured`. Helpers remain ambient unless separately bound.
- **L1**: nine allowlisted wrapper reads described in E3, sanitized field/type/boolean summaries only.
- **D1**: final 16 isolated installed-dependency/pure-function diagnostics and five repository contract tests described in E5.
- **PUB1 — PUBLIC_DOC_ONLY**: current official [CLI README](https://github.com/PixVerseAI/cli/blob/main/README.md), [manifest](https://github.com/PixVerseAI/cli/blob/main/capabilities.json) and [changelog](https://github.com/PixVerseAI/cli/blob/main/CHANGELOG.md), inspected as secondary context. The changelog describes no-wait parameter output, but that wording does not establish provider-origin resolution; P1/R1 establish its local provenance. No matching exact-runtime trusted receipt/refund contract was established from these pages. Public mutable main is not the sealed installed 1.4.5 runtime and does not promote any UNKNOWN target.

## E1 — Transport, timeout and repeat submission

`Fl` constructs a Ky client with a **30,000 ms** timeout and retry limit **2**, status codes **408/429/500/502/503**. It does not override Ky's retry methods, enable timeout retries, or register an after-response forced-retry hook. Ky's default methods exclude **POST**; its retry method check rejects ordinary POST retry before the status/network/timeout checks. Thus the inspected ordinary T2V client path does **not automatically retry its create POST** for 429/5xx/network errors/timeouts. Eligible reads still have retries. This resolves the narrow client/library no-retry UNKNOWN; it is not provider-side deduplication or whole-Plugin execution equivalence.

`Rt` awaits a POST and then response JSON. Request and successful response-body timeouts abort/throw locally. An abort is not proof that the provider did not accept the request. No inspected error path supplies a trustworthy acceptance boundary or recovers a lost task ID from an accepted-but-unread response. Caller timeout/nonzero exit without a durable ID must therefore remain `UNKNOWN_SUBMISSION`.

`ae` may emit successful task identities and still set exit code **5** when `fail_count > 0`. Missing returned identity also exits **5**. Polling timeout uses exit **2** and includes the known video identity in error text; generic JSON errors are not a guaranteed structured task-ID envelope. Inspect payloads even on nonzero exit; never infer no submission from exit code alone.

The Plugin queue has additional resubmission behavior: a classified rejected reference input can be localized and submitted once with a new key; a concurrency branch leaves the item pending and can invoke create in a later queue pass. Its timeout branch records unresolved and does not immediately resubmit. These different branches do not establish the required global exactly-one-create invariant or server acceptance knowledge. In particular, the reference branch's comment claiming safe pre-submission rejection is not independent provider proof.

Trace is attached to requests; `Rt` prefers a response trace header and otherwise falls back to its local trace. `vt` exports its own local trace in the create result. The command also passes `idempotency_key` in the request body. **Server deduplication, request-to-receipt trace identity and refund behavior remain UNKNOWN**; bundled help promises do not prove them.

## E2 — Requested versus submitted versus provider-observed parameters

- `Dt` warns and chooses a supported duration; `Ae` warns and falls back to supported quality; `Vi` can adjust framing, with rejection only for some unsupported combinations. Unsupported audio/multi-shot/off-peak controls may be ignored or changed. The installed ordinary-video command contract exposes no global fail-on-adjust/strict flag.
- The video callback builds a local parameter object, invokes T2V, and passes that **local object** to `ae`. Its `--no-wait` JSON `params` therefore represents caller-side normalized parameters, **not provider-resolved/effective parameters**.
- Additional layers can add submitted fields after that object is built: `Gu` adds model-specific controls for certain models; `Ri` can add `model_name_default`. These transformations use new objects, so the returned local `params` need not enumerate every wire field. This does not claim those model-specific additions occur for ordinary v6.
- Poll/detail output can contain provider-origin model/prompt/duration/output dimensions, but no suitable existing video sample verified those fields here. Neither authoritative pre-submit resolved parameters nor complete prompt-transformation provenance is proven.
- Any future binding must distinguish raw requested, locally normalized, final serialized and independently provider-observed parameters. A local echo cannot authorize billing exposure or certify prompt preservation.

## E3 — Existing samples and receipt linkage

Final wrapper reads: auth status twice; workspace status three times; explicit-selector account info once; explicit-selector generated video asset list once; explicit-selector usage twice. **Nine processes**, all exit 0. Query pagination was bounded to page 1 / limit 5. Offline `--version` and the two list/usage help calls are separate from these live reads.

Generated-video list had no usable item. Inspected usage records contained the field names `create_time`, `video_id`, `credits`, `acquired_type`, `video_source`, `source`, `platform`, `type`, `sub_type`, but none provided a positive video identity suitable for a task/asset follow-up. No task status/asset info/download was invoked. No billing values, IDs, raw private payloads or signed URLs were retained or published.

Result: **NO_SAFE_EXISTING_SAMPLE** for a linked intended-workspace video receipt within this bounded inventory. This is not proof that the account has no historical assets or that other pages/workspaces have no samples. Intended paid workspace was not confirmed; no workspace switch or sample generation was used to resolve that limit.

**Correction to earlier account evidence:** on explicit-selector account-info reads, the output `workspace.workspaceId` comes from `he()` / caller context. Its equality to the supplied selector is not an independently provider-observed receipt/workspace binding. Provider-origin account/credits data and selected workspace metadata must be distinguished from this echoed selector. The earlier #13 successful read remains valid as a successful structured lookup; its workspace echo cannot satisfy #5 Decision C.

| Field/path | Exact-runtime provenance | Missing production linkage |
| --- | --- | --- |
| Create `video_id(s)` / `success_ids` | Read from successful provider response in `ae` | No existing trusted task sample; no independent workspace/trace lineage |
| Create `params` | Caller-side normalized object | Provider-observed/effective params and all final wire fields |
| `trace_id` | Local/generated or explicitly caller-selected in create wrapper | Independent correlation to provider task/usage |
| Create `cost_credits` | Optional positive numeric response field forwarded by `ae` | Quote versus actual charge, final refund and per-task workspace lineage |
| Detail prompt/model/duration/size/created_at | Fields read from detail response, then formatted by `Pr`/`dm` | No safe real video sample; independent completion time/workspace/refund |
| Usage `video_id` / `credits` / `create_time` | Provider-query field shape observed | No positive task ID in inspected records; no verified charge/refund semantics |
| Account `workspace.workspaceId` | Caller selector in explicit mode | Independent observed task/asset/receipt workspace |

## E4 — Required evidence matrix

Every row binds to **E0: Plugin 1.3.2 / managed CLI 1.4.5 / Ky 2.1.0 and the hashes above**. Classification records the scoped fact acquired, not a production PASS. `Provider-origin` describes independent provider evidence acquired in this run, not merely a source-code expectation. `WS` means independent workspace observation; `B/P` means independently observed billing/resolved parameters. No row is sufficient for whole-production acceptance.

| # | Target and scoped result | Classification | evidence_ref | Provider-origin | WS | B/P | Production sufficient |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Paid HTTP retry: ordinary T2V uses Ky POST with automatic method retries excluded | PROVEN_EXACT_RUNTIME | T1/T2, D1 | No; static source | No | No | No; scoped client transport only |
| 2 | One invocation versus hidden repetition: CLI POST not retried; Plugin queue has separate resubmission branches | PROVEN_EXACT_RUNTIME | T1/T2/Q1 | No; static source | No | No | No; whole-path exactly-once/dedup unproven |
| 3 | Timeout before/after acceptance: local timeout/abort known, provider acceptance boundary unknown | UNKNOWN | T2/T3/Q1 | No acceptance sample | No | No | No |
| 4 | Nonzero exit with task ID: partial result may emit IDs and exit 5; polling timeout may include known ID in text | PROVEN_EXACT_RUNTIME | T3, D1 | No; isolated fixture | No | No | No; durable trusted correlation missing |
| 5 | Strict versus adjust: ordinary video normalizers can adjust; strict option not exposed by installed contract | PROVEN_EXACT_RUNTIME | P1, D1 | No; local control flow | No | No | No; reject-on-drift guarantee absent |
| 6 | Resolved submitted params: no-wait params are local; full provider-effective params unproven | UNKNOWN | P1/R1 | No effective-param sample | No | No | No |
| 7 | Trustworthy task identity linkage | UNKNOWN | R1/L1 | No safe linked task | No | No | No |
| 8 | Trustworthy asset identity/linkage | UNKNOWN | R1/L1 | Empty bounded video inventory | No | No | No |
| 9 | Independent task/asset/receipt workspace | UNKNOWN | W1/R1/L1 | Account echo is caller-supplied | No | No | No |
| 10 | Charged/refunded credits and task linkage | UNKNOWN | R1/L1 | Yes for usage field shape only | No | No linked charge/refund | No |
| 11 | Sufficient timestamps/terminal-state reconciliation | UNKNOWN | T3/R1/L1 | Usage timestamp shape only | No | No | No; completion/task linkage missing |

Counts: **4 PROVEN_EXACT_RUNTIME**, **7 UNKNOWN** targets. No target reaches PROVEN_EXISTING_SAMPLE, PUBLIC_DOC_ONLY or LOCAL_REPRODUCIBLE_CONTROL as its overall classification. Usage field shape is existing-sample evidence for that subclaim only; D1 local controls do not promote provider behavior.

## E5 — Sanity checks, limits and zero-spend proof

- **16 PASS / 0 failures**, exit 0, Node 24.19.0: installed Ky with injected offline fetch; isolated exact `ae`, `Dt`, `Ae`, `Gu` functions with sanitized fixtures. Cases cover POST 408/429/500/502/503/504/network/timeout (one mock fetch each), GET 429 (three mock fetches), local-parameter echo versus provider data, nonzero partial identity, missing identity, zero-cost omission, duration/quality adjustment and additional submitted fields. Real fetch attempts **0**. These prove inspected dependency/function behavior under fixtures, not full CLI/provider acceptance or server billing/deduplication.
- **5 PASS / 0 failures / 0 errors**, exit 0, Python 3.13.14: existing I3 no-retry/reconciliation workspace and receipt-verifier tests, I2 provider-enforced cap/workspace test, I8 workspace-mismatch and missing-trusted-receipt tests. Real `subprocess.run/call/Popen`, `socket.create_connection` and `socket.socket.connect` were forbidden; all five attempted-call counters **0**. These are repository fail-closed controls, not a live adapter implementation.
- Initial sandbox Bash/temp-directory attempts failed with WinError 5; the same scoped commands/tests succeeded through the approved Windows route. One initial diagnostic expectation incorrectly assumed missing-ID exit 4; inspecting the arithmetic and fixture result established exit 5 and the diagnostic was corrected. A helper import attempt failed before any provider call. Those attempts are not counted as PASS. No product/Plugin/runtime changes were made to repair diagnostics.
- No full CI replay was needed for this evidence-only/docs work. Local diagnostics are **not GitHub Actions PASS**; no live provider acceptance/fault injection was run.

For all enumerated operations in **this Issue #15 investigation**:

```text
create = 0
upload = 0
generate = 0
dispatch = 0
workspace switch = 0
spend = 0
```

The proof is the read-only command allowlist, no executed full paid callback, forbidden real network/process APIs in contract tests, injected offline fetch in dependency diagnostics, and unchanged runtime/source seals. `spend=0` counts credit-consuming invocations by this investigation; it is not a shared-account billing audit or a claim about unrelated account activity. Active workspace was unchanged across the before/after live probe. No login/logout/bootstrap/reset, cache patch, guard/schema change or production adapter was performed.

## Consequences for #13 and #5

- #13's narrow ordinary-T2V HTTP no-retry UNKNOWN is resolved by T1/T2. Its row 18 whole-surface safety classification remains UNKNOWN: Plugin resubmission, accepted-but-unread outcomes and trusted reconciliation remain unresolved. No execution-surface equivalence is approved.
- Row 9 now has concrete adjustment control-flow evidence and local-echo provenance; strict fail-on-adjust/provider-effective billing controls remain unproven. Rows 11/13–16 retain unproven independent trace/task/asset/workspace/charge-refund linkage. Do not reduce the nine safety-relevant equivalence UNKNOWN count merely because a narrower source fact was acquired.
- #5 Decision A retains the maintained Plugin target; #12 remains blocked on maintainable source/deployment. Decision B/B2 retains provider-enforced-only authorization. Decision C requires independently provider-origin workspace and linked receipt evidence; caller workspace/parameter echoes do not qualify.
- Next action: obtain maintained vendor-supported contracts for strict/final parameter preservation and independently scoped receipt/charge-refund linkage, or inspect a confirmed-intended-workspace existing safe sample through a separately bounded read-only query. No new sample generation, live adapter or paid smoke before Gate B PASS.
