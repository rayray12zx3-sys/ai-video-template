"""Permission checks for concrete actions, separate from production gates."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from math import isfinite

from .gates import _generative_shots, evaluate_gates
from .validators import evidence_status, finding, validate_project


@dataclass(frozen=True)
class ActionRequest:
    action: str
    action_id: str
    expected_state_revision: int
    expected_project_hash: str
    provider: str | None = None
    workspace_id: str | None = None
    ticket_id: str | None = None
    candidate_id: str | None = None
    shot_id: str | None = None
    asset_ids: tuple[str, ...] = ()
    quoted_cost: float | None = None


def _valid_cost(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool) and
            value >= 0 and (not isinstance(value, float) or isfinite(value)))


def _approval(doc, snapshot, kind, subject, request, *, provider=None, now=None, approval_verifier=None):
    valid, reason = evidence_status(doc, kind=kind, subject=subject, snapshot=snapshot,
                                    human=True, action_id=request.action_id, provider=provider, now=now)
    if not valid:
        return [finding(reason, f"{kind} authorization is absent or stale", subject=subject)]
    if not _trusted_approval(approval_verifier, kind, subject, request, snapshot):
        return [finding("UNTRUSTED_APPROVAL", f"{kind} lacks trusted human identity verification", subject=subject)]
    return []


def _trusted_approval(verifier, kind, subject, request, snapshot):
    if verifier is None:
        return False
    try:
        return verifier(kind, subject, request, snapshot) is True
    except Exception:
        return False


def _upload(doc, snapshot, asset_id, request, now, approval_verifier):
    errors = []
    asset = next((a for a in doc.get("assets", []) if isinstance(a, dict) and a.get("id") == asset_id), None)
    subject = f"asset:{asset_id}"
    if asset is None:
        return [finding("MISSING_ASSET", "Upload asset does not exist", subject=subject)]
    if asset.get("lifecycle") not in {"APPROVED", "FINAL"}:
        errors.append(finding("ASSET_NOT_APPROVED", "Upload asset is not approved", subject=subject))
    policy = asset.get("external_processing", {"policy": "REVIEW_REQUIRED"})
    if not isinstance(policy, dict):
        return errors + [finding("EXTERNAL_POLICY", "Invalid external processing policy", subject=subject)]
    value = policy.get("policy", "REVIEW_REQUIRED")
    allowed = policy.get("allowed_providers", [])
    if value == "FORBIDDEN":
        errors.append(finding("UPLOAD_FORBIDDEN", "External processing is forbidden", subject=subject))
    elif value not in {"ALLOWED", "REVIEW_REQUIRED"}:
        errors.append(finding("EXTERNAL_POLICY", "Unknown external processing policy", subject=subject))
    elif not isinstance(allowed, list) or not request.provider or request.provider not in allowed:
        errors.append(finding("PROVIDER_NOT_ALLOWED", "Provider is not explicitly allowed", subject=subject))
    elif value == "REVIEW_REQUIRED":
        valid, reason = evidence_status(doc, kind="EXTERNAL_PROCESSING_APPROVAL", subject=subject,
                                        snapshot=snapshot, human=True, action_id=request.action_id,
                                        provider=request.provider, workspace_id=request.workspace_id, now=now)
        if not valid:
            errors.append(finding(reason, "External processing review does not bind this action/provider/workspace",
                                  subject=subject))
        elif not _trusted_approval(approval_verifier, "EXTERNAL_PROCESSING_APPROVAL", subject, request, snapshot):
            errors.append(finding("UNTRUSTED_APPROVAL", "Upload review lacks trusted human identity verification",
                                  subject=subject))
    return errors


def guard_action(engine, request: ActionRequest, *, now=None, preflight_verifier=None,
                 approval_verifier=None):
    """Return ALLOW/DENY with reasons; no provider or State Engine mutation."""
    now = now or datetime.now(timezone.utc)
    validation = validate_project(engine)
    errors = list(validation.findings) if not validation.ok else []
    snapshot = validation.snapshot
    if snapshot is None:
        return {"action": request.action, "decision": "DENY", "blocking_findings": errors}
    doc = snapshot.document
    if request.expected_state_revision != snapshot.state_revision or request.expected_project_hash != snapshot.project_hash:
        errors.append(finding("STALE_ACTION", "Action state revision/hash differs from canonical state"))
    if not request.action_id:
        errors.append(finding("ACTION_ID", "Action ID is required"))
    if request.action in {"EXTERNAL_UPLOAD", "PAID_GENERATION", "BATCH_GENERATION"}:
        if not request.provider or not request.workspace_id:
            errors.append(finding("EXECUTION_TARGET", "Explicit provider and workspace ID are required"))
        if not request.asset_ids and request.action == "EXTERNAL_UPLOAD":
            errors.append(finding("INPUT_ASSETS", "Upload requires asset IDs"))
        for asset_id in request.asset_ids:
            errors.extend(_upload(doc, snapshot, asset_id, request, now, approval_verifier))
    if request.action in {"PAID_GENERATION", "BATCH_GENERATION"}:
        gates = evaluate_gates(engine)
        gate_id = "G5" if request.action == "BATCH_GENERATION" else "G4"
        if gates[gate_id]["status"] != "PASS":
            errors.append(finding("GATE_NOT_READY", f"{gate_id} must pass before this action"))
        if not all((request.ticket_id, request.candidate_id, request.shot_id)):
            errors.append(finding("TICKET_BINDING", "Ticket, candidate, and shot IDs are required"))
        if not _valid_cost(request.quoted_cost):
            errors.append(finding("COST_QUOTE", "A nonnegative quoted cost is required"))
        if request.shot_id not in {s.get("id") for s in doc.get("shots", []) if isinstance(s, dict)}:
            errors.append(finding("SHOT_MISSING", "Requested shot does not exist"))
        else:
            shot = next(s for s in doc["shots"] if isinstance(s, dict) and s.get("id") == request.shot_id)
            if shot not in _generative_shots(doc):
                errors.append(finding("SHOT_NOT_GENERATIVE", "Paid generation requires a required generative shot"))
            shot_inputs = shot.get("input_asset_ids", [])
            if (not isinstance(shot_inputs, list) or any(not isinstance(value, str) for value in shot_inputs)
                    or len(set(request.asset_ids)) != len(request.asset_ids)
                    or set(request.asset_ids) != set(shot_inputs)):
                errors.append(finding("INPUT_BINDING", "Action input assets must match the shot's canonical inputs"))
        plan = doc.get("generation_plan", {})
        if (not isinstance(plan, dict) or not isinstance(plan.get("budget_remaining"), (int, float))
                or isinstance(plan.get("budget_remaining"), bool) or request.quoted_cost is None
                or plan.get("budget_remaining", -1) < request.quoted_cost):
            errors.append(finding("BUDGET", "Project budget is absent or insufficient"))
        valid, reason = evidence_status(doc, kind="SPEND_APPROVAL", subject="project:generation_plan",
                                        snapshot=snapshot, human=True, action_id=request.action_id,
                                        provider=request.provider, ticket_id=request.ticket_id,
                                        candidate_id=request.candidate_id, shot_id=request.shot_id,
                                        workspace_id=request.workspace_id, max_cost=request.quoted_cost,
                                        exact_revision=True, now=now)
        if not valid:
            errors.append(finding("SPEND_APPROVAL_BINDING", f"Human spend approval does not bind this action: {reason}"))
        elif not _trusted_approval(approval_verifier, "SPEND_APPROVAL", "project:generation_plan", request, snapshot):
            errors.append(finding("UNTRUSTED_APPROVAL", "Spend approval lacks trusted human identity verification"))
        if request.action == "BATCH_GENERATION" and not _trusted_approval(
                approval_verifier, "BATCH_APPROVAL", "project:generation_plan", request, snapshot):
            errors.append(finding("UNTRUSTED_APPROVAL", "Batch approval lacks trusted human identity verification"))
        try:
            preflight = preflight_verifier(request, snapshot, now) if preflight_verifier is not None else None
        except Exception:
            preflight = None
        if not isinstance(preflight, dict):
            preflight = {}
            errors.append(finding("UNTRUSTED_PREFLIGHT", "Trusted runtime preflight is unavailable"))
        if (preflight.get("provider") != request.provider or preflight.get("workspace_id") != request.workspace_id
                or preflight.get("state_revision") != snapshot.state_revision
                or preflight.get("project_hash") != snapshot.project_hash):
            errors.append(finding("PREFLIGHT_BINDING", "Preflight does not bind this provider, workspace, and state"))
        if (preflight.get("workspace_binding_proven") is not True or
                preflight.get("workspace_binding_workspace_id") != request.workspace_id or
                preflight.get("workspace_binding_method") != "EXPLICIT_REQUEST" or
                not isinstance(preflight.get("workspace_binding_evidence_ref"), str) or
                not preflight["workspace_binding_evidence_ref"].strip()):
            errors.append(finding("WORKSPACE_BINDING", "Paid command workspace binding is unproven"))
        cap = preflight.get("provider_cost_cap")
        if (preflight.get("provider_cost_cap_enforced") is not True or
                preflight.get("provider_cost_cap_source") != "PROVIDER_ENFORCED" or
                not isinstance(preflight.get("provider_cost_cap_evidence_ref"), str) or
                not preflight["provider_cost_cap_evidence_ref"].strip() or
                not _valid_cost(cap) or not _valid_cost(request.quoted_cost) or
                cap > request.quoted_cost):
            errors.append(finding("COST_CAP", "Provider-enforced spend cap is unproven or exceeds approval"))
        if not all(preflight.get(k) is True for k in ("auth_ready", "workspace_matches", "entitlement_ready",
                                                    "slots_ready", "candidate_limit_ready", "capability_ready")):
            errors.append(finding("PREFLIGHT", "Fresh authenticated capacity/capability preflight is required"))
        try:
            checked = datetime.fromisoformat(preflight["checked_at"].replace("Z", "+00:00"))
            if checked.tzinfo is None or checked > now or now - checked > timedelta(hours=1):
                raise ValueError
        except (KeyError, AttributeError, ValueError):
            errors.append(finding("PREFLIGHT_STALE", "Preflight timestamp is absent or stale"))
        if preflight.get("submission_state") != "CLEAR":
            errors.append(finding("SUBMISSION_STATE", "Submission state must be CLEAR after reconciliation"))
    elif request.action in {"REPLACE_ASSET", "DESTRUCTIVE_OPERATION"}:
        if len(request.asset_ids) != 1:
            errors.append(finding("TARGET_ASSET", "Exactly one target asset is required"))
        else:
            subject = f"asset:{request.asset_ids[0]}"
            asset = next((a for a in doc.get("assets", []) if isinstance(a, dict)
                          and a.get("id") == request.asset_ids[0]), None)
            selections = doc.get("selections")
            selections = selections if isinstance(selections, dict) else {}
            if asset is None:
                errors.append(finding("MISSING_ASSET", "Target asset does not exist", subject=subject))
            elif (asset.get("lifecycle") in {"APPROVED", "FINAL"} or asset.get("selected") is True
                  or request.asset_ids[0] in selections.values()
                  or request.action == "DESTRUCTIVE_OPERATION"):
                errors.extend(_approval(doc, snapshot, "REPLACEMENT_APPROVAL" if request.action == "REPLACE_ASSET" else "DESTRUCTIVE_APPROVAL",
                                        subject, request, now=now, approval_verifier=approval_verifier))
    elif request.action != "EXTERNAL_UPLOAD":
        errors.append(finding("UNKNOWN_ACTION", "Unknown action type"))
    return {"action": request.action, "decision": "DENY" if errors else "ALLOW",
            "blocking_findings": errors}
