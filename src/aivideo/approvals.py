"""Trusted human approval verification and State Engine-only adoption.

Trust is injected by the runtime and must live outside project state.
Supported backends:
- Ed25519 operator-signed receipts.
- Platform-attested explicit-user approvals.

This module never infers user consent and never creates a trusted attestation.
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


def _payload_shape_ok(payload, *, audience, clock, actor_id=None):
    try:
        if (not isinstance(payload, dict)
                or payload["audience"] != audience
                or payload["decision"] != "APPROVE"
                or not isinstance(payload["actor_id"], str)
                or not payload["actor_id"].strip()
                or (actor_id is not None and payload["actor_id"] != actor_id)
                or not isinstance(payload["operator_event_id"], str)
                or not payload["operator_event_id"].strip()):
            return False
        issued = datetime.fromisoformat(payload["issued_at"].replace("Z", "+00:00"))
        if issued.tzinfo is None or issued > clock():
            return False
        revision = payload["base_state_revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            return False
        digest = payload["base_project_hash"]
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)):
            return False
        evidence = payload["evidence"]
        if (not isinstance(evidence, dict)
                or evidence["actor_type"] != "HUMAN"
                or evidence["status"] != "APPROVED"
                or isinstance(evidence["state_revision"], bool)
                or not isinstance(evidence["state_revision"], int)
                or evidence["state_revision"] != revision + 1
                or "approval_provenance" in evidence):
            return False
        return True
    except Exception:
        return False


def _trusted_verifier_call(verifier, *args):
    if len(args) == 2:
        evidence, snapshot = args
        payload = verifier.payload(evidence.get("approval_provenance", {}))
        if not (payload and payload.get("project_id") == snapshot.document.get("project_id")
                and payload["evidence"] == {k: v for k, v in evidence.items()
                                            if k != "approval_provenance"}):
            return False
        try:
            history = verifier.history_reader() if verifier.history_reader else ()
            return any(event.get("event_type") == "HUMAN_APPROVAL_ADOPTED"
                       and event.get("state_revision_before") == payload["base_state_revision"]
                       and event.get("project_hash_before") == payload["base_project_hash"]
                       and event.get("state_revision_after") == payload["evidence"]["state_revision"]
                       and event.get("transition_metadata", {}).get("approval_payload_hash") == fingerprint(payload)
                       and event.get("transition_metadata", {}).get("adopted_evidence_hash") == fingerprint(evidence)
                       and event.get("transition_metadata", {}).get("operator_event_id") == payload["operator_event_id"]
                       for event in history)
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
                           approval_verifier=verifier, now=verifier.clock(), **options)[0]


class SignedApprovalVerifier:
    """Verify operator-signed Ed25519 approval receipts.

    This remains the high-assurance/offline backend. The keyring and audience
    must be injected by a trusted launcher, never read from canonical state.
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
            if not _payload_shape_ok(payload, audience=self.audience,
                                     actor_id=actor, clock=self.clock):
                return None
            signature = base64.b64decode(envelope["signature"], validate=True)
            Ed25519PublicKey.from_public_bytes(key).verify(signature, approval_bytes(payload))
            return payload
        except Exception:
            return None

    def __call__(self, *args):
        return _trusted_verifier_call(self, *args)


class AttestedApprovalVerifier:
    """Verify a platform-attested explicit-user approval.

    attestation_verifier is a trusted-runtime callback with signature
    (attestation, payload) -> bool. It must independently verify that the
    platform attestation represents an explicit user approval for the exact
    payload. Only the literal boolean True is accepted.

    Raw chat text, GitHub comments/labels/reviews, actor_type=HUMAN strings, or
    agent-authored metadata are not attestations.
    """

    def __init__(self, attestation_verifier, *, audience, actor_id,
                 history_reader=None, clock=None):
        if not callable(attestation_verifier):
            raise ValueError("trusted attestation verifier is required")
        if not isinstance(audience, str) or not audience:
            raise ValueError("trusted audience is required")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ValueError("trusted actor_id is required")
        self.attestation_verifier = attestation_verifier
        self.audience = audience
        self.actor_id = actor_id
        self.history_reader = history_reader
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def payload(self, envelope):
        try:
            if (not isinstance(envelope, dict)
                    or envelope.get("backend") != "PLATFORM_ATTESTATION"
                    or "attestation" not in envelope):
                return None
            payload = envelope["payload"]
            if not _payload_shape_ok(payload, audience=self.audience,
                                     actor_id=self.actor_id, clock=self.clock):
                return None
            if self.attestation_verifier(envelope["attestation"], payload) is not True:
                return None
            return payload
        except Exception:
            return None

    def __call__(self, *args):
        return _trusted_verifier_call(self, *args)


def adopt_approval(engine, envelope, verifier, *, transaction_id, handoff_base=None):
    """Adopt one explicit trusted user event; never infer consent or alter subjects."""
    before = engine.inspect_consistency()
    payload = verifier.payload(envelope)
    if payload is None:
        raise StateConflict("approval is untrusted")
    return engine.commit_approval_adoption(
        TransactionRequest(before.state_revision, before.project_hash, transaction_id,
                           payload["actor_id"], "HUMAN_APPROVAL_ADOPTED", handoff_base),
        envelope, verifier)


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
           e.get("approval_provenance", {}).get("payload", {}).get("operator_event_id")
           == payload["operator_event_id"]
           for e in existing):
        raise StateConflict("approval event or evidence ID was already adopted")
    existing.append(evidence)

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
    candidate = ProjectSnapshot(after, after["state_revision"], "", before.access,
                                after.get("next_action"))
    valid, _ = evidence_status(after, kind=evidence.get("kind"),
                               subject=evidence.get("subject"),
                               snapshot=candidate, human=True,
                               required_bindings=required,
                               require_trusted=True,
                               approval_verifier=lambda item, snap: item == evidence,
                               now=verifier.clock())
    if not valid:
        raise StateConflict(
            "approval subject/dependencies/expiry do not bind final canonical content")
    return after, payload
