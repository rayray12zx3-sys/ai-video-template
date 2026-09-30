"""Pure, deterministic legacy project importer and dry-run report builder.

Consumes repository-safe sanitized legacy fixture format `legacy-project-sanitized-v1`
and produces a current-schema v2 canonical document candidate + dry-run report.
Does not mutate canonical state or input fixtures.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any, Dict, List, Tuple

from .schema import validate, CURRENT_PROJECT_SCHEMA


LEGACY_FORMAT = "legacy-project-sanitized-v1"

RECOGNIZED_TOP_LEVEL_KEYS = {
    "format",
    "fixture_id",
    "project",
    "assets",
    "shots",
    "dependencies",
    "selections",
    "evidence",
    "approvals",
    "legacy_records",
    "unknown_fields",
}

RECOGNIZED_PROJECT_KEYS = {
    "legacy_project_id",
    "project_id",
    "mode_hint",
    "mode",
    "workflow_status_hint",
    "workflow_status",
    "interaction_mode",
    "template_version",
    "state_revision",
    "next_action",
    "brief",
    "storyboard",
    "animatic",
    "generation_plan",
    "final_qc",
    "selections",
}

RECOGNIZED_ASSET_KEYS = {
    "id",
    "media_type",
    "origin",
    "content_role",
    "lifecycle",
    "sha256",
    "selected",
    "criticality",
    "request_state",
    "reupload_reason",
    "external_processing",
    "locators",
    "provenance",
    "media_metadata",
    "provider_task_id",
    "lineage",
}

RECOGNIZED_SHOT_KEYS = {
    "id",
    "duration_frames",
    "intent",
    "input_asset_ids",
    "production_method",
    "readiness",
    "new_media_required",
    "editorial_only",
    "error_owner",
    "requirements",
    "constraints",
}


def _fingerprint(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _is_absolute_path(path_str: str) -> bool:
    if not isinstance(path_str, str):
        return False
    return (PurePosixPath(path_str).is_absolute()
            or PureWindowsPath(path_str).is_absolute()
            or bool(re.search(r"(?i)(?<![a-z0-9])(?:[a-z]:[\\/]|\\\\)|(?<![a-z0-9:/])/(?!/|\s)", path_str)))


def _safe_copy(value: Any, location: str, redactions: List[Dict[str, Any]]) -> Any:
    """Retain JSON fixture values while removing machine paths from every output surface."""
    if isinstance(value, dict):
        result = {}
        for key in sorted(value):
            if not isinstance(key, str) or _is_absolute_path(key):
                raise ValueError("Fixture keys must be repository-safe strings")
            result[key] = _safe_copy(value[key], f"{location}.{key}" if location else key, redactions)
        return result
    if isinstance(value, list):
        return [_safe_copy(item, f"{location}[{idx}]", redactions)
                for idx, item in enumerate(value)]
    if isinstance(value, str) and _is_absolute_path(value):
        redactions.append({
            "code": "ABSOLUTE_PATH_REDACTED",
            "source_key": location,
            "disposition": "REDACTED",
            "message": "Absolute or private machine path redacted",
        })
        return "REDACTED"
    return value


def _leaf_values(value: Any, location: str):
    """Walk each source fact once, including empty collections."""
    if isinstance(value, dict) and value:
        for key in sorted(value):
            yield from _leaf_values(value[key], f"{location}.{key}" if location else key)
    elif isinstance(value, list) and value:
        for idx, item in enumerate(value):
            yield from _leaf_values(item, f"{location}[{idx}]")
    else:
        yield location, value


def _source_accounting(src, mapped, evidence, unresolved, redactions):
    """Assign one disposition to every sanitized source leaf."""
    entries = []
    for collection in (mapped, evidence, unresolved, redactions):
        entries.extend(collection)
    result = []
    for location, value in _leaf_values(src, ""):
        matches = [item for item in entries
                   if location == item["source_key"]
                   or location.startswith(item["source_key"] + ".")
                   or location.startswith(item["source_key"] + "[")]
        if matches:
            priority = {"MAPPED": 0, "EVIDENCE_ONLY": 1,
                        "UNRESOLVED": 2, "REDACTED": 3}
            best = max(matches, key=lambda item: (len(item["source_key"]),
                                                   priority[item["disposition"]]))
            disposition = best["disposition"]
        elif location == "format":
            disposition = "EVIDENCE_ONLY"
        elif location in {"evidence", "approvals", "legacy_records"}:
            disposition = "EVIDENCE_ONLY"  # Empty supporting-evidence collections.
        elif location.split(".")[0].split("[")[0] in {"assets", "shots", "dependencies"}:
            disposition = "MAPPED"  # Empty collections map to the candidate's empty arrays.
        else:
            disposition = "UNRESOLVED"
        result.append({"source_key": location, "disposition": disposition,
                       "value": value})
    return result


def import_legacy_project(fixture: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Pure, deterministic importer. Accepts a legacy fixture dict and returns (candidate, report)."""
    if not isinstance(fixture, dict):
        raise ValueError("Legacy fixture must be an object")

    if fixture.get("format") != LEGACY_FORMAT:
        raise ValueError(f"Unsupported or missing legacy format; expected {LEGACY_FORMAT}")

    mapped_items: List[Dict[str, Any]] = []
    evidence_only_items: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    unresolved_items: List[Dict[str, Any]] = []
    redactions: List[Dict[str, Any]] = []
    source_fingerprint = _fingerprint(fixture)
    src = _safe_copy(fixture, "", redactions)

    # 1. Project mapping
    proj_src = src.get("project", {})
    if not isinstance(proj_src, dict):
        raise ValueError("Project section must be an object")

    project_id = proj_src.get("project_id") or proj_src.get("legacy_project_id") or "legacy-project"
    mode = proj_src.get("mode") or proj_src.get("mode_hint") or "NEW_PRODUCTION"
    workflow_status = proj_src.get("workflow_status") or proj_src.get("workflow_status_hint") or "ACTIVE"

    candidate: Dict[str, Any] = {
        "schema_version": CURRENT_PROJECT_SCHEMA,
        "template_version": proj_src.get("template_version", "2.0"),
        "project_id": project_id,
        "state_revision": proj_src.get("state_revision", 0),
        "mode": mode,
        "interaction_mode": proj_src.get("interaction_mode", "DISCOVERY"),
        "next_action": proj_src.get("next_action") or "Imported legacy project record pending state adoption",
        "workflow_status": workflow_status,
        "assets": [],
        "shots": [],
        "dependencies": [],
    }

    mapped_items.append({
        "code": "PROJECT_METADATA_MAPPED",
        "source_key": "project",
        "target_location": "$",
        "disposition": "MAPPED",
        "message": f"Mapped project '{project_id}' in mode '{mode}'",
    })

    if "fixture_id" in src:
        evidence_only_items.append({
            "code": "FIXTURE_ID_RETAINED", "source_key": "fixture_id",
            "disposition": "EVIDENCE_ONLY", "value": src["fixture_id"],
            "message": "Sanitized fixture identity retained for provenance",
        })

    # Both the selected and overridden legacy hints must remain accounted for.
    project_targets = {
        "project_id": "project_id", "legacy_project_id": "project_id",
        "mode": "mode", "mode_hint": "mode",
        "workflow_status": "workflow_status", "workflow_status_hint": "workflow_status",
        "template_version": "template_version", "state_revision": "state_revision",
        "interaction_mode": "interaction_mode", "next_action": "next_action",
    }
    preferred = {
        "project_id": "project_id" if proj_src.get("project_id") else "legacy_project_id",
        "mode": "mode" if proj_src.get("mode") else "mode_hint",
        "workflow_status": "workflow_status" if proj_src.get("workflow_status") else "workflow_status_hint",
    }
    for key, target in project_targets.items():
        if key not in proj_src:
            continue
        if (key in preferred.values() or key == target) and candidate[target] == proj_src[key]:
            continue
        evidence_only_items.append({
            "code": "PROJECT_SOURCE_FIELD_RETAINED", "source_key": f"project.{key}",
            "disposition": "EVIDENCE_ONLY", "value": proj_src[key],
            "message": "Legacy project field retained without promotion",
        })

    for obj_key in ("brief", "storyboard", "animatic", "generation_plan", "final_qc"):
        if obj_key in proj_src and isinstance(proj_src[obj_key], dict):
            candidate[obj_key] = proj_src[obj_key]
            mapped_items.append({
                "code": "PROJECT_OBJECT_MAPPED",
                "source_key": f"project.{obj_key}",
                "target_location": f"$.{obj_key}",
                "disposition": "MAPPED",
                "message": f"Mapped top-level object '{obj_key}'",
            })
        elif obj_key in proj_src:
            unresolved_items.append({
                "code": "UNMAPPED_PROJECT_OBJECT", "source_key": f"project.{obj_key}",
                "disposition": "UNRESOLVED", "value": proj_src[obj_key],
                "message": "Project object could not be mapped", "blocking": False,
            })

    selections_src = proj_src.get("selections") or src.get("selections")
    if isinstance(selections_src, dict):
        candidate["selections"] = selections_src
        mapped_items.append({
            "code": "SELECTIONS_MAPPED",
            "source_key": "selections",
            "target_location": "$.selections",
            "disposition": "MAPPED",
            "message": "Mapped selections mapping",
        })
    for location, value in (("project.selections", proj_src.get("selections")),
                            ("selections", src.get("selections"))):
        if (location == "project.selections" and "selections" not in proj_src) or (
                location == "selections" and "selections" not in src):
            continue
        if value is selections_src and isinstance(value, dict):
            continue
        unresolved_items.append({
            "code": "UNMAPPED_SELECTIONS", "source_key": location,
            "disposition": "UNRESOLVED", "value": value,
            "message": "Selections not promoted to candidate", "blocking": False,
        })

    for k in proj_src:
        if k not in RECOGNIZED_PROJECT_KEYS:
            unresolved_items.append({
                "code": "UNRESOLVED_PROJECT_FIELD",
                "source_key": f"project.{k}",
                "disposition": "UNRESOLVED",
                "message": f"Unrecognized project field '{k}' retained in report",
                "blocking": False,
                "value": proj_src[k],
            })

    # 2. Asset Mapping
    assets_src = src.get("assets", [])
    if not isinstance(assets_src, list):
        raise ValueError("Assets section must be a list")

    known_asset_ids = set()
    for idx, asset in enumerate(assets_src):
        if not isinstance(asset, dict):
            unresolved_items.append({
                "code": "MALFORMED_ASSET_RECORD",
                "source_key": f"assets[{idx}]",
                "disposition": "UNRESOLVED",
                "message": "Asset item is not an object",
                "blocking": True,
                "value": asset,
            })
            continue

        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id:
            unresolved_items.append({
                "code": "MISSING_ASSET_ID",
                "source_key": f"assets[{idx}]",
                "disposition": "UNRESOLVED",
                "message": "Asset missing string 'id'",
                "blocking": True,
                "value": asset,
            })
            continue

        known_asset_ids.add(asset_id)
        asset_out: Dict[str, Any] = {"id": asset_id}

        for field in ("media_type", "origin", "content_role", "lifecycle", "sha256",
                      "selected", "criticality", "request_state", "reupload_reason",
                      "external_processing", "provenance", "media_metadata",
                      "provider_task_id", "lineage"):
            if field in asset and asset[field] is not None:
                asset_out[field] = asset[field]
            elif field in asset:
                unresolved_items.append({
                    "code": "UNMAPPED_ASSET_FIELD", "source_key": f"assets[{idx}].{field}",
                    "disposition": "UNRESOLVED", "value": asset[field],
                    "message": "Asset field could not be mapped", "blocking": False,
                })

        locators_src = asset.get("locators", [])
        if isinstance(locators_src, list):
            locators_out = []
            for loc_idx, loc in enumerate(locators_src):
                if isinstance(loc, dict):
                    loc_copy = deepcopy(loc)
                    path_val = loc_copy.get("path")
                    if path_val == "REDACTED" and any(
                            item["source_key"] == f"assets[{idx}].locators[{loc_idx}].path"
                            for item in redactions):
                        loc_copy["availability"] = "UNAVAILABLE"
                        unresolved_items.append({
                            "code": "REDACTED_LOCATOR_PATH",
                            "source_key": f"assets[{idx}].locators[{loc_idx}]",
                            "disposition": "UNRESOLVED",
                            "message": f"Asset '{asset_id}' locator path was redacted for safety",
                            "blocking": False,
                            "value": loc,
                        })
                    locators_out.append(loc_copy)
                else:
                    unresolved_items.append({
                        "code": "MALFORMED_LOCATOR_RECORD",
                        "source_key": f"assets[{idx}].locators[{loc_idx}]",
                        "disposition": "UNRESOLVED", "value": loc,
                        "message": "Locator item is not an object", "blocking": False,
                    })
            asset_out["locators"] = locators_out
        elif "locators" in asset:
            unresolved_items.append({
                "code": "UNMAPPED_ASSET_LOCATORS", "source_key": f"assets[{idx}].locators",
                "disposition": "UNRESOLVED", "value": locators_src,
                "message": "Asset locators are not a list", "blocking": False,
            })

        lifecycle = asset_out.get("lifecycle")
        if lifecycle in {"APPROVED", "FINAL"}:
            has_hash = isinstance(asset_out.get("sha256"), str) and len(asset_out["sha256"]) == 64
            has_prov = bool(asset_out.get("provenance"))
            durable_locs = [loc for loc in asset_out.get("locators", []) if isinstance(loc, dict)
                            and loc.get("type") in {"LOCAL", "GOOGLE_DRIVE", "ARCHIVE"}
                            and loc.get("availability") == "AVAILABLE"
                            and loc.get("path") != "REDACTED"]
            if not (has_hash and has_prov and durable_locs):
                demoted_lifecycle = "RECEIVED" if asset_out.get("origin") != "PROVIDER_OUTPUT" else "REVIEWED"
                asset_out["lifecycle"] = demoted_lifecycle
                unresolved_items.append({
                    "code": "LIFECYCLE_DEMOTED_INSUFFICIENT_EVIDENCE",
                    "source_key": f"assets[{idx}].lifecycle",
                    "disposition": "UNRESOLVED",
                    "message": f"Asset '{asset_id}' lifecycle demoted from '{lifecycle}' to '{demoted_lifecycle}' due to missing hash/provenance/locator evidence",
                    "blocking": False,
                    "value": lifecycle,
                })

        candidate["assets"].append(asset_out)
        mapped_items.append({
            "code": "ASSET_MAPPED",
            "source_key": f"assets[{idx}]",
            "target_location": f"$.assets[?(@.id=='{asset_id}')]",
            "disposition": "MAPPED",
            "message": f"Mapped asset '{asset_id}'",
        })

        for k in asset:
            if k not in RECOGNIZED_ASSET_KEYS:
                unresolved_items.append({
                    "code": "UNRESOLVED_ASSET_FIELD",
                    "source_key": f"assets[{idx}].{k}",
                    "disposition": "UNRESOLVED",
                    "message": f"Unrecognized field '{k}' on asset '{asset_id}' retained in report",
                    "blocking": False,
                    "value": asset[k],
                })

    # 3. Shot Mapping
    shots_src = src.get("shots", [])
    if not isinstance(shots_src, list):
        raise ValueError("Shots section must be a list")

    known_shot_ids = set()
    for idx, shot in enumerate(shots_src):
        if not isinstance(shot, dict):
            unresolved_items.append({
                "code": "MALFORMED_SHOT_RECORD",
                "source_key": f"shots[{idx}]",
                "disposition": "UNRESOLVED",
                "message": "Shot item is not an object",
                "blocking": True,
                "value": shot,
            })
            continue

        shot_id = shot.get("id")
        if not isinstance(shot_id, str) or not shot_id:
            unresolved_items.append({
                "code": "MISSING_SHOT_ID",
                "source_key": f"shots[{idx}]",
                "disposition": "UNRESOLVED",
                "message": "Shot missing string 'id'",
                "blocking": True,
                "value": shot,
            })
            continue

        known_shot_ids.add(shot_id)
        shot_out: Dict[str, Any] = {"id": shot_id}

        for field in ("duration_frames", "intent", "input_asset_ids", "production_method",
                      "readiness", "new_media_required", "editorial_only", "error_owner",
                      "requirements", "constraints"):
            if field in shot and shot[field] is not None:
                shot_out[field] = shot[field]
            elif field in shot:
                unresolved_items.append({
                    "code": "UNMAPPED_SHOT_FIELD", "source_key": f"shots[{idx}].{field}",
                    "disposition": "UNRESOLVED", "value": shot[field],
                    "message": "Shot field could not be mapped", "blocking": False,
                })

        candidate["shots"].append(shot_out)
        mapped_items.append({
            "code": "SHOT_MAPPED",
            "source_key": f"shots[{idx}]",
            "target_location": f"$.shots[?(@.id=='{shot_id}')]",
            "disposition": "MAPPED",
            "message": f"Mapped shot '{shot_id}'",
        })

        for k in shot:
            if k not in RECOGNIZED_SHOT_KEYS:
                unresolved_items.append({
                    "code": "UNRESOLVED_SHOT_FIELD",
                    "source_key": f"shots[{idx}].{k}",
                    "disposition": "UNRESOLVED",
                    "message": f"Unrecognized field '{k}' on shot '{shot_id}' retained in report",
                    "blocking": False,
                    "value": shot[k],
                })

    # 4. Dependencies Mapping
    deps_src = src.get("dependencies", [])
    if not isinstance(deps_src, list):
        raise ValueError("Dependencies section must be a list")

    valid_subjects = {f"project:{name}" for name in ("brief", "storyboard", "animatic", "generation_plan", "final_qc")}
    valid_subjects.update(f"asset:{aid}" for aid in known_asset_ids)
    valid_subjects.update(f"shot:{sid}" for sid in known_shot_ids)

    for idx, dep in enumerate(deps_src):
        if not isinstance(dep, dict):
            unresolved_items.append({
                "code": "MALFORMED_DEPENDENCY_RECORD",
                "source_key": f"dependencies[{idx}]",
                "disposition": "UNRESOLVED",
                "message": "Dependency item is not an object",
                "blocking": True,
                "value": dep,
            })
            continue

        src_ref = dep.get("source")
        tgt_ref = dep.get("target")
        impact = dep.get("impact", "GENERIC")

        if (isinstance(src_ref, str) and isinstance(tgt_ref, str)
                and src_ref in valid_subjects and tgt_ref in valid_subjects):
            candidate["dependencies"].append({
                "source": src_ref,
                "target": tgt_ref,
                "impact": impact,
            })
            mapped_items.append({
                "code": "DEPENDENCY_MAPPED",
                "source_key": f"dependencies[{idx}]",
                "target_location": f"$.dependencies[{len(candidate['dependencies']) - 1}]",
                "disposition": "MAPPED",
                "message": f"Mapped dependency {src_ref} -> {tgt_ref}",
            })
        else:
            unresolved_items.append({
                "code": "DANGLING_DEPENDENCY_OMITTED",
                "source_key": f"dependencies[{idx}]",
                "disposition": "UNRESOLVED",
                "message": f"Dependency {src_ref} -> {tgt_ref} omitted because source/target is missing",
                "blocking": False,
                "value": dep,
            })

        for key in dep:
            if key not in {"source", "target", "impact"}:
                unresolved_items.append({
                    "code": "UNRESOLVED_DEPENDENCY_FIELD",
                    "source_key": f"dependencies[{idx}].{key}",
                    "disposition": "UNRESOLVED", "value": dep[key],
                    "message": "Unrecognized dependency field retained", "blocking": False,
                })

    # 5. Evidence & Approvals Mapping
    evidence_src = src.get("evidence", [])
    if isinstance(evidence_src, list) and evidence_src:
        candidate_evidence = []
        for idx, ev in enumerate(evidence_src):
            if (isinstance(ev, dict) and isinstance(ev.get("subject"), str)
                    and ev.get("id") and ev["subject"] in valid_subjects
                    and ev.get("subject_hash")):
                candidate_evidence.append(ev)
                mapped_items.append({
                    "code": "EVIDENCE_MAPPED",
                    "source_key": f"evidence[{idx}]",
                    "target_location": f"$.evidence[?(@.id=='{ev['id']}')]",
                    "disposition": "MAPPED",
                    "message": f"Mapped evidence '{ev['id']}'",
                })
            else:
                evidence_only_items.append({
                    "code": "INCOMPLETE_EVIDENCE_RETAINED",
                    "source_key": f"evidence[{idx}]",
                    "disposition": "EVIDENCE_ONLY",
                    "message": "Legacy evidence item retained as supporting evidence only",
                    "value": ev,
                })
        if candidate_evidence:
            candidate["evidence"] = candidate_evidence
    elif "evidence" in src and not isinstance(evidence_src, list):
        unresolved_items.append({
            "code": "UNMAPPED_EVIDENCE_SECTION", "source_key": "evidence",
            "disposition": "UNRESOLVED", "value": evidence_src,
            "message": "Evidence section is not a list", "blocking": False,
        })

    approvals_src = src.get("approvals", [])
    if isinstance(approvals_src, list):
        for idx, app in enumerate(approvals_src):
            evidence_only_items.append({
                "code": "LEGACY_APPROVAL_RETAINED",
                "source_key": f"approvals[{idx}]",
                "disposition": "EVIDENCE_ONLY",
                "message": f"Legacy approval '{app.get('id', idx) if isinstance(app, dict) else idx}' preserved as supporting evidence",
                "details": app,
            })
    elif "approvals" in src:
        unresolved_items.append({
            "code": "UNMAPPED_APPROVALS_SECTION", "source_key": "approvals",
            "disposition": "UNRESOLVED", "value": approvals_src,
            "message": "Approvals section is not a list", "blocking": False,
        })

    # 6. Legacy Records
    legacy_records_src = src.get("legacy_records", [])
    if isinstance(legacy_records_src, list):
        for idx, rec in enumerate(legacy_records_src):
            evidence_only_items.append({
                "code": "LEGACY_RECORD_RETAINED",
                "source_key": f"legacy_records[{idx}]",
                "disposition": "EVIDENCE_ONLY",
                "message": "Legacy record retained for historical provenance",
                "details": rec,
            })
    elif "legacy_records" in src:
        unresolved_items.append({
            "code": "UNMAPPED_LEGACY_RECORDS_SECTION", "source_key": "legacy_records",
            "disposition": "UNRESOLVED", "value": legacy_records_src,
            "message": "Legacy records section is not a list", "blocking": False,
        })

    # 7. Unknown fields handling
    unknown_fields_src = src.get("unknown_fields", {})
    if isinstance(unknown_fields_src, dict):
        for k, v in unknown_fields_src.items():
            unresolved_items.append({
                "code": "EXPLICIT_UNKNOWN_FIELD",
                "source_key": f"unknown_fields.{k}",
                "disposition": "UNRESOLVED",
                "message": f"Explicit legacy unknown field '{k}' retained in report",
                "blocking": False,
                "value": v,
            })
    elif "unknown_fields" in src:
        unresolved_items.append({
            "code": "UNMAPPED_UNKNOWN_FIELDS_SECTION", "source_key": "unknown_fields",
            "disposition": "UNRESOLVED", "value": unknown_fields_src,
            "message": "Unknown fields section is not an object", "blocking": False,
        })

    for k in src:
        if k not in RECOGNIZED_TOP_LEVEL_KEYS:
            unresolved_items.append({
                "code": "UNRECOGNIZED_TOP_LEVEL_KEY",
                "source_key": k,
                "disposition": "UNRESOLVED",
                "message": f"Unrecognized top-level key '{k}' retained in report",
                "blocking": False,
                "value": src[k],
            })

    validate(candidate, "project")

    report = {
        "source_format": LEGACY_FORMAT,
        "source_fingerprint": source_fingerprint,
        "target_schema_version": CURRENT_PROJECT_SCHEMA,
        "mapped_items": mapped_items,
        "evidence_only_items": evidence_only_items,
        "warnings": warnings,
        "unresolved_items": unresolved_items,
        "redactions": redactions,
        "source_accounting": _source_accounting(
            src, mapped_items, evidence_only_items, unresolved_items, redactions),
    }

    return candidate, report
