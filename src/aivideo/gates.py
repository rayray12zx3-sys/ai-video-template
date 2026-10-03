"""Deterministic, derived production gate evaluation."""

from .validators import evidence_status, finding, validate_project


GATES = (
    ("G0", "BRIEF_LOCK"),
    ("G1", "MASTER_ASSETS_APPROVED"),
    ("G2", "STORYBOARD_APPROVED"),
    ("G3", "STATIC_ANIMATIC_APPROVED"),
    ("G4", "GENERATION_READY"),
    ("G5", "BATCH_GENERATION_ALLOWED"),
    ("G6", "FINAL_QC_APPROVED"),
)

GENERATIVE_METHODS = frozenset({"AUTO", "AI_IMAGE", "AI_VIDEO"})


def _generative_shots(doc):
    return [shot for shot in doc.get("shots", []) if isinstance(shot, dict)
            and shot.get("readiness", "REQUIRED") == "REQUIRED"
            and (shot.get("production_method") in tuple(GENERATIVE_METHODS)
                 or shot.get("generation_required") is True
                 or (shot.get("production_method") == "COMPOSITE" and shot.get("generation_required") is not False)
                 or (isinstance(shot.get("lip_sync"), dict)
                     and shot["lip_sync"].get("status") in ("REQUIRED", "CONDITIONAL", "PARTIAL", "AVOIDABLE")
                     and not (shot.get("base_plate_policy") == "APPROVED_SOURCE"
                              and shot.get("lip_sync_execution") == "SOURCE_ALREADY_SYNCHRONIZED")))]


def _approval(doc, snapshot, kind, subject, *, human=True, bindings=(), approval_verifier=None):
    bindings = tuple(bindings) + tuple(edge["source"] for edge in doc.get("dependencies", [])
                                      if isinstance(edge, dict) and isinstance(edge.get("source"), str)
                                      and edge.get("target") == subject)
    valid, reason = evidence_status(doc, kind=kind, subject=subject, snapshot=snapshot,
                                    human=human, required_bindings=bindings,
                                    require_trusted=human, approval_verifier=approval_verifier)
    return [] if valid else [finding(reason, f"{kind} approval is absent, stale, or unapproved", subject=subject)]


def _assets(doc, criticality):
    return [asset for asset in doc.get("assets", []) if isinstance(asset, dict)
            and asset.get("criticality", "OPTIONAL") == criticality]


def _required_assets(doc, criticality, snapshot, approval_verifier=None):
    findings = []
    for asset in _assets(doc, criticality):
        subject = f"asset:{asset.get('id')}"
        if asset.get("lifecycle") not in {"APPROVED", "FINAL"}:
            findings.append(finding("ASSET_NOT_APPROVED", "Required asset is not approved", subject=subject))
        else:
            findings.extend(_approval(doc, snapshot, "ASSET_APPROVAL", subject, approval_verifier=approval_verifier))
    return findings


