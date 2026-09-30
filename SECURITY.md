# Security Policy

## Supported code

Security reports should target the current `main` branch or the latest published release. Historical branches and abandoned experimental branches are not maintained unless a report also affects current code.

## Report a vulnerability privately

Do **not** disclose a vulnerability, credential, token, cookie, signed URL, private asset, account identifier, workspace identifier, or customer/company information in a public Issue, Pull Request, discussion, commit, or Actions log.

Use GitHub Private Vulnerability Reporting when it is enabled.

If private vulnerability reporting is temporarily unavailable, open only a minimal public Issue stating that you need a private security contact channel. Do not include exploit details or sensitive values in that Issue.

## Sensitive-data boundary

This repository must never contain:

- API keys, OAuth tokens or sessions
- cookies, signed URLs, private download links, or provider credentials
- private/company/customer media
- real billing, entitlement, account, or workspace identifiers unless intentionally anonymized
- machine-specific private paths or local execution state
- raw private conversation/session archives
- unreleased production prompts or assets that are not intentionally licensed for publication

If any secret is found in Git history, treat it as compromised: revoke or rotate it first, then remove or rewrite the affected history as appropriate.

## Public CI trust model

Pull requests from forks are untrusted input.

- Public PR CI must not receive provider credentials or paid-generation authority.
- Public PR CI must not execute live provider/authentication flows.
- Public fork PRs must not run on self-hosted or maintainer-local runners.
- Do not use privileged `pull_request_target` execution to check out and run untrusted PR code.
- GitHub Actions permissions should remain read-only unless a narrowly scoped job proves it needs more.

## Project safety invariants

A security change must not silently weaken:

- State Engine single-writer behavior
- revision/hash conflict checks
- recovery semantics
- paid-generation human approval
- provider/workspace binding
- `UNKNOWN_SUBMISSION` fail-closed behavior

Security fixes that affect these invariants require explicit review and regression coverage.
