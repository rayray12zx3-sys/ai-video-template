# Cross-Machine Project Handoff Contract v0.1

Local file locks do not protect two different machines.

## MVP policy

One active workstation is the canonical writer for a production project at a time.

Before switching machines:
1. finish/abort pending transactions
2. create project checkpoint
3. commit/push canonical state required for handoff
4. next machine fetches/pulls
5. verify exact remote/base state before mutation

## Remote conflict guard

State Engine may validate:
- repository remote identity
- branch
- base Git commit
- canonical revision/hash

If origin canonical state advanced unexpectedly:
`REMOTE_STATE_CONFLICT`

Do not force-overwrite.

## Empty-project bootstrap

Before a project has a canonical revision/hash, use `capture_bootstrap_base`
and `StateEngine.bootstrap(..., handoff_base=base)` rather than ordinary
handoff evidence. Fetch `origin` first. Bootstrap requires a committed base
with neither `project.yaml` nor `events.jsonl`, local HEAD equal to fetched
`origin/<branch>`, and evidence binding the remote identity fingerprint,
attached branch, commit and repository-relative project path. Working canonical
files must be absent, except for a zero-byte prepared history or an exact
revision-zero retry using the retained bootstrap evidence. A pending journal,
competing candidate or different fetched origin ref fails closed.

Capture and verification also require effective `-text` on both canonical
paths and no active `filter`, `ident` or `working-tree-encoding` conversions.
They query Git attributes before canonical creation and bind the effective
values into bootstrap evidence. Missing `-text` (including with
`core.autocrlf=true`) or changed attributes after capture rejects bootstrap.
Commit the byte-preserving policy in the base's `.gitattributes` so subsequent
workstations inherit it. Ordinary handoff checks are unchanged.

Revision zero is genesis with empty history; no `-1 -> 0` event exists. Bootstrap
is local and offline. As with ordinary handoff, a tracking ref proves only the
last fetched base, not live remote freshness or exclusive remote ownership.
Commit/push genesis, fetch, then capture ordinary handoff evidence before the
first Git-backed `0 -> 1` transaction. See the
[I1 protocol](../implementation/phase-i1-state-engine.md#revision-zero-bootstrap)
for crash retry and exact-byte idempotence.

## Environment profile

Machine-specific capabilities remain outside canonical project semantics:
- local root mappings
- PixVerse Plugin availability
- Node/Python/FFmpeg
- Adobe
- network/admin constraints

## Future

If true simultaneous multi-machine writing becomes necessary, add a remote serialization service via ADR. Do not build it in MVP.
