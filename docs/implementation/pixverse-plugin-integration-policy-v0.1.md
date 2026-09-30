# PixVerse Plugin Integration Policy v0.1

## Backend priority

The PixVerse provider adapter supports two execution backends:

1. `PLUGIN_WRAPPER` — preferred when a compatible managed wrapper is present and healthy
2. `RAW_CLI` — fallback using the official PixVerse CLI when the wrapper is unavailable

Neither backend changes canonical shot/project semantics.

## Discovery

At runtime, detect whether the supported plugin/skills and wrapper are available.

Do not hard-code absolute installation paths or machine-specific runtime locations into Git.

## Setup/readiness

Relevant read-only readiness checks may include:
- setup/doctor status
- runtime version/compatibility
- authentication status
- account/workspace readiness
- available capacity
- live Canvas capability/schema when Canvas is used

The repository records only sanitized capability state. Credentials, raw account payloads, private identifiers, and local runtime files stay outside Git.

## Spend guard

Template Action Guard is authoritative.

Before paid work:
- ticket approved
- expected workspace binding verified locally
- provider ready
- quote/cost captured when possible
- candidate/project budget passes
- human approval present

Provider convenience/automatic-generation settings MUST NOT override this contract.

## Prompt provenance

For every generated candidate preserve repository-safe provenance for:
- canonical/source prompt
- compiled provider prompt
- enhanced/submitted prompt when the provider/model modifies it
- model/mode
- integration/runtime version where useful
- capability snapshot ID
- sanitized provider task/dispatch reference when safe to publish

Private provider/account identifiers remain outside public repository state.

## Canvas

Canvas helpers are an execution implementation, not canonical project truth.

Canonical state remains outside provider/plugin memory.

Provider state may be referenced through sanitized IDs/evidence where publication is safe and necessary. Concurrency/version rules from the architecture still apply.

## Failure/recovery

Convenience workflows do not relax:
- UNKNOWN_SUBMISSION
- no automatic ambiguous paid retry
- workspace checks
- edit/version conflict handling
- durable provider receipt requirements
- State Engine single-writer rule

## Portability

A project created on a machine with a provider wrapper must remain inspectable and editable on a machine without it.

No canonical schema field may require an opaque machine-local provider file to interpret the project.