def _own_findings(gate_id, doc, snapshot, approval_verifier=None):
    errors = []
    evidence = []
    if gate_id == "G0":
        evidence = ["BRIEF_LOCK"]
        if not doc.get("brief"):
            errors.append(finding("MISSING_BRIEF", "Brief is missing"))
        else:
            errors.extend(_approval(doc, snapshot, "BRIEF_LOCK", "project:brief", approval_verifier=approval_verifier))
    elif gate_id == "G1":
        evidence = ["ASSET_APPROVAL for each REQUIRED_FOR_STORYBOARD asset"]
        errors.extend(_required_assets(doc, "REQUIRED_FOR_STORYBOARD", snapshot, approval_verifier))
    elif gate_id == "G2":
        evidence = ["STORYBOARD_APPROVAL"]
        if not doc.get("storyboard"):
            errors.append(finding("MISSING_STORYBOARD", "Storyboard is missing"))
        else:
            shot_refs = tuple(f"shot:{shot['id']}" for shot in doc.get("shots", [])
                              if isinstance(shot, dict) and shot.get("readiness", "REQUIRED") == "REQUIRED")
            errors.extend(_approval(doc, snapshot, "STORYBOARD_APPROVAL", "project:storyboard",
                                    bindings=shot_refs, approval_verifier=approval_verifier))
        for shot in doc.get("shots", []):
            if not isinstance(shot, dict):
                continue
            subject = f"shot:{shot.get('id')}"
            if (shot.get("base_plate_policy") == "APPROVED_SOURCE"
                    and isinstance(shot.get("lip_sync"), dict)
                    and shot["lip_sync"].get("status") in ("REQUIRED", "CONDITIONAL", "PARTIAL", "AVOIDABLE")):
                errors.extend(_approval(doc, snapshot, "SOURCE_SYNC_APPROVAL", subject,
                    bindings=(f"asset:{shot.get('base_plate_asset_id')}",), approval_verifier=approval_verifier))
            readiness = shot.get("readiness", "REQUIRED")
            if readiness == "OMITTED_BY_DESIGN":
                evidence.append(f"OMISSION_APPROVAL for {subject}")
                errors.extend(_approval(doc, snapshot, "OMISSION_APPROVAL", subject, approval_verifier=approval_verifier))
            elif readiness == "REQUIRED" and not all(shot.get(key) for key in ("intent", "duration_frames", "production_method")):
                errors.append(finding("SHOT_INCOMPLETE", "Required shot lacks intent, duration, or production method", subject=subject))
    elif gate_id == "G3":
        evidence = ["ANIMATIC_APPROVAL", "ASSET_APPROVAL for each REQUIRED_FOR_ANIMATIC asset"]
        if not doc.get("animatic"):
            errors.append(finding("MISSING_ANIMATIC", "Static animatic is missing"))
        else:
            bound = ("project:storyboard",) + tuple(f"asset:{asset['id']}" for asset in
                                                    _assets(doc, "REQUIRED_FOR_ANIMATIC"))
            errors.extend(_approval(doc, snapshot, "ANIMATIC_APPROVAL", "project:animatic",
                                    bindings=bound, approval_verifier=approval_verifier))
        errors.extend(_required_assets(doc, "REQUIRED_FOR_ANIMATIC", snapshot, approval_verifier))
    elif gate_id == "G4":
        evidence = ["GENERATION_READINESS for each required shot", "Approved and materialized generation inputs",
                    "Explicit provider upload policy"]
        for shot in _generative_shots(doc):
            if shot.get("readiness", "REQUIRED") == "REQUIRED" and not shot.get("generation_ready", False):
                errors.append(finding("SHOT_NOT_GENERATION_READY", "Required shot lacks generation readiness", subject=f"shot:{shot.get('id')}"))
            elif shot.get("readiness", "REQUIRED") == "REQUIRED":
                bound = tuple(f"asset:{asset_id}" for asset_id in shot.get("input_asset_ids", []))
                errors.extend(_approval(doc, snapshot, "GENERATION_READINESS", f"shot:{shot.get('id')}",
                                        human=False, bindings=bound, approval_verifier=approval_verifier))
            inputs = shot.get("input_asset_ids", [])
            for asset_id in inputs if isinstance(inputs, list) else []:
                asset = next((a for a in doc.get("assets", []) if isinstance(a, dict) and a.get("id") == asset_id), None)
                subject = f"asset:{asset_id}"
                if asset is None or asset.get("lifecycle") not in {"APPROVED", "FINAL"}:
                    errors.append(finding("INPUT_NOT_READY", "Generation input is absent or unapproved", subject=subject))
                else:
                    errors.extend(_approval(doc, snapshot, "ASSET_APPROVAL", subject, approval_verifier=approval_verifier))
                    policy = asset.get("external_processing")
                    policy = policy if isinstance(policy, dict) else {"policy": "REVIEW_REQUIRED"}
                    if policy.get("policy") == "FORBIDDEN":
                        errors.append(finding("UPLOAD_FORBIDDEN", "Generation input cannot be uploaded", subject=subject))
                    elif policy.get("policy") == "REVIEW_REQUIRED":
                        errors.extend(_approval(doc, snapshot, "EXTERNAL_PROCESSING_APPROVAL", subject, approval_verifier=approval_verifier))
        errors.extend(_required_assets(doc, "REQUIRED_FOR_GENERATION", snapshot, approval_verifier))
        for asset in _assets(doc, "REQUIRED_FOR_GENERATION"):
            policy = asset.get("external_processing")
            policy = policy if isinstance(policy, dict) else {"policy": "REVIEW_REQUIRED"}
            subject = f"asset:{asset.get('id')}"
            if policy.get("policy") == "FORBIDDEN":
                errors.append(finding("UPLOAD_FORBIDDEN", "Required generation asset cannot be uploaded", subject=subject))
            elif policy.get("policy") == "REVIEW_REQUIRED":
                errors.extend(_approval(doc, snapshot, "EXTERNAL_PROCESSING_APPROVAL", subject, approval_verifier=approval_verifier))
    elif gate_id == "G5":
        evidence = ["BATCH_APPROVAL"]
        if not doc.get("generation_plan"):
            errors.append(finding("MISSING_GENERATION_PLAN", "Generation plan is missing"))
        else:
            shot_refs = tuple(f"shot:{shot['id']}" for shot in doc.get("shots", [])
                              if isinstance(shot, dict) and shot.get("readiness", "REQUIRED") == "REQUIRED")
            errors.extend(_approval(doc, snapshot, "BATCH_APPROVAL", "project:generation_plan",
                                    bindings=shot_refs, approval_verifier=approval_verifier))
    elif gate_id == "G6":
        evidence = ["FINAL_QC_APPROVAL", "ASSET_APPROVAL for each REQUIRED_FOR_DELIVERY asset"]
        if not doc.get("final_qc"):
            errors.append(finding("MISSING_FINAL_QC", "Final QC record is missing"))
        else:
            if (not isinstance(doc["final_qc"], dict) or doc["final_qc"].get("technical") != "PASS"
                    or doc["final_qc"].get("creative") != "APPROVED"):
                errors.append(finding("FINAL_QC_INCOMPLETE", "Technical and creative QC must each pass"))
            bound = tuple(f"asset:{asset['id']}" for asset in _assets(doc, "REQUIRED_FOR_DELIVERY"))
            errors.extend(_approval(doc, snapshot, "FINAL_QC_APPROVAL", "project:final_qc",
                                    bindings=bound, approval_verifier=approval_verifier))
        errors.extend(_required_assets(doc, "REQUIRED_FOR_DELIVERY", snapshot, approval_verifier))
    return errors, evidence


