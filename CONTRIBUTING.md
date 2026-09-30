# Contributing

Thanks for contributing to AI Video Template v2.

This project is designed for public, reproducible repository work while keeping private production assets, provider credentials, account state, and local execution evidence outside Git.

## Before you start

For a bug fix, test, documentation update, or small refactor, open or reference a bounded GitHub Issue with objective acceptance criteria.

Open an architecture discussion/Issue first when a change would affect:

- canonical State Engine semantics
- schemas or migrations
- provider execution contracts
- paid-action approval or spend controls
- `UNKNOWN_SUBMISSION` handling
- security/trust boundaries
- compatibility guarantees

Do not use a contribution as an implicit architecture rewrite.

## Public-data rule

Everything committed, attached, logged, or posted to this repository must be safe for public disclosure.

Do not include:

- credentials, API keys, OAuth sessions, cookies, or signed URLs
- provider account/workspace identifiers or private billing details
- private/company/customer media
- absolute private machine paths
- raw private conversation/session archives
- unreleased production assets or prompts
- local configuration or execution evidence containing private identifiers

Use sanitized fixtures, hashes, opaque IDs, and repository-safe examples instead.

See `docs/governance/public-private-boundary-v0.1.md`.

## Development

The repository supports Python 3.11+ and uses only the Python standard library for the current core test suite.

Run:

```powershell
python -B -m compileall -q src scripts tests
python -B -m unittest discover -s tests -v
git diff --check
```

If Windows provides the Python launcher but not `python`, use `py -3` instead.

## Provider and paid execution

Repository tests and public CI must remain offline with respect to paid/provider execution.

Do not make a Pull Request depend on:

- PixVerse/Flow/Adobe authentication
- provider credits
- private media
- browser sessions
- local GUI state
- paid generation

Provider-specific live validation belongs in the private/local execution lane and should return only sanitized evidence to the public repository.

## Pull requests

Keep Pull Requests bounded and reviewable.

A PR should:

- state the Issue or goal it addresses
- list in-scope and out-of-scope changes
- include deterministic validation evidence
- avoid unrelated formatting/churn
- preserve architecture invariants unless an explicit ADR/change decision authorizes otherwise
- pass the repository's public-data checks

CI passing is necessary but not sufficient for semantic acceptance.

## Security reports

Do not report security-sensitive details in a public Issue. Follow `SECURITY.md`.
