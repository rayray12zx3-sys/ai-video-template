"""Operator-signed approval verification and State Engine-only adoption.

The trusted runtime supplies public keys and audience outside project state.
This module never creates keys or signs approvals. The signer must be outside
the agent's filesystem/credential boundary and confirm an explicit human event.
"""

import base64
from copy import deepcopy
from datetime import datetime, timezone
import json

from .state_engine import StateConflict, TransactionRequest
from .validators import evidence_status, fingerprint

DOMAIN = b"aivideo.operator-approval.v1\x00"


def approval_bytes(payload):
    return DOMAIN + json.dumps(payload, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode("utf-8")


class SignedApprovalVerifier:
    """Fail closed for missing crypto, unknown keys, malformed or forged events.

    keyring maps key IDs to (actor ID, raw Ed25519 public key bytes).
    Do not derive the keyring or audience from canonical project data.
    Two-argument calls verify a gate's exact evidence. Four-argument calls
    support the existing Action Guard verifier protocol.
    """

    def __init__(self, keyring, *, audience, history_reader=None, clock=None):
        if not isinstance(audience, str) or not audience:
            raise ValueError("trusted audience is required")
        self.keyring = dict(keyring)
        self.audience = audience
        self.history_reader = history_reader
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def payload(self, envelope):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            payload = envelope["payload"]
            actor, key = self.keyring[envelope["key_id"]]
            if (payload["audience"] != self.audience or payload["actor_id"] != actor
                    or payload["decision"] != "APPROVE"
                    or not isinstance(payload["operator_event_id"], str)
                    or not payload["operator_event_id"].strip()):
                return None
            issued = datetime.fromisoformat(payload["issued_at"].replace("Z", "+00:00"))
            if issued.tzinfo is None or issued > self.clock():
                return None
            revision = payload["base_state_revision"]
            if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                return None
            digest = payload["base_project_hash"]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                return None
            e = payload["evidence"]
            if (e["actor_type"] != "HUMAN" or e["status"] != "APPROVED"
                    or isinstance(e["state_revision"], bool) or not isinstance(e["state_revision"], int)
                    or e["state_revision"] != revision + 1
                    or "approval_provenance" in e):
                return None
            signature = base64.b64decode(envelope["signature"], validate=True)
            Ed25519PublicKey.from_public_bytes(key).verify(signature, approval_bytes(payload))
            return payload
        except Exception:
            return None

    def __call__(self, *args):
        if len(args) == 2:
            evidence, snapshot = args
            payload = self.payload(evidence.get("approval_provenance", {}))
            if not (payload and payload.get("project_id") == snapshot.document.get("project_id")
                    and payload["evidence"] == {k: v for k, v in evidence.items() if k != "approval_provenance"}):
                return False
            try:
                history = self.history_reader() if self.history_reader else ()
                return any(e.get("event_type") == "HUMAN_APPROVAL_ADOPTED"
                           and e.get("state_revision_before") == payload["base_state_revision"]
                           and e.get("project_hash_before") == payload["base_project_hash"]
                           and e.get("state_revision_after") == payload["evidence"]["state_revision"]
                           and e.get("transition_metadata", {}).get("approval_payload_hash") == fingerprint(payload)
                           and e.get("transition_metadata", {}).get("adopted_evidence_hash") == fingerprint(evidence)
                           and e.get("transition_metadata", {}).get("operator_event_id") == payload["operator_event_id"]
                           for e in history)
            except Exception:
                return False
        if len(args) != 4:
            return False
        kind, subject, request, snapshot = args
        options = {}
        if kind in {"SPEND_APPROVAL", "EXTERNAL_PROCESSING_APPROVAL",
                    "REPLACEMENT_APPROVAL", "DESTRUCTIVE_APPROVAL"}:
            options["action_id"] = request.action_id
        if kind in {"SPEND_APPROVAL", "EXTERNAL_PROCESSING_APPROVAL"}:
            options.update(provider=request.provider, workspace_id=request.workspace_id)
        if kind == "SPEND_APPROVAL":
            options.update(ticket_id=request.ticket_id, candidate_id=request.candidate_id,
                           shot_id=request.shot_id, max_cost=request.quoted_cost,
                           exact_revision=True)
        return evidence_status(snapshot.document, kind=kind, subject=subject,
                               snapshot=snapshot, human=True, require_trusted=True,
                               approval_verifier=self, now=self.clock(), **options)[0]


def adopt_approval(engine, envelope, verifier, *, transaction_id, handoff_base=None):
    """Adopt one explicit operator event; never infer consent or alter subjects."""
    before = engine.inspect_consistency()
    payload = verifier.payload(envelope)
    if payload is None:
        raise StateConflict("approval is untrusted")
    return engine.commit_approval_adoption(
        TransactionRequest(before.state_revision, before.project_hash, transaction_id,
                           payload["actor_id"], "HUMAN_APPROVAL_ADOPTED", handoff_base), envelope, verifier)


def _plan_approval_adoption(before, envelope, verifier):
    """Pure plan for the reserved State Engine path; never accepts an after-state."""
    payload = verifier.payload(envelope)
    if (payload is None or payload.get("project_id") != before.document.get("project_id")
            or payload["base_state_revision"] != before.state_revision
            or payload["base_project_hash"] != before.project_hash):
        raise StateConflict("approval is untrusted or does not bind the exact adoption base")
    evidence = deepcopy(payload["evidence"])
    evidence["approval_provenance"] = deepcopy(envelope)
    after = deepcopy(before.document)
    after["state_revision"] += 1
    existing = after.setdefault("evidence", [])
    if any(e.get("id") == evidence.get("id") or
           e.get("approval_provenance", {}).get("payload", {}).get("operator_event_id") == payload["operator_event_id"]
           for e in existing):
        raise StateConflict("approval event or evidence ID was already adopted")
    existing.append(evidence)
    # Check all typed upstream dependencies in addition to gate-required bindings.
    required = tuple(edge["source"] for edge in after.get("dependencies", [])
                     if isinstance(edge, dict) and isinstance(edge.get("source"), str)
                     and edge.get("target") == evidence.get("subject"))
    if evidence.get("kind") == "SOURCE_SYNC_APPROVAL":
        shot = next((s for s in after.get("shots", [])
                     if f"shot:{s.get('id')}" == evidence.get("subject")), {})
        required += (f"asset:{shot.get('base_plate_asset_id')}",)
    if evidence.get("kind") in {"STORYBOARD_APPROVAL", "BATCH_APPROVAL"}:
        required += tuple(f"shot:{s['id']}" for s in after.get("shots", [])
                          if s.get("readiness", "REQUIRED") == "REQUIRED")
    if evidence.get("kind") == "ANIMATIC_APPROVAL":
        required += ("project:storyboard",)
        required += tuple(f"asset:{a['id']}" for a in after.get("assets", [])
                          if a.get("criticality") == "REQUIRED_FOR_ANIMATIC")
    if evidence.get("kind") == "FINAL_QC_APPROVAL":
        required += tuple(f"asset:{a['id']}" for a in after.get("assets", [])
                          if a.get("criticality") == "REQUIRED_FOR_DELIVERY")
    from .state_engine import ProjectSnapshot
    candidate = ProjectSnapshot(after, after["state_revision"], "", before.access, after.get("next_action"))
    valid, _ = evidence_status(after, kind=evidence.get("kind"), subject=evidence.get("subject"),
                               snapshot=candidate, human=True, required_bindings=required,
                               require_trusted=True,
                               approval_verifier=lambda item, snap: item == evidence,
                               now=verifier.clock())
    if not valid:
        raise StateConflict("approval subject/dependencies/expiry do not bind final canonical content")
    return after, payload
