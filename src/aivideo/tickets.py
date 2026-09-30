"""Immutable execution intent and scoped canonical dependency fingerprints."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

from .validators import fingerprint, validate_project
from .state_engine import RecoveryConflict


SURFACES = frozenset({"CODEX_PLUGIN", "RAW_CLI", "WEB_MANUAL", "CANVAS_WEB",
                      "CHATGPT_ACTION", "OTHER_MANUAL"})
TRANSFORMS = frozenset({"EXACT", "ALLOW_OPTIMIZATION", "REQUIRED_PROVIDER_TRANSFORM"})
OPERATIONS = frozenset({"TEXT_TO_IMAGE", "IMAGE_EDIT", "TEXT_TO_VIDEO", "IMAGE_TO_VIDEO",
                        "FIRST_LAST_VIDEO", "REFERENCE_VIDEO", "MOTION_CONTROL",
                        "VIDEO_MODIFY", "VIDEO_EXTEND", "UPSCALE", "GENERATIVE_INSERT",
                        "AUDIO_GENERATE"})
UNKNOWN = "UNKNOWN"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return result


@dataclass(frozen=True)
class OperationCapability:
    operation: str
    model: str
    durations_seconds: tuple[int, ...] = ()
    resolutions: tuple[str, ...] = ()
    aspect_ratios: tuple[str, ...] = ()
    max_image_references: int | None = None
    supports_audio: bool | None = None

    def __post_init__(self):
        if self.operation not in OPERATIONS or not self.model:
            raise ValueError("invalid operation/model capability")
        if self.max_image_references is not None and self.max_image_references < 0:
            raise ValueError("invalid reference limit")


@dataclass(frozen=True)
class TechnicalCapabilitySnapshot:
    id: str
    provider: str
    backend: str
    captured_at: str
    expires_at: str
    operations: tuple[str, ...]
    models: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    native_evidence_ref: str | None = None
    idempotent_operations: tuple[str, ...] = ()
    trace_operations: tuple[str, ...] = ()
    operation_profiles: tuple[OperationCapability, ...] = ()

    def __post_init__(self):
        if not self.id or not self.provider or not self.backend or not self.operations:
            raise ValueError("technical capability identity and operations required")
        if set(self.operations) - OPERATIONS or set(self.idempotent_operations) - set(self.operations):
            raise ValueError("unknown or unproven operation")
        if set(self.trace_operations) - set(self.operations) or _time(self.expires_at) <= _time(self.captured_at):
            raise ValueError("invalid technical capability evidence")
        if any(profile.operation not in self.operations for profile in self.operation_profiles):
            raise ValueError("operation profile is not supported")
        if (self.idempotent_operations or self.trace_operations) and not self.native_evidence_ref:
            raise ValueError("provider idempotency/trace support requires native evidence reference")

    def fresh(self, now=None):
        now = now or datetime.now(timezone.utc)
        return _time(self.captured_at) <= now < _time(self.expires_at)

    def supports_idempotency(self, operation, backend, now=None):
        return self.fresh(now) and backend == self.backend and operation in self.idempotent_operations


@dataclass(frozen=True)
class AccountEntitlementSnapshot:
    id: str
    provider: str
    workspace_id: str
    captured_at: str
    expires_at: str
    authenticated: bool
    subscription_active: bool | None
    credits_available: float | None
    slots_available: int | None
    native_evidence_ref: str | None = None

    def __post_init__(self):
        if not self.id or not self.provider or not self.workspace_id or _time(self.expires_at) <= _time(self.captured_at):
            raise ValueError("invalid entitlement evidence")

    def fresh(self, now=None):
        now = now or datetime.now(timezone.utc)
        return _time(self.captured_at) <= now < _time(self.expires_at)


@dataclass(frozen=True)
class CanvasLiveState:
    provider_project_id: str
    schema_version: str
    edit_version: str
    base_edit_version: str | None
    captured_at: str

    def __post_init__(self):
        if not all((self.provider_project_id, self.schema_version, self.edit_version)):
            raise ValueError("Canvas identity/version required")
        _time(self.captured_at)


@dataclass(frozen=True)
class ProviderRuntimeSnapshot:
    id: str
    provider: str
    backend: str
    execution_surface: str
    workspace_id: str
    captured_at: str
    technical_snapshot_id: str
    entitlement_snapshot_id: str | None = None
    plugin_version: str | None = None
    cli_version: str | None = None
    region: str | None = None
    canvas: CanvasLiveState | None = None

    def __post_init__(self):
        if not all((self.id, self.provider, self.backend, self.workspace_id, self.technical_snapshot_id)):
            raise ValueError("runtime identity required")
        if self.execution_surface not in SURFACES:
            raise ValueError("invalid execution surface")
        _time(self.captured_at)


@dataclass(frozen=True)
class GenerationTicket:
    """A sealed JSON byte string; payload() returns a copy, never mutable authority."""

    raw: bytes
    id: str

    def payload(self):
        return json.loads(self.raw)

    def verify(self):
        return self.id == hashlib.sha256(self.raw).hexdigest()


def compile_ticket(engine, *, shot_id, candidate_id, provider, surface, workspace_id,
                   operation, mode, source_prompt, compiled_prompt, transform_policy,
                   technical: TechnicalCapabilitySnapshot, runtime: ProviderRuntimeSnapshot,
                   entitlement: AccountEntitlementSnapshot | None = None,
                   derivative_inputs=(), model=None, capability_requirements=(),
                   parameters=None, expected_output_id=None, qc_profile=None,
                   quote=None, external_processing_decision=None, approval_refs=(), strategy_id=None):
    validation = validate_project(engine)
    if not validation.ok:
        raise ValueError("canonical project is invalid")
    snapshot = validation.snapshot
    doc = snapshot.document
    shot = next((s for s in doc["shots"] if s.get("id") == shot_id), None)
    if shot is None or not candidate_id or not provider or not workspace_id:
        raise ValueError("ticket identity is incomplete")
    if surface not in SURFACES or operation not in OPERATIONS or transform_policy not in TRANSFORMS:
        raise ValueError("invalid execution contract")
    if not mode or not isinstance(source_prompt, str) or not isinstance(compiled_prompt, str):
        raise ValueError("prompt and operation mode required")
    if strategy_id is not None and (not isinstance(strategy_id, str) or not strategy_id.strip()):
        raise ValueError("strategy ID must be nonempty")
    if transform_policy == "EXACT" and source_prompt != compiled_prompt:
        raise ValueError("EXACT disallows prompt transformation")
    if (runtime.provider != provider or runtime.workspace_id != workspace_id or
            runtime.execution_surface != surface or runtime.technical_snapshot_id != technical.id or
            technical.provider != provider or technical.backend != runtime.backend):
        raise ValueError("runtime/capability binding mismatch")
    if operation not in technical.operations or not technical.fresh():
        raise ValueError("current technical capability unproven")
    if not set(capability_requirements).issubset(set(technical.features)):
        raise ValueError("required feature unproven")
    settings = parameters or {}
    if not isinstance(settings, dict):
        raise ValueError("parameters must be an object")
    if model is not None:
        profile = next((p for p in technical.operation_profiles
                        if p.operation == operation and p.model == model), None)
        if profile is None:
            raise ValueError("model/operation support unproven")
        checks = (("duration_seconds", profile.durations_seconds),
                  ("resolution", profile.resolutions), ("aspect_ratio", profile.aspect_ratios))
        for key, supported in checks:
            if key in settings and settings[key] not in supported:
                raise ValueError(f"{key} support unproven")
        if ("image_reference_count" in settings and
                (profile.max_image_references is None or
                 settings["image_reference_count"] > profile.max_image_references)):
            raise ValueError("image reference count unproven")
        if settings.get("audio") is True and profile.supports_audio is not True:
            raise ValueError("audio support unproven")
    if entitlement is not None and (entitlement.provider != provider or entitlement.workspace_id != workspace_id or
                                    runtime.entitlement_snapshot_id != entitlement.id):
        raise ValueError("entitlement binding mismatch")
    if entitlement is None and runtime.entitlement_snapshot_id is not None:
        raise ValueError("missing entitlement evidence")
    if quote is not None and (entitlement is None or not entitlement.fresh()):
        raise ValueError("paid ticket requires current entitlement evidence")
    if surface == "CANVAS_WEB" and runtime.canvas is None:
        raise ValueError("Canvas execution requires live edit-version evidence")
    if quote is not None and (not isinstance(quote, (int, float)) or isinstance(quote, bool) or quote < 0):
        raise ValueError("invalid quote")
    if external_processing_decision not in {"ALLOWED", "APPROVED_REVIEW", "NOT_APPLICABLE"}:
        raise ValueError("external-processing decision required")
    assets = {a["id"]: a for a in doc["assets"]}
    input_ids = shot.get("input_asset_ids", [])
    if len(set(input_ids)) != len(input_ids):
        raise ValueError("duplicate shot input")
    inputs = []
    for asset_id in input_ids:
        asset = assets.get(asset_id)
        if asset is None or asset.get("lifecycle") not in {"APPROVED", "FINAL"} or not asset.get("sha256"):
            raise ValueError("ticket input is unapproved or unverified")
        policy = asset.get("external_processing", {"policy": "REVIEW_REQUIRED"})
        if policy.get("policy") == "FORBIDDEN" or provider not in policy.get("allowed_providers", []):
            raise ValueError("provider upload forbidden for input")
        if policy.get("policy") == "REVIEW_REQUIRED" and external_processing_decision != "APPROVED_REVIEW":
            raise ValueError("external processing needs review")
        inputs.append({"asset_id": asset_id, "sha256": asset["sha256"]})
    derivatives = []
    derivative_sources = set()
    for item in derivative_inputs:
        source_id = item.get("source_asset_id")
        if source_id not in input_ids or item.get("source_sha256") != assets[source_id]["sha256"]:
            raise ValueError("derivative source binding mismatch")
        if source_id in derivative_sources:
            raise ValueError("only one provider-ready derivative may be selected per source")
        derivative_sources.add(source_id)
        if (not item.get("derivative_id") or
                not isinstance(item.get("derivative_sha256"), str) or
                not SHA256.fullmatch(item["derivative_sha256"]) or
                not isinstance(item.get("transform_fingerprint"), str) or
                not SHA256.fullmatch(item["transform_fingerprint"])):
            raise ValueError("derivative requires deterministic lineage")
        derivatives.append({k: item[k] for k in ("source_asset_id", "source_sha256", "derivative_id",
                                                  "derivative_sha256", "transform_fingerprint")})
    refs = {f"shot:{shot_id}": fingerprint(shot)}
    refs.update({f"asset:{asset_id}": fingerprint(assets[asset_id]) for asset_id in input_ids})
    for edge in doc.get("dependencies", []):
        if edge.get("target") == f"shot:{shot_id}" and edge.get("source", "").startswith("asset:"):
            asset_id = edge["source"].split(":", 1)[1]
            if asset_id in assets:
                refs[edge["source"]] = fingerprint(assets[asset_id])
    relevant_edges = sorted((edge for edge in doc.get("dependencies", [])
                             if edge.get("target") == f"shot:{shot_id}"), key=lambda edge: json.dumps(edge, sort_keys=True))
    payload = {"version": "1.0", "project_id": doc["project_id"], "state_revision": snapshot.state_revision,
               "project_hash": snapshot.project_hash, "dependency_hashes": refs,
               "dependency_edges_hash": fingerprint(relevant_edges), "shot_id": shot_id,
               "candidate_id": candidate_id, "provider": provider, "execution_surface": surface,
               "workspace_id": workspace_id, "backend": runtime.backend,
               "operation": operation, "mode": mode,
               "inputs": inputs, "derivative_inputs": derivatives,
               "prompt": {"source": source_prompt, "compiled": compiled_prompt,
                          "transform_policy": transform_policy},
               "model": model, "capability_requirements": list(capability_requirements),
               "parameters": settings, "technical_snapshot_id": technical.id,
               "technical_snapshot_hash": _digest(asdict(technical)),
               "entitlement_snapshot_id": entitlement.id if entitlement else None,
               "entitlement_snapshot_hash": _digest(asdict(entitlement)) if entitlement else None,
               "runtime_snapshot_id": runtime.id, "runtime_snapshot_hash": _digest(asdict(runtime)),
               "quote": quote,
               "external_processing_decision": external_processing_decision,
               "approval_refs": list(approval_refs), "expected_output_id": expected_output_id,
               "qc_profile": qc_profile, "strategy_id": strategy_id}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return GenerationTicket(raw, hashlib.sha256(raw).hexdigest())


def ticket_staleness(ticket: GenerationTicket, engine):
    if not ticket.verify():
        return ("TICKET_TAMPERED",)
    try:
        snapshot = engine.inspect_consistency()
    except (OSError, ValueError, RecoveryConflict):
        return ("CANONICAL_INVALID",)
    if snapshot.access != "WRITABLE_VERSION":
        return ("CANONICAL_INVALID",)
    doc = snapshot.document
    data = ticket.payload()
    if doc["project_id"] != data["project_id"]:
        return ("PROJECT_CHANGED",)
    refs = {f"shot:{item['id']}": item for item in doc["shots"]}
    refs.update({f"asset:{item['id']}": item for item in doc["assets"]})
    changed = [ref for ref, digest in data["dependency_hashes"].items()
               if ref not in refs or fingerprint(refs[ref]) != digest]
    relevant_edges = sorted((edge for edge in doc.get("dependencies", [])
                             if edge.get("target") == f"shot:{data['shot_id']}"), key=lambda edge: json.dumps(edge, sort_keys=True))
    if fingerprint(relevant_edges) != data["dependency_edges_hash"]:
        changed.append("DEPENDENCY_EDGES")
    return tuple(sorted(changed))
