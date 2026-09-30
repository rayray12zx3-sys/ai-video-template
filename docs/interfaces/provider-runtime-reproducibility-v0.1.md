# Provider Runtime Reproducibility Policy v0.1

Each provider execution binds a runtime snapshot where applicable:
- execution backend/surface
- Plugin version
- private/raw PixVerse CLI version
- region
- workspace ID
- technical capability snapshot
- account entitlement snapshot
- Canvas schema/edit_version

## No casual mid-project updates

Do not update Plugin/CLI merely because a newer version exists during active production.

If update is necessary:
- record runtime-change event
- refresh capability snapshots
- invalidate/recompile affected unexecuted tickets

## Split capability evidence

Separate:
1. technical capability snapshot — models/operations/parameter ranges
2. account entitlement snapshot — auth/membership/credits/slots
3. Canvas live schema — node routes/edit_version when used

## Explicit parameters

Tickets should set important model/mode/quality/duration/aspect/audio/multi-shot controls explicitly where supported.

## Prompt transform policy

```yaml
prompt_transform:
  policy: EXACT | ALLOW_OPTIMIZATION | REQUIRED_PROVIDER_TRANSFORM
```

When optimization occurs, preserve source and effective/submitted prompt plus version/provenance where available.
