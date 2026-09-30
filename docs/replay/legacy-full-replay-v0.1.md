# Legacy Full Replay v0.1

Purpose: replay representative legacy production paths through the proposed Template v2 architecture to find project-specific exceptions before freezing the specification.

## Replay cases

### Example A — exact diegetic text + hand contact

Canonical state:
- intent: hand contacts the SAMPLE label on a marked panel
- requirements: semantic precision HIGH, interaction precision HIGH, motion LOW
- constraints:
  - exact DIEGETIC text = "SAMPLE"
  - hand CONTACT MARKED_PANEL
  - text readable
  - wrong-panel contact forbidden

Router:
- T2V disqualified by hard semantic/interaction constraints
- primary: reference-first AI_IMAGE/composite
- optional video: minimal-motion I2V after reference approval

Gate/validator:
- reference asset must be APPROVED with hash before paid I2V
- active prompt must be unique
- ticket must bind exact approved reference

QC:
- exact text
- contact relation
- hand/anatomy
- locked composition
- temporal artifacts

Result: PASS. No project-specific exception required.

### Example B — low angle + scale + structure growth/lift

Canonical state:
- structure HIGH
- motion HIGH
- camera HIGH
- 24 mm low-angle wide lens
- key states: low structure → rapid growth/lift → elevated end state
- spatial relation: structure supports/lifts subject
- must_not: distort subject

Router:
- complexity HIGH
- MOTION_3D previs recommended
- then evaluate transition/reference video route
- split-shot fallback if combined event complexity remains too high

Gate/validator:
- previs/approved key-state evidence required before generation when the project profile marks this shot as high-risk
- paid ticket requires fresh provider capability snapshot

QC:
- structure
- subject distortion
- camera/lens look
- scale relation
- motion physics
- start/end state
- edit handles

Result: PASS. No project-specific exception required.

### Example C — revision lane

Revision state:
- source = completed master
- affected shot = the selected revision target
- initial failure owner = REFERENCE due to a reference mismatch in framing and environment
- after corrected reference approval, owner becomes GENERATION for unwanted body sway/smile

Canonical state:
- locked properties: face identity, head/shoulder/torso position, environment, background, camera
- allowed motion: one natural blink
- forbidden: smile, body sway, head sway

Router:
1. REFERENCE_FIX
2. approve new reference
3. reference-first I2V
4. second same-route attempt may test one changed hypothesis
5. repeated same failure triggers REPLAN_REQUIRED
6. fallback STATIC_HOLD / AE micro-animation

Ticket:
- binds the selected reference hash and current state revision
- separate candidate ticket per paid attempt
- idempotency prevents duplicate submission

QC:
- identity
- locked-property drift
- expression
- body motion
- background/camera lock
- editability

Result: PASS. Revision does not need to rerun the full new-production gate chain.

### Example D — real UI source video

Canonical state:
- production method = SOURCE_VIDEO
- source asset = real UI recording
- no AI generation route
- evidence = approval/QC, not production method

Router:
- bypass paid generation

QC profile:
- UI accuracy
- legibility
- crop
- timing
- safe area

Result: PASS. No fixture-specific validator branch is required.

### Example E — editorial match cut / no new media

Canonical state:
- production method = PREMIERE
- operation = MATCH_CUT
- inputs = neighboring approved media
- evidence = editorial approval

Router:
- NO_NEW_MEDIA / PREMIERE
- no provider capability or paid generation path

QC:
- continuity
- timing
- editorial intent

Result: PASS. No fixture-specific exception is required.

## Whole-project replay

### Discovery → Brief lock
DISCOVERY interaction mode collects creative requirements.
G0 BRIEF_LOCK requires human approval.

### Master assets
Character/world/prop masters enter the Asset Registry and advance through EXPECTED → RECEIVED → IMPORTED → REVIEWED → APPROVED.
G1 is evaluated from asset criticality, not hard-coded asset names.

### Storyboard
A frame-based timeline is represented as shot entities with ranges, intent, requirements, constraints, and production methods.
Real UI / editorial shots coexist with AI shots without schema exceptions.
G2 requires appropriate evidence per shot, not a fixed JPEG count.

### Static animatic
G3 checks timing, shot order, continuity and creative approval.
Bulk paid generation remains blocked before G3.

### Generation readiness
Provider capability snapshots are refreshed.
Provider runtime, entitlement, and capability facts are revalidated before execution. Manual web routes remain explicit unless an authorized programmable path is configured.
G4 confirms routes can be compiled but does not itself authorize spend.

### Pilot / batch
Representative high-risk shots can be used for G5 pilot validation.
Small projects may mark G5 NOT_APPLICABLE.
Batch generation uses independent Generation Tickets with candidate limits and human spend approval.

### QC / post
Q0-Q3 separate deterministic file checks, visual/temporal QC, creative QC and delivery QC.
Failures route back by owner rather than by provider-specific retry logic.

### Revision
A completed project may enter REVISION with scoped impact analysis.
Only affected dependencies become STALE.

### Delivery
G6 requires resolved required shots, no stale critical dependencies, technical delivery conformance and human creative approval.

## Remaining gaps discovered by replay

The replay cases required no shot-ID-specific runtime logic. Five interface details still needed definition before the baseline was frozen:

1. **Criticality vocabulary**
   Assets/shots need a small standard set of criticality/readiness tags so G1/G2/G3 can evaluate requirements without project-specific code.

2. **Impact propagation semantics**
   Dependency edges need typed propagation rules. Not every upstream change should invalidate every downstream artifact.

3. **Ticket retention policy**
   Executed/paid tickets and receipts must be durable; unexecuted derived tickets may be regenerated. Exact Git retention paths need to be specified.

4. **Provider capability schema**
   A normalized provider snapshot interface is needed to expose native controls without leaking provider-specific fields into shot schema.

5. **Asset locator abstraction**
   Local path, Drive ID/URL, provider asset ID and future object storage need one URI/locator contract.

These are implementation-interface gaps, not evidence of a broken core model.

## Replay verdict

PASS WITH FIVE INTERFACE ITEMS.

No replay fixture requires a branch keyed to a shot identifier.

The architecture is therefore ready for one final interface-definition pass before `SPEC_V2_BASELINE_1`.
