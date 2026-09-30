# Provider Boundaries v0.3

Updated: 2026-09-23

## GitHub

Canonical control plane for specifications, decisions, machine-readable state/schema, validator/router logic and durable audit history.

## Local SSD

Primary heavy-media/edit/cache location. Assets use stable IDs, locators and hashes rather than machine-specific filenames as identity.

## Google Drive

Optional media/review bridge. Not required for core operation.

## PixVerse

Provider backend priority:
1. `PLUGIN_WRAPPER` — PixVerse Agent Plugin's `pvx` wrapper/private managed runtime when available
2. `RAW_CLI` — official PixVerse CLI fallback
3. Web/manual — fallback/handoff when required

The Plugin is an execution convenience, not canonical state.

Plugin/Canvas project memory, browser bindings and local helper state must not become Source of Truth.

Canonical project state retains provider project IDs, workspace IDs, task/dispatch IDs, approved asset IDs/hashes/locators and prompt/settings provenance required for recovery.

Current Plugin workflow may apply Seedance prompt enhancement. The effective submitted prompt/enhancement artifact must be captured when reproducibility or one-variable retries matter.

Template spend policy overrides provider/plugin convenience defaults. Paid work requires Action Guard and human approval by default.

Canvas edit-version and shared workspace rules from the baseline amendment remain mandatory.

## Codex

Codex is the implementation/executor environment, not media Source of Truth.

Use the user's managed `codex-config` when present rather than cloning its agent definitions into this repository.

Current managed environment has network disabled for ordinary workspace-write shell commands; external provider/network actions should use isolated on-request permission rather than weakening the global default.

## Flow

Image + video + revision provider.
Default subscription route remains WEB_MANUAL.

Gemini API video is a separate optional provider/billing/auth boundary.

## Premiere / After Effects

Primary editorial and targeted post/repair layers.
Adobe generative capabilities have their own credit boundary.

## open-media

Optional previs only. Browser-local persistence is non-canonical.

## ComfyUI/local AI

Fallback/research only.
