# External Processing, Provider Inputs & Materialization Contract v0.1

## External processing policy

Assets uploaded to external providers carry:

```yaml
external_processing:
  policy: ALLOWED | REVIEW_REQUIRED | FORBIDDEN
  allowed_providers: []
```

Default for unclassified private/company/source assets: REVIEW_REQUIRED.

Action Guard blocks upload when policy is FORBIDDEN or required review is unresolved.

## Rights/provenance

Assets may record ownership/license/source/restriction/release evidence.

## Provider-ready derivatives

Critical identity/structure inputs should avoid opaque automatic resizing/compression.

Preferred:
canonical source → deterministic provider-ready derivative → provider upload reference

Hash/register the derivative actually intended for upload.

## Provider upload is not backup

Canonical source/reference assets require a durable non-provider locator.

## Output materialization

Before an output becomes APPROVED/FINAL:
- materialize to project-controlled storage
- record durable locator
- SHA-256
- media metadata
- provider task/asset ID
- lineage

Provider cloud preview alone is insufficient as the sole final asset record.
