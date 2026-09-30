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

## Environment profile

Machine-specific capabilities remain outside canonical project semantics:
- local root mappings
- PixVerse Plugin availability
- Node/Python/FFmpeg
- Adobe
- network/admin constraints

## Future

If true simultaneous multi-machine writing becomes necessary, add a remote serialization service via ADR. Do not build it in MVP.
