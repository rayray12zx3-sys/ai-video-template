"""Read-only I2 integrity and evidence checks over a State Engine snapshot."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from .schema import SchemaError
from .state_engine import RecoveryConflict, StateEngine, ProjectSnapshot


IMPACTS = frozenset({"IDENTITY", "APPEARANCE", "STRUCTURE", "COMPOSITION", "CAMERA",
                     "MOTION", "TIMING", "SEMANTIC_CONTENT", "AUDIO", "BRAND",
                     "TECHNICAL_FORMAT", "DELIVERY_ONLY", "GENERIC"})
CRITICALITIES = frozenset({"OPTIONAL", "REQUIRED_FOR_STORYBOARD", "REQUIRED_FOR_ANIMATIC",
                           "REQUIRED_FOR_GENERATION", "REQUIRED_FOR_DELIVERY"})
LIFECYCLES = frozenset({"EXPECTED", "RECEIVED", "IMPORTED", "REVIEWED", "APPROVED",
                        "FINAL", "REJECTED", "SUPERSEDED", "MISSING", "STALE",
                        "REUPLOAD_REQUIRED"})
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ValidationResult:
    snapshot: ProjectSnapshot | None
    findings: tuple[dict, ...]

    @property
    def ok(self):
        return self.snapshot is not None and not any(f["severity"] == "ERROR" for f in self.findings)


def finding(code, message, *, severity="ERROR", subject=None):
    return {"code": code, "severity": severity, "message": message, "subject": subject}


def fingerprint(value):
    """Stable hash of a canonical subject, independent of file formatting."""
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def subjects(document):
    result = {f"project:{name}": document[name] for name in
              ("brief", "storyboard", "animatic", "generation_plan", "final_qc")
              if name in document}
    for kind, key in (("asset", "assets"), ("shot", "shots")):
        for item in document.get(key, []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                result[f"{kind}:{item['id']}"] = item
    return result


def evidence_status(document, *, kind, subject, snapshot, human=False, action_id=None,
                    provider=None, ticket_id=None, candidate_id=None, shot_id=None,
                    workspace_id=None, max_cost=None, exact_revision=False,
                    required_bindings=(), now=None):
    """Return (valid, reason). Approvals bind to exact canonical subject hashes."""
    target = subjects(document).get(subject)
    if target is None:
        return False, "MISSING_SUBJECT"
    try:
        target_hash = fingerprint(target)
    except (TypeError, ValueError):
        return False, "INVALID_SUBJECT"
    matching = [item for item in document.get("evidence", []) if isinstance(item, dict)
                and item.get("kind") == kind and item.get("subject") == subject
                and (action_id is None or item.get("action_id") == action_id)
                and (provider is None or item.get("provider") == provider)
                and (ticket_id is None or item.get("ticket_id") == ticket_id)
                and (candidate_id is None or item.get("candidate_id") == candidate_id)
                and (shot_id is None or item.get("shot_id") == shot_id)
                and (workspace_id is None or item.get("workspace_id") == workspace_id)
                and (max_cost is None or isinstance(item.get("max_cost"), (int, float))
                     and not isinstance(item.get("max_cost"), bool) and item["max_cost"] >= max_cost)]
    if not matching:
        return False, "MISSING_EVIDENCE"
    current = subjects(document)
    now = now or datetime.now(timezone.utc)
    for item in matching:
        if item.get("status") != "APPROVED":
            continue
        if human and item.get("actor_type") != "HUMAN":
            continue
        revision = item.get("state_revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision > snapshot.state_revision or revision < 0:
            continue
        if exact_revision and revision != snapshot.state_revision:
            continue
        if item.get("subject_hash") != target_hash:
            continue
        expires = item.get("expires_at")
        if expires is not None:
            try:
                deadline = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if deadline.tzinfo is None or deadline <= now:
                    continue
            except (AttributeError, ValueError):
                continue
        bindings = item.get("dependency_hashes", {})
        try:
            binding_valid = isinstance(bindings, dict) and all(
                ref in current and isinstance(digest, str)
                and digest == fingerprint(current[ref]) for ref, digest in bindings.items())
        except (TypeError, ValueError):
            binding_valid = False
        if not binding_valid:
            continue
        if any(ref not in bindings for ref in required_bindings):
            continue
        return True, "APPROVED"
    return False, "STALE_OR_UNAPPROVED_EVIDENCE"


def _asset_findings(asset, root):
    out = []
    ident = asset.get("id")
    label = f"asset:{ident}"
    lifecycle = asset.get("lifecycle")
    if lifecycle not in LIFECYCLES:
        out.append(finding("ASSET_LIFECYCLE", "Asset lifecycle is missing or invalid", subject=label))
    if asset.get("criticality", "OPTIONAL") not in CRITICALITIES:
        out.append(finding("ASSET_CRITICALITY", "Asset criticality is invalid", subject=label))
    if lifecycle == "REUPLOAD_REQUIRED" and not asset.get("reupload_reason"):
        out.append(finding("REUPLOAD_REASON", "Reupload requires a reason", subject=label))
    if "selected" in asset and not isinstance(asset["selected"], bool):
        out.append(finding("ASSET_SELECTION", "selected must be a boolean", subject=label))
    if lifecycle == "RECEIVED" and asset.get("request_state") == "REQUESTED":
        out.append(finding("DUPLICATE_ASSET_REQUEST", "Received asset cannot be requested again", subject=label))
    digest = asset.get("sha256")
    if lifecycle in {"APPROVED", "FINAL"}:
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            out.append(finding("ASSET_HASH", "Approved/final asset requires SHA-256", subject=label))
        if not asset.get("provenance"):
            out.append(finding("ASSET_PROVENANCE", "Approved/final asset requires provenance", subject=label))
        locators = asset.get("locators", [])
        if not isinstance(locators, list):
            locators = []
        durable = [loc for loc in locators if isinstance(loc, dict)
                   and loc.get("type") in {"LOCAL", "GOOGLE_DRIVE", "ARCHIVE"}
                   and loc.get("availability") == "AVAILABLE"]
        if not durable:
            out.append(finding("MATERIALIZATION", "Approved/final asset requires an available non-provider locator", subject=label))
        if asset.get("origin") == "PROVIDER_OUTPUT":
            for name in ("media_metadata", "provider_task_id", "lineage"):
                if not asset.get(name):
                    out.append(finding("MATERIALIZATION", f"Provider output requires {name}", subject=label))
        for loc in durable:
            if loc.get("type") == "LOCAL":
                path = loc.get("path")
                if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                    out.append(finding("LOCATOR_PATH", "LOCAL locator must be project-relative", subject=label))
                    continue
                file_path = root / path
                try:
                    if not file_path.resolve().is_relative_to(root.resolve()):
                        out.append(finding("LOCATOR_PATH", "LOCAL locator resolves outside project", subject=label))
                    elif not file_path.is_file():
                        out.append(finding("MATERIALIZATION", "Available LOCAL locator is missing", subject=label))
                    elif isinstance(digest, str) and SHA256.fullmatch(digest):
                        if hashlib.sha256(file_path.read_bytes()).hexdigest() != digest:
                            out.append(finding("ASSET_HASH_MISMATCH", "LOCAL materialization hash differs", subject=label))
                except OSError:
                    out.append(finding("MATERIALIZATION", "LOCAL locator cannot be verified", subject=label))
    policy = asset.get("external_processing")
    if policy is not None:
        if not isinstance(policy, dict) or policy.get("policy") not in {"ALLOWED", "REVIEW_REQUIRED", "FORBIDDEN"}:
            out.append(finding("EXTERNAL_POLICY", "External processing policy is invalid", subject=label))
        elif not isinstance(policy.get("allowed_providers", []), list):
            out.append(finding("EXTERNAL_POLICY", "allowed_providers must be a list", subject=label))
    return out


def validate_project(engine: StateEngine) -> ValidationResult:
    """Inspect canonical state/history and report findings without recovery or writes."""
    try:
        snapshot = engine.inspect_consistency()
    except (OSError, ValueError, SchemaError, RecoveryConflict) as exc:
        return ValidationResult(None, (finding("CANONICAL_INTEGRITY", str(exc)),))
    doc = snapshot.document
    out = []
    if snapshot.access != "WRITABLE_VERSION":
        out.append(finding("SCHEMA_ACCESS", f"Project access is {snapshot.access}"))
        return ValidationResult(snapshot, tuple(out))
    try:
        json.dumps(doc, allow_nan=False)
    except (TypeError, ValueError):
        out.append(finding("CANONICAL_NUMERIC", "Canonical JSON contains non-finite or unserializable values"))
    if doc.get("workflow_status", "ACTIVE") != "COMPLETE" and not doc.get("next_action", "").strip():
        out.append(finding("NEXT_ACTION", "Non-complete project requires next_action"))
    ids = set()
    for kind, collection in (("asset", "assets"), ("shot", "shots")):
        for item in doc.get(collection, []):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                out.append(finding("ENTITY_ID", f"{kind} requires a nonempty id"))
                continue
            ref = f"{kind}:{item['id']}"
            if ref in ids:
                out.append(finding("DUPLICATE_ID", f"Duplicate {ref}", subject=ref))
            ids.add(ref)
            if kind == "asset":
                out.extend(_asset_findings(item, engine.project_dir))
            else:
                if item.get("readiness", "REQUIRED") not in {"REQUIRED", "OPTIONAL", "OMITTED_BY_DESIGN"}:
                    out.append(finding("SHOT_READINESS", "Invalid shot readiness", subject=ref))
                inputs = item.get("input_asset_ids", [])
                if not isinstance(inputs, list) or any(not isinstance(value, str) or not value for value in inputs):
                    out.append(finding("SHOT_INPUTS", "Shot input_asset_ids must be asset ID strings", subject=ref))
                elif any(f"asset:{value}" not in ids for value in inputs):
                    out.append(finding("SHOT_INPUTS", "Shot references a missing input asset", subject=ref))
                frames = item.get("duration_frames")
                if frames is not None and (not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0):
                    out.append(finding("SHOT_DURATION", "Shot duration_frames must be a positive integer", subject=ref))
    refs = subjects(doc)
    for group, asset_id in doc.get("selections", {}).items():
        if f"asset:{asset_id}" not in refs:
            out.append(finding("SELECTION_TARGET", "Selection must reference an existing asset",
                               subject=group))
    dependency_keys = set()
    for edge in doc.get("dependencies", []):
        if not isinstance(edge, dict) or edge.get("source") not in refs or edge.get("target") not in refs:
            out.append(finding("DEPENDENCY_TARGET", "Dependency source/target is missing"))
        elif not isinstance(edge.get("impact", "GENERIC"), str) or edge.get("impact", "GENERIC") not in IMPACTS:
            out.append(finding("DEPENDENCY_IMPACT", "Unknown dependency impact"))
        else:
            key = (edge["source"], edge["target"], edge.get("impact", "GENERIC"))
            if key in dependency_keys:
                out.append(finding("DUPLICATE_DEPENDENCY", "Duplicate dependency edge", subject=edge["target"]))
            dependency_keys.add(key)
    seen = set()
    for item in doc.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            out.append(finding("EVIDENCE_ID", "Evidence requires a nonempty id"))
            continue
        if item["id"] in seen:
            out.append(finding("DUPLICATE_EVIDENCE", "Duplicate evidence id", subject=item["id"]))
        seen.add(item["id"])
        if item.get("subject") not in refs or not isinstance(item.get("subject_hash"), str):
            out.append(finding("EVIDENCE_BINDING", "Evidence subject/hash is missing", subject=item["id"]))
        if item.get("status") not in {"PENDING", "APPROVED", "REJECTED", "STALE"}:
            out.append(finding("EVIDENCE_STATUS", "Evidence status is invalid", subject=item["id"]))
        if item.get("status") == "APPROVED":
            valid, reason = evidence_status(doc, kind=item.get("kind"), subject=item.get("subject"),
                                            snapshot=snapshot, action_id=item.get("action_id"),
                                            provider=item.get("provider"))
            if not valid:
                out.append(finding("STALE_EVIDENCE", reason, subject=item["id"]))
    for edge in doc.get("dependencies", []):
        if not isinstance(edge, dict) or edge.get("source") not in refs or edge.get("target") not in refs:
            continue
        source = refs[edge["source"]]
        target = refs[edge["target"]]
        if isinstance(source, dict) and source.get("lifecycle") in {"STALE", "MISSING", "SUPERSEDED"}:
            if isinstance(target, dict) and target.get("lifecycle", target.get("status")) not in {"STALE", "MISSING", "SUPERSEDED"}:
                out.append(finding("STALE_DEPENDENCY", "Dependent must be stale or remediated",
                                   subject=edge["target"]))
    try:
        history = engine.inspect_history()
    except (OSError, ValueError, SchemaError, RecoveryConflict) as exc:
        return ValidationResult(snapshot, tuple(out + [finding("CANONICAL_INTEGRITY", str(exc))]))
    for event in history:
        metadata = event.get("transition_metadata", {})
        if not isinstance(metadata, dict):
            out.append(finding("CHANGE_METADATA", "Transition metadata must be an object"))
            continue
        changes = metadata.get("changes", [])
        if not isinstance(changes, list):
            out.append(finding("CHANGE_METADATA", "changes must be a list"))
            changes = []
        if "change" in metadata:
            changes = [*changes, metadata["change"]]
        for change in changes:
            if (not isinstance(change, dict) or not isinstance(change.get("target"), str)
                    or not isinstance(change.get("dimensions"), list)
                    or not change["dimensions"] or any(d not in IMPACTS for d in change["dimensions"])):
                out.append(finding("CHANGE_METADATA", "Change declaration is malformed"))
                continue
            changed = change["target"]
            dimensions = change["dimensions"]
            if changed not in refs:
                continue
            for edge in doc.get("dependencies", []):
                if not isinstance(edge, dict) or edge.get("source") != changed or edge.get("target") not in refs:
                    continue
                impact = edge.get("impact", "GENERIC")
                if impact != "GENERIC" and "GENERIC" not in dimensions and impact not in dimensions:
                    continue
                target = refs[edge["target"]]
                if isinstance(target, dict) and target.get("lifecycle", target.get("status")) not in {"STALE", "MISSING", "SUPERSEDED"}:
                    revision = target.get("remediated_after_revision")
                    remediated = isinstance(revision, int) and not isinstance(revision, bool) and (
                        event["state_revision_after"] < revision <= snapshot.state_revision) and any(
                        later["state_revision_after"] == revision
                        and isinstance(later.get("transition_metadata"), dict)
                        and isinstance(later["transition_metadata"].get("remediation"), dict)
                        and later["transition_metadata"]["remediation"].get("target") == edge["target"]
                        for later in history)
                    if not remediated:
                        out.append(finding("MISSING_STALE_PROPAGATION", "Changed upstream dependency was not invalidated or remediated",
                                           subject=edge["target"]))
    return ValidationResult(snapshot, tuple(out))
