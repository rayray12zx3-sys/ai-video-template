"""Offline PixVerse discovery evidence. This module never invokes a provider."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re

from .tickets import (AccountEntitlementSnapshot, OperationCapability,
                      ProviderRuntimeSnapshot, TechnicalCapabilitySnapshot, UNKNOWN)


SURFACE_ORDER = ("CODEX_PLUGIN", "RAW_CLI")
BACKENDS = {"CODEX_PLUGIN": "PLUGIN_WRAPPER", "RAW_CLI": "RAW_CLI",
            "WEB_MANUAL": "WEB_MANUAL"}
STATES = frozenset({"YES", "NO", UNKNOWN})
EVIDENCE_REF = re.compile(r"^[A-Z][A-Z0-9_.:-]{1,119}$")
PUBLIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+-]{0,63}$")
SECRET_PREFIXES = ("sk-", "pk-", "eyj", "bearer", "token", "secret")


@dataclass(frozen=True)
class SurfaceEvidence:
    surface: str
    installed: str = UNKNOWN
    executable: str = UNKNOWN
    authenticated: str = UNKNOWN
    entitled: str = UNKNOWN
    capability_proven: str = UNKNOWN
    workspace_resolved: str = UNKNOWN
    evidence: tuple[str, ...] = ()

    def __post_init__(self):
        if self.surface not in BACKENDS or any(
            value not in STATES for value in (self.installed, self.executable,
                self.authenticated, self.entitled, self.capability_proven,
                self.workspace_resolved)
        ):
            raise ValueError("invalid discovery evidence")
        if any(not EVIDENCE_REF.fullmatch(item) for item in self.evidence):
            raise ValueError("evidence must be a non-secret reference code")

    @property
    def execution_ready(self):
        return all(getattr(self, field) == "YES" for field in
                   ("installed", "executable", "authenticated", "entitled",
                    "capability_proven", "workspace_resolved"))

    @property
    def status(self):
        if self.execution_ready:
            return "READY"
        if self.installed == "NO" or self.executable == "NO":
            return "UNAVAILABLE"
        if self.authenticated == "NO":
            return "AUTH_REQUIRED"
        return "BLOCKED"


def preferred_surface(probes):
    """Only proven local routes outrank the manual fallback recommendation."""
    by_surface = {probe.surface: probe for probe in probes}
    if len(by_surface) != len(probes):
        raise ValueError("duplicate execution surface")
    for surface in SURFACE_ORDER:
        probe = by_surface.get(surface)
        if probe is not None and probe.execution_ready:
            return surface
    return "WEB_MANUAL"


def _public(value):
    """Copy only supported scalar/collection values; never serialize raw CLI output."""
    if value is None:
        return UNKNOWN
    if isinstance(value, str):
        if not PUBLIC_ID.fullmatch(value) or value.lower().startswith(SECRET_PREFIXES):
            raise ValueError("unreviewed or secret-shaped discovery value")
        return value
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return [_public(item) for item in value]
    raise ValueError("unsupported discovery value")


def _profiles(items):
    if items is None:
        return UNKNOWN
    allowed = {"operation", "model", "durations_seconds", "resolutions",
               "aspect_ratios", "max_image_references", "supports_audio"}
    if not isinstance(items, (list, tuple)):
        raise ValueError("profiles must be a collection")
    if any(not isinstance(item, dict) or set(item) - allowed for item in items):
        raise ValueError("unsupported profile field")
    return [{key: _public(value) for key, value in item.items()} for item in items]


def _canvas(item):
    if item is None:
        return UNKNOWN
    allowed = {"provider_project_id", "schema_version", "edit_version",
               "base_edit_version", "captured_at"}
    if not isinstance(item, dict) or set(item) - allowed:
        raise ValueError("unsupported Canvas field")
    return {key: _public(value) for key, value in item.items()}


def snapshot_candidate(*, probes, captured_at, evidence_source,
                       evidence_surface=None,
                       plugin_version=None, cli_version=None, region=None,
                       workspace_id=None, operations=None, models=None,
                       profiles=None, idempotent_operations=None,
                       trace_operations=None, authenticated=None,
                       subscription_active=None, credits_available=None,
                       slots_available=None, canvas=None):
    """Sanitized, non-authoritative evidence; UNKNOWN never becomes a capability.

    The caller supplies already-reviewed facts, not raw command/account payloads.
    A candidate cannot be passed to compile_ticket as a trusted preflight.
    """
    captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    if captured.tzinfo is None:
        raise ValueError("captured_at requires timezone")
    if not isinstance(evidence_source, str) or not EVIDENCE_REF.fullmatch(evidence_source):
        raise ValueError("evidence_source must be a non-secret reference code")
    preferred = preferred_surface(probes)
    account_facts = (authenticated, subscription_active, credits_available,
                     slots_available)
    technical_facts = (operations, models, profiles, idempotent_operations,
                       trace_operations)
    if any(item is not None for item in account_facts + technical_facts + (workspace_id, canvas)):
        if (preferred not in SURFACE_ORDER or evidence_surface != preferred
                or workspace_id is None):
            raise ValueError("live evidence must bind selected local surface and explicit workspace")
        source_probe = next((probe for probe in probes if probe.surface == preferred), None)
        if source_probe is None or not source_probe.execution_ready:
            raise ValueError("live evidence requires a ready source surface")
    expires = (captured + timedelta(hours=1)).isoformat()
    evidence = {
        "provider": "pixverse", "captured_at": captured.isoformat(),
        "expires_at": expires, "freshness_policy": "refresh before ticket or paid preflight",
        "evidence_source": _public(evidence_source),
        "evidence_surface": _public(evidence_surface),
        "surfaces": [asdict(p) | {"execution_ready": p.execution_ready,
                                "status": p.status} for p in probes],
        "preferred_surface": preferred,
        "installed_plugin_version": _public(plugin_version),
        "technical": {"backend": BACKENDS[preferred],
                      "operations": _public(operations), "models": _public(models),
                      "profiles": _profiles(profiles),
                      "idempotent_operations": _public(idempotent_operations),
                      "trace_operations": _public(trace_operations)},
        "entitlement": {"authenticated": _public(authenticated),
                        "subscription_active": _public(subscription_active),
                        "credits_available": _public(credits_available),
                        "slots_available": _public(slots_available)},
        "runtime": {"execution_surface": preferred, "backend": BACKENDS[preferred],
                    "workspace_id": _public(workspace_id),
                    "plugin_version": _public(plugin_version if preferred == "CODEX_PLUGIN" else None),
                    "cli_version": _public(cli_version if preferred in SURFACE_ORDER else None),
                    "region": _public(region if preferred in SURFACE_ORDER else None)},
        "canvas_live_state": _canvas(canvas),
        "trusted_preflight": False,
    }
    # No caller-controlled keys are copied; use content-derived ID for audit binding.
    payload = json.dumps(evidence, sort_keys=True, ensure_ascii=False, allow_nan=False)
    evidence["id"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return evidence


def i3_snapshots(candidate, *, native_evidence_ref):
    """Convert proven evidence to I3 types; deny incomplete discovery."""
    content = {key: value for key, value in candidate.items() if key != "id"}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False,
                                      allow_nan=False).encode("utf-8")).hexdigest()
    if candidate.get("id") != digest or candidate.get("trusted_preflight") is not False:
        raise ValueError("discovery candidate is altered or misclassified")
    runtime = candidate["runtime"]
    technical = candidate["technical"]
    entitlement = candidate["entitlement"]
    surface = runtime["execution_surface"]
    if (surface not in SURFACE_ORDER or runtime["workspace_id"] == UNKNOWN
            or technical["operations"] == UNKNOWN
            or not technical["operations"] or not native_evidence_ref):
        raise ValueError("provider evidence incomplete for I3")
    if (candidate["preferred_surface"] != surface
            or candidate["evidence_surface"] != surface
            or technical["backend"] != BACKENDS.get(surface)
            or runtime["backend"] != BACKENDS.get(surface)):
        raise ValueError("discovery source/backend binding mismatch")
    if not isinstance(runtime["workspace_id"], str):
        raise ValueError("invalid explicit workspace ID")
    _public(runtime["workspace_id"])
    probe = next((item for item in candidate["surfaces"] if item["surface"] == surface), None)
    if probe is None or not probe["execution_ready"]:
        raise ValueError("execution surface is not ready")
    if (entitlement["authenticated"] is not True
            or entitlement["subscription_active"] is not True
            or not isinstance(entitlement["slots_available"], int)
            or isinstance(entitlement["slots_available"], bool)
            or entitlement["slots_available"] < 1):
        raise ValueError("entitlement evidence incomplete")
    profiles = tuple(OperationCapability(**item) for item in
                     (technical["profiles"] if technical["profiles"] != UNKNOWN else ()))
    prefix = candidate["id"]
    cap = TechnicalCapabilitySnapshot(
        id=f"{prefix}:technical", provider="pixverse", backend=runtime["backend"],
        captured_at=candidate["captured_at"], expires_at=candidate["expires_at"],
        operations=tuple(technical["operations"]),
        models=tuple(technical["models"] if technical["models"] != UNKNOWN else ()),
        native_evidence_ref=native_evidence_ref,
        idempotent_operations=tuple(technical["idempotent_operations"]
                                    if technical["idempotent_operations"] != UNKNOWN else ()),
        trace_operations=tuple(technical["trace_operations"]
                               if technical["trace_operations"] != UNKNOWN else ()),
        operation_profiles=profiles)
    account = AccountEntitlementSnapshot(
        id=f"{prefix}:entitlement", provider="pixverse",
        workspace_id=runtime["workspace_id"],
        captured_at=candidate["captured_at"], expires_at=candidate["expires_at"],
        authenticated=True, subscription_active=entitlement["subscription_active"],
        credits_available=None if entitlement["credits_available"] == UNKNOWN else entitlement["credits_available"],
        slots_available=entitlement["slots_available"])
    provider_runtime = ProviderRuntimeSnapshot(
        id=f"{prefix}:runtime", provider="pixverse", backend=runtime["backend"],
        execution_surface=surface, workspace_id=runtime["workspace_id"],
        captured_at=candidate["captured_at"], technical_snapshot_id=cap.id,
        entitlement_snapshot_id=account.id,
        plugin_version=None if runtime["plugin_version"] == UNKNOWN else runtime["plugin_version"],
        cli_version=None if runtime["cli_version"] == UNKNOWN else runtime["cli_version"],
        region=None if runtime["region"] == UNKNOWN else runtime["region"])
    return cap, account, provider_runtime
