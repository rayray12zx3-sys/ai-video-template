# Workflow Lessons Audit v1

This document captures reusable workflow lessons extracted from prior AI-video production work. It intentionally excludes raw conversation/session metadata, private project names, local paths, provider account state, and production assets.

## Interaction mode must be explicit

Discovery work and deadline-driven production require different interaction patterns.

Supported modes should include:
- DISCOVERY
- PRODUCTION
- PRODUCTION_FAST

## next_action is a contract

A non-complete project should always expose an actionable next step with owner, action, target, readiness, and blockers.

## Asset receipt must be tracked

Asset lifecycle should distinguish:
- EXPECTED
- RECEIVED
- IMPORTED
- REVIEWED
- APPROVED

This prevents already-supplied assets from being requested again or treated as missing.

## Generation packages must be executable

A Generation Ticket should contain enough information to execute without extra interpretation:
- required assets
- exact prompt boundaries
- provider mode/settings
- readiness/preflight result
- approval/spend state

## Batch review is required

Single-item upload/review loops can become a throughput bottleneck. Batch QC should report failures, disposition, and the next review batch together when risk allows.

## Active prompt must be unambiguous

There should be one ACTIVE prompt per shot/purpose. Previous prompt versions belong in provenance/history rather than competing active state.

## Provider constraints must be checked before ticket creation

Capability/preflight should precede executable ticket compilation so unsupported provider modes or limits are discovered before submission preparation.

## Error ownership must be formal

Failure routing should distinguish whether the next correction belongs to:
- REFERENCE
- GENERATION
- POST
- STORYBOARD

## State updates should be atomic

One logical production change should produce one auditable state transaction/checkpoint rather than a sequence of loosely coupled status edits.
