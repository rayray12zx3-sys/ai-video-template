# Provider Capability Schema v0.1

Purpose: normalize provider capabilities enough for routing while keeping provider-specific controls out of canonical shot semantics.

## Normalized snapshot

```yaml
snapshot:
  id: PIXVERSE-20260922-001
  provider: pixverse
  captured_at: 2026-09-22T10:40:00+08:00
  expires_at: 2026-09-23T10:40:00+08:00

  execution_surfaces:
    - CLI
    - WEB

  account:
    authenticated: true
    workspace_alias: company
    subscription_active: true
    credits_available: 1000
    concurrency_slots:
      total: 2
      available: 1

  capabilities:
    - operation: IMAGE_TO_VIDEO
      models:
        - id: v6
          durations_seconds: [5, 8]
          resolutions: [720p, 1080p]
          audio: false
          references:
            first_frame: true
            last_frame: false
            multi_reference: false

  native:
    ref: evidence/provider_capabilities/pixverse-native-20260922.json
```

## Normalized operation vocabulary

Initial cross-provider operations:

- TEXT_TO_IMAGE
- IMAGE_EDIT
- TEXT_TO_VIDEO
- IMAGE_TO_VIDEO
- FIRST_LAST_VIDEO
- REFERENCE_VIDEO
- MOTION_CONTROL
- VIDEO_MODIFY
- VIDEO_EXTEND
- UPSCALE
- GENERATIVE_INSERT
- AUDIO_GENERATE

Providers may support only a subset.

## Common capability dimensions

Where known:
- duration range/options
- aspect ratios
- resolutions
- fps
- native audio
- first frame
- last frame
- multi-reference
- image reference count
- video reference count
- audio reference count
- motion source support
- seed support
- deterministic/reproducibility hints
- concurrency/account limits
- estimated cost unit

Unknown values remain UNKNOWN; do not invent them.

## Native payload

Provider-specific controls that do not map cleanly to normalized fields stay under `native` evidence or adapter-owned fields.

Canonical Shot schema MUST NOT absorb provider-native settings merely because one provider exposes them.

## Freshness

A project/provider profile defines a maximum snapshot age. Paid execution against an expired snapshot is blocked until refresh.

## Router behavior

1. Filter routes by hard normalized requirements.
2. Read provider-native controls only inside the adapter when compiling a ticket.
3. Preserve the exact snapshot ID used by the ticket.
4. If an adapter cannot prove a required capability, treat it as unsupported/unknown rather than assuming support.

## Invariants

- Snapshot is evidence, not canonical creative truth.
- Provider adapters translate native capabilities into normalized operations.
- New provider features should normally require adapter/schema extension, not Shot schema changes.
