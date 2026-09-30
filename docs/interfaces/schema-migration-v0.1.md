# Schema Migration Contract v0.1

## Purpose

Allow the template/project schema to evolve without silently corrupting older projects.

## Version fields

Canonical state includes:
- schema_version
- template_version

Event records include:
- event_schema_version

Provider snapshots/tickets may have their own document versions.

## Compatibility policy

### Same supported version
Read/write allowed.

### Older supported version
Read-only inspection is allowed.
Writes require an explicit migration to the current writable version.

### Newer unknown version
Refuse write.
Return `UNSUPPORTED_NEWER_SCHEMA`.

Never attempt best-effort downgrade.

## Migration chain

Migrations are explicit adjacent transforms:

```text
2.0 -> 2.1
2.1 -> 2.2
```

Do not maintain many ad-hoc direct jumps unless generated/tested from the same chain.

## Migration properties

Each migration must be:
- deterministic
- testable
- side-effect free until commit
- information-preserving unless an ADR explicitly authorizes loss
- able to report warnings/manual actions

## Migration procedure

1. Validate source document under its source schema.
2. Create a Git/checkpoint or backup copy.
3. Run migration in dry-run.
4. Produce migration report:
   - source version
   - target version
   - fields added/changed
   - warnings
   - unresolved items
5. Validate migrated output under target schema.
6. Commit through State Engine as a MIGRATION transaction/event.
7. Preserve the report as evidence.

## Event history

Do not rewrite historical event semantics merely to make them look current.

Readers may normalize old event versions at read time, or explicit event-history migration may be performed when required.

## Provider/native evidence

Historical provider receipts/capability snapshots remain immutable even if current normalized schemas evolve. New readers use versioned adapters.

## Tests

Every schema migration requires:
- source fixture
- expected target fixture
- round-trip/invariant tests where applicable
- malformed-input test
- unknown-newer-version refusal test

## Invariants

- no implicit migration on ordinary read
- no write to unknown newer schema
- no silent field dropping
- every migration is auditable