def evaluate_gates(engine, *, approval_verifier=None):
    """Return a fresh report. This report is never read as canonical input."""
    validation = validate_project(engine)
    results = {}
    doc = validation.snapshot.document if validation.snapshot else {}
    has_generation = bool(_generative_shots(doc))
    for index, (gate_id, name) in enumerate(GATES):
        applicable = has_generation or gate_id not in {"G4", "G5"}
        own, required = _own_findings(gate_id, doc, validation.snapshot, approval_verifier) if applicable and validation.snapshot and validation.snapshot.access == "WRITABLE_VERSION" else ([], [])
        upstream = [GATES[i][0] for i in range(index)
                    if results[GATES[i][0]]["status"] not in {"PASS", "NOT_APPLICABLE"}]
        blocking = list(validation.findings) + own if not validation.ok else own
        if not validation.ok:
            status = "BLOCKED"
        elif upstream:
            status = "BLOCKED"
            blocking = [finding("UPSTREAM_GATE", "Prerequisite gates are not passing: " + ", ".join(upstream))] + blocking
        elif not applicable:
            status = "NOT_APPLICABLE"
        else:
            status = "FAIL" if blocking else "PASS"
        results[gate_id] = {"gate_id": gate_id, "name": name, "status": status,
                            "blocking_findings": blocking, "nonblocking_findings": [],
                            "required_evidence": required,
                            "next_remediation": blocking[0]["message"] if blocking else None}
    return results
