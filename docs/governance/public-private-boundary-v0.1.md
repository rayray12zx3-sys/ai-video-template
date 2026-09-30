# Public / Private Boundary v0.1

## Purpose

This document defines what may enter the public AI Video Template v2 repository and what must stay in private/local execution surfaces.

The goal is to keep one public canonical development repository without making private production state part of repository truth.

## Public repository scope

The public repository may contain:

- provider-neutral source code
- schemas and migration contracts
- deterministic tests
- sanitized fixtures and examples
- architecture/interface/ADR documentation
- repository-safe CI configuration
- contribution and security policies
- sanitized release, validation, and compatibility evidence

Public repository state is appropriate for reproducible software behavior, not private production identity.

## Private/local scope

Keep the following outside the public repository, Issues, Pull Requests, comments, Actions logs, and artifacts:

- credentials, API keys, OAuth tokens/sessions, cookies, signed URLs
- provider account/workspace IDs and private entitlement/billing state
- private/company/customer media
- local-only production assets
- absolute private machine paths
- local profiles containing private identifiers
- provider receipts containing private account/runtime identifiers
- raw conversation or agent-session archives
- personal tool or agent configuration details that are not part of the product contract
- unreleased prompts/scripts/assets that are not intentionally published

A value does not become safe merely because it appears in a Markdown file instead of source code.

## Sanitized public evidence

When public development needs evidence from private execution, publish only the minimum repository-safe representation.

Prefer:

- opaque repository IDs instead of real account/workspace IDs
- hashes instead of private file locations
- capability states instead of private account responses
- sanitized fixtures instead of real production assets
- pass/fail/reason codes instead of raw provider payloads
- redacted paths instead of local absolute paths

Example:

```text
asset_id: asset-042
availability: LOCAL_PRIVATE
content_hash: sha256:...
workspace_binding: VERIFIED
submission_state: COMPLETED
```

Do not publish the corresponding local path, account identifier, token, private URL, or customer asset.

## Execution surfaces

### General assistance + GitHub

May coordinate public repository work, create/review Issues and Pull Requests, inspect CI, and maintain sanitized project state.

It must not copy private execution details into public GitHub surfaces.

### Delegated cloud repository coding

May receive only repository-safe inputs and sanitized fixtures.

It must not receive provider credentials, OAuth sessions, cookies, signed URLs, private/company media, paid-generation authority, or private local filesystem state.

### Local execution

Owns work that requires local Windows state, private media, provider/plugin authentication, workspace/account checks, GUI interaction, paid execution, or full local Git-history inspection.

Results returned to the public repository must be sanitized.

## Public CI trust model

Fork Pull Requests are untrusted.

Public CI:

- runs deterministic repository tests only
- receives no provider secrets
- performs no live provider/auth/paid action
- does not use maintainer-local/self-hosted runners for fork code
- keeps `GITHUB_TOKEN` permissions minimal
- does not execute fork code through privileged `pull_request_target` workflows

## History and hosting metadata

A current-tree review does not cover Git history or hosted repository content. Before publishing a repository or making historical material public, review these separately:

- all Git refs and history
- branches/tags
- Issue and Pull Request bodies/comments
- Actions run logs and artifacts
- releases/assets if any

Removing a value from the current branch does not remove it from Git history or historical hosting metadata. Treat any real secret committed to history as compromised: revoke or rotate it before publishing that history or related artifacts.

## Exceptions

Publishing normally private operational information requires an explicit deliberate decision that:

1. the material is owned/licensed for publication,
2. it contains no secret or third-party confidential data,
3. publication has a concrete product/documentation purpose,
4. the public artifact is the minimum necessary disclosure.

Silence or accidental prior commitment is not approval.

## Architecture invariants

This boundary changes repository governance, not the product's core architecture.

It does not weaken:

- State Engine single-writer semantics
- revision/hash conflict protection
- recovery/rollback guarantees
- provider-neutral canonical state
- paid-generation human approval
- provider/workspace preflight
- `UNKNOWN_SUBMISSION` fail-closed handling
