# Trusted human approval adoption

Engineering permission is not brief/asset/storyboard approval. `actor_type=HUMAN` is descriptive metadata, never identity proof.

The State Engine uses a **pluggable trusted approval verifier**. The verifier is injected by a trusted runtime outside canonical project state. Missing, throwing, non-boolean, or rejecting verification fails closed.

Two trust backends are supported by the implementation:

1. **Platform-attested explicit-user approval** — preferred for cloud-native ChatGPT/Codex workflows when the hosting platform supplies an immutable attestation that the user explicitly approved the exact payload.
2. **Operator-signed Ed25519 receipt** — optional high-assurance/offline fallback for environments that need a local cryptographic signer.

Neither backend is automatically trusted merely because its data exists in GitHub or project files.

## Common approval payload

Every trusted approval binds:

- audience;
- project ID;
- actor ID;
- operator event ID;
- decision = `APPROVE`;
- timezone-aware issue time;
- exact base state revision;
- exact base project hash;
- evidence ID/kind/subject;
- exact subject hash;
- exact dependency hashes;
- `status=APPROVED`;
- `actor_type=HUMAN`;
- evidence state revision = base + 1;
- action/provider/workspace/ticket/candidate/shot/cost fields where applicable.

The subject and dependencies are revalidated during adoption. Drift invalidates the approval.

## Cloud-native platform attestation

`AttestedApprovalVerifier` accepts an envelope shaped as:

```json
{
  "backend": "PLATFORM_ATTESTATION",
  "payload": { "...": "exact approval payload" },
  "attestation": { "...": "opaque platform proof" }
}
```

The trusted launcher injects:

- expected audience;
- expected human actor ID;
- `history_reader=engine.inspect_history`;
- a platform-specific `attestation_verifier(attestation, payload)`.

The attestation verifier must independently prove that:

1. the action was an **explicit user approval**, not model inference;
2. it binds the exact payload bytes/claims represented by the payload;
3. the actor belongs to the expected trusted user identity;
4. the attestation is valid for the intended runtime/audience;
5. it has not been revoked, replayed, substituted, or fabricated by the agent.

Only the literal boolean `True` is accepted from the verifier.

### Not trusted as platform attestation

The following are **workflow evidence only** and must never be accepted as the trust root:

- ordinary chat text such as “approved”;
- an assistant interpretation of user intent;
- GitHub issue comments;
- GitHub labels;
- pull-request reviews;
- commit authorship;
- `actor_type=HUMAN`;
- agent-authored JSON;
- any GitHub record created with credentials the agent can itself use.

This matters because an agent operating through the user's GitHub authorization can create records that GitHub displays under the same account identity. GitHub provenance alone therefore does not distinguish user action from agent action in this operating model.

### Deployment status

Support in the library does **not** prove that the current ChatGPT/Codex runtime exposes a usable immutable user attestation.

Until the runtime can actually provide and verify that attestation, the cloud-native backend remains **deployment-blocked / fail-closed**. Do not substitute GitHub comments or raw chat history.

## Ed25519 signer backend

`SignedApprovalVerifier` remains supported as an optional high-assurance/offline backend.

The trusted launcher supplies an externally pinned audience and mapping of key ID to `(operator actor ID, public key bytes)`. Never accept the keyring or audience from project/ticket data.

The signer and private key must remain outside agent access. The implementation verifies only; it does not create keys or infer consent.

Install the optional verifier dependency from `requirements-approval.txt` when this backend is used.

## Reserved State Engine adoption

Both trusted backends use the same reserved adoption path:

`adopt_approval` → `StateEngine.commit_approval_adoption` → `HUMAN_APPROVAL_ADOPTED`

Generic `begin_transaction` refuses `HUMAN_APPROVAL_ADOPTED`.

The reserved path:

- verifies the trusted payload;
- checks exact project/base revision/hash;
- checks current subject/dependency bindings;
- rejects duplicate evidence/operator events;
- increments state revision by exactly one;
- appends only the approval evidence;
- records approval payload hash, adopted evidence hash, and operator event ID in event history.

It does **not** alter subject content, timing, assets, claims, storyboard content, provider state, or spend state.

First prepare final subject content through an ordinary State Engine transaction. Then obtain trusted approval of that exact canonical base.

## Runtime verification at gates

`evaluate_gates(engine, approval_verifier=verifier)` requires the verifier to validate the exact canonical evidence and the matching `HUMAN_APPROVAL_ADOPTED` history event.

The launcher must supply `history_reader=engine.inspect_history`.

Missing history, missing trusted verifier, revoked trust, subject drift, dependency drift, wrong base, or unsupported attestation all fail closed.

The four-argument action-guard protocol uses the same trusted verifier for action-bound approvals such as spend/external processing/replacement/destructive operations.

## Project policy

For projects operated only through general ChatGPT conversation + Codex Cloud:

- do **not** require Windows signer enrollment by default;
- prefer platform-attested approval **only when the platform exposes a real trusted attestation interface**;
- until then, HUMAN approval gates remain blocked rather than silently weakening trust;
- the Ed25519 signer may be retained as an optional fallback, not a mandatory production workflow.
