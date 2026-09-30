# Asset Locator Contract v0.1

Purpose: let one stable Asset ID refer to media that may live locally, in Drive, in a provider library, or in future storage without changing creative/project semantics.

## Asset identity vs location

`asset_id` is stable project identity.

A locator is only a way to retrieve a physical representation.

```yaml
asset:
  id: REVISION_REFERENCE
  sha256: "..."
  locators: [...]
```

## Locator types

Initial types:

### LOCAL
```yaml
- type: LOCAL
  path: assets/references/revision_reference.png
  scope: project_relative
  availability: AVAILABLE
```

### GOOGLE_DRIVE
```yaml
- type: GOOGLE_DRIVE
  file_id: "..."
  availability: AVAILABLE
```

### PROVIDER_ASSET
```yaml
- type: PROVIDER_ASSET
  provider: pixverse
  asset_id: "..."
  workspace_alias: company
  availability: AVAILABLE
```

### URL
For stable authorized/public HTTP(S) resources when appropriate.

### ARCHIVE
For offline/archive storage that requires restoration before use.

Future locator types may be added without changing Asset identity.

## Preferred locator

An asset may expose multiple equivalent locators.

```yaml
preferred_locator:
  for_execution: LOCAL
  for_review: GOOGLE_DRIVE
```

Preference is contextual and may be derived.

## Integrity

For immutable file representations, SHA-256 is the primary cross-location identity check.

Two locators claiming to represent the same immutable asset but producing different hashes are an integrity ERROR.

## Availability

- AVAILABLE
- OFFLINE
- MISSING
- UNVERIFIED
- ACCESS_DENIED

Availability is environment-dependent and is not the same as approval status.

## Portability

Canonical state should prefer project-relative local paths over machine-specific absolute paths.

Machine-specific mappings belong in local configuration, for example:

```text
project root + assets/references/revision_reference.png
```

not:

```text
D:\user\desktop\...
```

## Security

Do not put signed temporary download URLs, auth tokens or secrets in canonical project state.

## Invariants

- Asset identity is independent of storage provider.
- A missing locator does not delete the logical asset; it changes availability.
- Approved immutable assets require a verifiable hash unless the asset type is inherently non-file/stateful and the schema explicitly allows another integrity method.
