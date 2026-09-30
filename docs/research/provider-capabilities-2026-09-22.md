# Provider Capability Snapshot — Research Notes — 2026-09-22

This file records planning assumptions discovered during September 2026 research. Runtime execution must still refresh live capabilities before paid work.

## PixVerse

Current official findings:
- Official CLI exists and is intended for terminal/agent workflows.
- Install globally with `npm install -g pixverse` or run with `npx pixverse`.
- Current CLI requirement is Node.js >= 22.12.
- CLI uses the same PixVerse subscription/credits as the website.
- CLI and Web/App sessions are independent; CLI authentication should not sign the Web session out.
- OAuth device-flow token is stored locally and is currently documented as valid for 30 days.
- Shared accounts require workspace/credits/slot preflight.
- Official CLI exposes video/reference/transition/motion-control/modify/extend/upscale plus image/audio/template/account/task/asset/workspace operations.
- Official CLI now also exposes Canvas project, graph, node, patch, dispatch, reconcile and version operations.
- `capabilities create` expands installed CLI model/mode constraints.
- Canvas node schemas and route mappings should be queried live with Canvas capability/schema commands.
- Different models expose different modes, reference limits and duration/resolution controls.

Architecture consequence:
PixVerse is a platform with Web, direct CLI generation and CLI-accessible Canvas execution. The adapter must discover live capabilities instead of hard-coding models.

## Flow / Google

Current official findings:
- Flow covers image generation/editing as well as video generation/editing workflows.
- First/last frames, references/ingredients, extend and editing routes are relevant.
- Whisk is not required as a formal pipeline dependency.
- Official desktop access is through a Chromium-based browser for the full experience.
- Google AI Plus/Pro/Ultra or qualifying Workspace access governs the Flow end-user product.
- Flow subscription access does not equal Gemini API paid-tier access.
- Google also provides a programmatic video generation/editing path through Gemini Omni via the Gemini API; this is a separate provider/billing surface.

Architecture consequence:
Flow remains a manual Web route in the default template. Gemini API video may later be added as a separate automated adapter; do not silently treat it as Flow automation.

## Premiere Pro / After Effects

- Premiere 26.5 introduced Generative Media in the timeline; 26.5.1 includes updated generation/credit transparency.
- Premiere and After Effects are installed/updated through Adobe Creative Cloud Desktop or organization-managed deployment.
- Premiere update policy should avoid mid-project upgrades unless needed; pin/record the production version in project environment metadata.
- After Effects remains the targeted composite/repair/motion-graphics layer.

## open-media / Shot Composer

Official repository path:
- Node.js 18+
- `npm install`
- `npm run dev`
- `npm run build` for a static `dist/`
- local MCP server: `cd mcp && npm install && npm start`

Persistence is browser localStorage. Treat the tool as optional previs and export evidence back to the project rather than using it as a source of truth.

## Codex

Official project integration points relevant to this repo:
- root `AGENTS.md` for repository instructions
- `.agents/skills` for repo-scoped skills
- optional trusted-repo `.codex/config.toml` for project-local Codex configuration
- local/remote MCP server support through Codex configuration
- Git checkpoints before/after implementation tasks

## Runtime policy

Never rely on this research note alone for a paid generation command. Refresh provider/account capabilities and bind the executable ticket to the resulting snapshot.
