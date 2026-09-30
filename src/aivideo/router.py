"""Deterministic, provider-neutral production routing from canonical shot facts."""

from dataclasses import dataclass


METHODS = frozenset({"AUTO", "AI_IMAGE", "AI_VIDEO", "SOURCE_IMAGE", "SOURCE_VIDEO",
                     "STATIC", "PREMIERE", "AFTER_EFFECTS", "COMPOSITE", "DERIVED",
                     "NO_NEW_MEDIA"})


@dataclass(frozen=True)
class RouteReport:
    shot_id: str
    method: str
    previs: str
    owner: str
    reasons: tuple[str, ...]
    eligible_operations: tuple[str, ...] = ()


def route_shot(shot: dict, assets: tuple[dict, ...] = (), capabilities: tuple[object, ...] = ()) -> RouteReport:
    """Recommend a method; capability gaps leave AI routing unresolved."""
    if not isinstance(shot, dict) or not isinstance(shot.get("id"), str) or not shot["id"]:
        raise ValueError("shot requires an ID")
    requested = shot.get("production_method", "AUTO")
    if requested not in METHODS:
        raise ValueError("unknown production method")
    requirements = shot.get("requirements", {})
    constraints = shot.get("constraints", {})
    if not isinstance(requirements, dict) or not isinstance(constraints, dict):
        raise ValueError("requirements and constraints must be objects")
    requested_features = requirements.get("required_features", ())
    if (not isinstance(requested_features, (tuple, list, set, frozenset)) or
            any(not isinstance(feature, str) or not feature for feature in requested_features)):
        raise ValueError("required_features must be a collection of feature names")
    asset_ids = set(shot.get("input_asset_ids", []))
    relevant_assets = [a for a in assets if a.get("id") in asset_ids]
    if len({a.get("id") for a in relevant_assets}) != len(asset_ids):
        raise ValueError("shot input assets are missing")
    approved = [a for a in relevant_assets if a.get("lifecycle") in {"APPROVED", "FINAL"}]
    visual_refs = [a for a in approved if a.get("media_type") in {"IMAGE", "VIDEO"}]
    owner = shot.get("error_owner", "GENERATION")
    if owner not in {"STORY", "SOURCE", "REFERENCE", "PREVIS", "GENERATION", "POST"}:
        raise ValueError("unknown error owner")
    reasons = []
    camera = requirements.get("camera", {})
    complex_camera = isinstance(camera, dict) and bool(camera.get("complex_geometry") or camera.get("lens_sensitive"))
    complex_motion = requirements.get("motion_complexity") == "HIGH"
    structural = (requirements.get("structure_sensitivity") == "HIGH" or
                  bool(constraints.get("spatial_relations")) or bool(constraints.get("interaction")))
    previs = "MOTION_3D" if complex_camera and complex_motion else "STATIC_3D" if complex_camera or structural else "NONE"
    if owner == "REFERENCE":
        return RouteReport(shot["id"], "AUTO", previs, owner, ("REFERENCE_ERROR_REQUIRES_REFERENCE_REPAIR",))
    if owner == "PREVIS":
        return RouteReport(shot["id"], "AUTO", previs, owner, ("PREVIS_ERROR_REQUIRES_PREVIS_REPAIR",))
    if requested != "AUTO":
        method = requested
        reasons.append("EXPLICIT_CANONICAL_METHOD")
    elif shot.get("new_media_required") is False:
        method = "NO_NEW_MEDIA"
        reasons.append("NO_NEW_MEDIA_REQUIRED")
    elif any(a.get("content_role") == "UI" or a.get("origin") == "REAL_UI" for a in approved):
        method = "SOURCE_VIDEO" if any(a.get("media_type") == "VIDEO" for a in approved) else "SOURCE_IMAGE"
        reasons.append("REAL_UI_USES_SOURCE")
    elif shot.get("editorial_only"):
        method = "PREMIERE"
        reasons.append("EDITORIAL_ONLY")
    elif shot.get("compositing_required") or constraints.get("exact_text"):
        method = "COMPOSITE"
        reasons.append("EXACT_CONTENT_OR_COMPOSITING")
    elif shot.get("motion_graphics"):
        method = "AFTER_EFFECTS"
        reasons.append("MOTION_GRAPHICS")
    elif shot.get("derived_from"):
        method = "DERIVED"
        reasons.append("EXISTING_MEDIA_DERIVATION")
    elif shot.get("motion_required") is False:
        method = "STATIC"
        reasons.append("MOTION_NOT_REQUIRED")
    elif approved and any(a.get("media_type") == "VIDEO" for a in approved) and shot.get("use_source_media"):
        method = "SOURCE_VIDEO"
        reasons.append("APPROVED_SOURCE_VIDEO")
    else:
        method = "AI_VIDEO" if shot.get("motion_required", True) else "AI_IMAGE"
        reasons.append("GENERATIVE_MEDIA_REQUIRED")
    if previs != "NONE":
        reasons.append("PREVIS_RECOMMENDED")
    operations = ()
    if method in {"AI_IMAGE", "AI_VIDEO"}:
        if requirements.get("identity_sensitivity") == "HIGH":
            if not visual_refs:
                reasons.append("IDENTITY_REFERENCE_REQUIRED")
                return RouteReport(shot["id"], "AUTO", previs, owner, tuple(reasons))
            reasons.append("IDENTITY_REFERENCE_FIRST")
        if requirements.get("expression_sensitivity") == "HIGH":
            reasons.append("EXPRESSION_SENSITIVE")
        if requirements.get("continuity_sensitivity") == "HIGH":
            reasons.append("CONTINUITY_REVIEW_REQUIRED")
        if any(a.get("external_processing", {}).get("policy", "REVIEW_REQUIRED") == "FORBIDDEN"
               for a in approved):
            reasons.append("EXTERNAL_PROCESSING_FORBIDDEN")
            return RouteReport(shot["id"], "AUTO", previs, owner, tuple(reasons))
        if any(a.get("external_processing", {}).get("policy", "REVIEW_REQUIRED") == "REVIEW_REQUIRED"
               for a in approved):
            reasons.append("EXTERNAL_PROCESSING_REVIEW_REQUIRED")
        operation = ("IMAGE_TO_VIDEO" if method == "AI_VIDEO" and visual_refs else
                     "TEXT_TO_VIDEO" if method == "AI_VIDEO" else "TEXT_TO_IMAGE")
        features = set(requested_features)
        available = sorted({op for cap in capabilities if callable(getattr(cap, "fresh", None)) and cap.fresh()
                            and features.issubset(set(getattr(cap, "features", ())))
                            for op in getattr(cap, "operations", ())})
        if operation not in available:
            reasons.append("CAPABILITY_UNPROVEN")
            return RouteReport(shot["id"], "AUTO", previs, owner, tuple(reasons))
        operations = (operation,)
    return RouteReport(shot["id"], method, previs, owner, tuple(reasons), operations)


def plan_shots(shots: tuple[dict, ...], assets: tuple[dict, ...] = (),
               capabilities: tuple[object, ...] = ()) -> tuple[RouteReport, ...]:
    """Derived production plan in canonical shot order; never writes project state."""
    return tuple(route_shot(shot, assets, capabilities) for shot in shots)
