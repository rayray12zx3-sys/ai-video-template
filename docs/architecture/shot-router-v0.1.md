# Shot Router v0.1

## Router responsibility

The router answers, in order:

1. Is new media required?
2. If something failed, who owns the error?
3. Is previs needed?
4. Which production method fits?
5. Which provider/mode fits current capabilities and constraints?

The router does not write final prompts, approve spend or permanently bind a model.

## Media-first routing

Before AI:
- existing source → SOURCE_MEDIA
- editorial-only → PREMIERE
- comp/mask/motion graphics → AFTER_EFFECTS
- static sufficient → STATIC
- hold/derived edit → DERIVED
- no new visual → NO_NEW_MEDIA

Only then consider AI_IMAGE / AI_VIDEO.

## Error ownership

- STORY → storyboard/spec
- SOURCE → source capture
- REFERENCE → identity/costume/environment/composition
- PREVIS → geometry/blocking/camera
- GENERATION → motion/expression/temporal behavior
- POST → timing/local repair/composite

Reference errors must not be repaired by repeated video prompting.

## Previs

Possible requirements:
- NONE
- STATIC_3D
- MOTION_3D

High-risk triggers include complex spatial relations, low/high angles, OTS, scale relationships, fisheye, camera+subject motion and multi-character blocking.

open-media / Shot Composer is an optional tool, not part of the schema.

## Video-route patterns

- identity high + motion low → reference-first I2V
- identity high + motion high → reference/motion-control
- important start/end states → first/last or transition
- multiple critical references → reference mode
- existing video, local change → modify/V2V/post
- only extension needed → extend
- motion unnecessary → static/AE first
- real UI → source media, not AI

## Provider abstraction

PixVerse candidate modes:
- I2V
- Reference
- Transition
- Motion Control
- Modify
- Extend

Flow candidate modes:
- Image/reference creation
- I2V
- First/Last
- Reference
- V2V edit
- Extend

Premiere Generative is a narrow optional route for timeline-context inserts, gaps, short fixes and SFX.

Models are selected from live capability snapshots. Shot schema does not hard-code V6 / Seedance / Veo / Kling etc.

## Hard constraints vs scores

Candidate routes may be scored for capability fit, identity, motion, continuity, editability, reproducibility, cost, risk and manual overhead.

Hard constraints disqualify a route rather than merely reducing score.

## Preflight

Paid generation requires fresh provider capability evidence and account/resource checks.

For PixVerse check:
- auth
- workspace
- subscription
- credits
- slots
- capability snapshot

Capacity shortage is WAIT, not a prompt/generation failure.

## Fallback ladder

primary route
→ one retry for same hypothesis
→ reclassify owner
→ alternate route
→ simplify
→ static/post fallback

Repeated identical failure or budget/candidate exhaustion produces REPLAN_REQUIRED.

## Sequence routing

Shots in the same sequence receive continuity penalties when provider/reference-family changes would increase visual drift. Multi-shot is optional and only used when the sequence actually benefits from joint generation.
