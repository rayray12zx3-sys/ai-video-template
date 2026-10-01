"""Provider-neutral, read-only QC findings and failure routing.

Reports and overrides are supporting facts. Neither API writes canonical state,
changes a Router decision, approves an asset, or authorizes provider work.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .validators import fingerprint


LAYERS = ("Q0", "Q1", "Q2", "Q3")
DIMENSION_STATUSES = frozenset({"PASS", "FAIL", "NOT_APPLICABLE", "NOT_REVIEWED"})
AUTHORITIES = frozenset({"MACHINE", "AI_ASSISTED", "HUMAN"})
OWNERS = frozenset({"STORY", "SOURCE", "REFERENCE", "PREVIS", "GENERATION", "POST"})
SEVERITIES = frozenset({"MINOR", "MAJOR", "CRITICAL"})
SHA256 = re.compile(r"^[0-9a-f]{64}$")

DIMENSIONS = {
    "Q0": frozenset({"exists", "readable", "container", "codec", "resolution", "fps",
                     "frame_count", "duration", "audio_presence", "color_metadata"}),
    "Q1": frozenset({"identity", "anatomy", "prop_correctness", "exact_text", "geometry",
                     "camera", "motion", "temporal_consistency", "artifacts", "continuity",
                     "flicker_morphing", "background_drift", "object_disappearance",
                     "unwanted_camera_motion", "unwanted_body_motion", "clean_start_handle",
                     "clean_end_handle", "transition_safety", "interaction", "locked_properties"}),
    "Q2": frozenset({"expression", "energy", "composition", "art_direction", "storytelling",
                     "performance", "pacing", "emotional_intent"}),
    "Q3": frozenset({"timeline_master", "audio_requirements", "captions", "clean_versions",
                     "logo_safe_area", "required_deliverables", "materialized_final_assets"}),
}

# A profile selects dimensions; it cannot turn a failed mandatory constraint off.
PROFILES = {
    "CHARACTER_LOCKED_LOW_MOTION": {
        "Q0": DIMENSIONS["Q0"],
        "Q1": frozenset({"identity", "anatomy", "prop_correctness", "motion", "temporal_consistency",
                         "artifacts", "continuity", "flicker_morphing", "background_drift",
                         "object_disappearance", "unwanted_camera_motion", "unwanted_body_motion",
                         "clean_start_handle", "clean_end_handle", "locked_properties"}),
        "Q2": DIMENSIONS["Q2"], "Q3": frozenset(),
    },
    "REAL_UI": {
        "Q0": DIMENSIONS["Q0"],
        "Q1": frozenset({"exact_text", "geometry", "camera", "motion", "temporal_consistency",
                         "artifacts", "continuity", "flicker_morphing", "background_drift",
                         "clean_start_handle", "clean_end_handle", "transition_safety", "interaction"}),
        "Q2": frozenset({"composition", "storytelling", "pacing"}), "Q3": frozenset(),
    },
    "STRUCTURE_HEAVY": {
        "Q0": DIMENSIONS["Q0"],
        "Q1": frozenset({"identity", "anatomy", "prop_correctness", "exact_text", "geometry",
                         "camera", "motion", "temporal_consistency", "artifacts", "continuity",
                         "flicker_morphing", "object_disappearance", "clean_start_handle",
                         "clean_end_handle", "transition_safety", "interaction", "locked_properties"}),
        "Q2": DIMENSIONS["Q2"], "Q3": frozenset(),
    },
    "DELIVERY_MASTER": {
        "Q0": DIMENSIONS["Q0"], "Q1": frozenset({"clean_start_handle", "clean_end_handle",
                                                       "transition_safety", "artifacts"}),
        "Q2": DIMENSIONS["Q2"], "Q3": DIMENSIONS["Q3"],
    },
}

# Reason codes encode ownership. A caller cannot silently route a known failure elsewhere.
REASON_OWNERS = {
    "STORY_SPEC_CONFLICT": "STORY", "STORY_SEMANTIC_ERROR": "STORY",
    "SOURCE_BAD_FILE": "SOURCE", "SOURCE_BAD_CONTENT": "SOURCE",
    "REFERENCE_IDENTITY_MISMATCH": "REFERENCE", "REFERENCE_APPEARANCE_MISMATCH": "REFERENCE",
    "PREVIS_CAMERA_GEOMETRY": "PREVIS", "PREVIS_SPATIAL_RELATION": "PREVIS",
    "GENERATION_FILE_ERROR": "GENERATION", "GENERATION_TEMPORAL_ARTIFACT": "GENERATION",
    "GENERATION_IDENTITY_DRIFT": "GENERATION", "GENERATION_TEXT_ERROR": "GENERATION",
    "GENERATION_INTERACTION_ERROR": "GENERATION", "GENERATION_LOCKED_PROPERTY": "GENERATION",
    "GENERATION_HANDLE_ERROR": "GENERATION", "GENERATION_VISUAL_ERROR": "GENERATION",
    "POST_FIXABLE": "POST", "POST_DELIVERY_FORMAT": "POST",
    "POST_MISSING_DELIVERABLE": "POST", "POST_MATERIALIZATION": "POST",
    "POST_AUDIO_CAPTION": "POST", "POST_HANDLE_ERROR": "POST",
}
OWNER_ACTIONS = {
    "STORY": "RETURN_TO_STORY", "SOURCE": "RETURN_TO_SOURCE",
    "REFERENCE": "RETURN_TO_REFERENCE", "PREVIS": "RETURN_TO_PREVIS",
    "GENERATION": "REVIEW_GENERATION_STRATEGY", "POST": "RETURN_TO_POST",
}


def _nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")


def _timestamp(value):
    _nonempty(value, "timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp needs a timezone")


@dataclass(frozen=True)
class QCBinding:
    project_id: str
    state_revision: int
    project_hash: str
    shot_id: str
    candidate_id: str
    ticket_id: str | None = None
    receipt_claim_id: int | None = None
    shot_hash: str | None = None
    strategy_id: str | None = None

    def __post_init__(self):
        for name in ("project_id", "shot_id", "candidate_id"):
            _nonempty(getattr(self, name), name)
        if (not isinstance(self.state_revision, int) or isinstance(self.state_revision, bool)
                or self.state_revision < 0 or not SHA256.fullmatch(self.project_hash)):
            raise ValueError("invalid canonical QC binding")
        if self.ticket_id is not None and not SHA256.fullmatch(self.ticket_id):
            raise ValueError("invalid ticket ID")
        if self.receipt_claim_id is not None and (self.ticket_id is None or
                not isinstance(self.receipt_claim_id, int) or self.receipt_claim_id < 0):
            raise ValueError("receipt requires ticket and claim ID")
        if self.shot_hash is not None and not SHA256.fullmatch(self.shot_hash):
            raise ValueError("invalid shot fingerprint")
        if self.strategy_id is not None:
            _nonempty(self.strategy_id, "strategy ID")


def binding_from_ticket(ticket, receipt=None):
    """Consume I3 provenance without interpreting completion as a QC result."""
    if not ticket.verify():
        raise ValueError("ticket integrity failure")
    data = ticket.payload()
    claim_id = None
    if receipt is not None:
        if (receipt.ticket_id != ticket.id or receipt.candidate_id != data["candidate_id"] or
                receipt.provider != data["provider"] or receipt.workspace_id != data["workspace_id"] or
                receipt.execution_surface != data["execution_surface"] or
                receipt.runtime_snapshot_id != data["runtime_snapshot_id"]):
            raise ValueError("receipt does not bind ticket")
        claim_id = receipt.claim_id
    return QCBinding(data["project_id"], data["state_revision"], data["project_hash"],
                     data["shot_id"], data["candidate_id"], ticket.id, claim_id,
                     data.get("dependency_hashes", {}).get(f"shot:{data['shot_id']}"),
                     data.get("strategy_id"))


@dataclass(frozen=True)
class DimensionResult:
    status: str
    authority: str | None = None
    observation: str | None = None
    interpretation: str | None = None
    reason_codes: tuple[str, ...] = ()
    severity: str | None = None
    evidence_refs: tuple[str, ...] = ()
    owner: str | None = None
    recommended_action: str | None = None

    def __post_init__(self):
        if self.status not in DIMENSION_STATUSES or self.authority not in AUTHORITIES | {None}:
            raise ValueError("invalid dimension status or authority")
        if self.status in {"PASS", "FAIL"} and self.authority is None:
            raise ValueError("reviewed dimension requires authority")
        if not isinstance(self.reason_codes, tuple):
            raise ValueError("reason codes must be an immutable tuple")
        if self.status == "FAIL":
            for name in ("observation", "interpretation", "owner", "recommended_action"):
                _nonempty(getattr(self, name), name)
            if self.severity not in SEVERITIES or not self.reason_codes:
                raise ValueError("failure requires severity and structured reason")
            if self.owner not in OWNERS or self.recommended_action != OWNER_ACTIONS[self.owner]:
                raise ValueError("failure owner/action mismatch")
            if any(REASON_OWNERS.get(code) != self.owner for code in self.reason_codes):
                raise ValueError("reason code does not match failure owner")
        elif self.reason_codes or self.severity or self.owner or self.recommended_action:
            raise ValueError("only failures have ownership and reasons")
        if not isinstance(self.evidence_refs, tuple) or any(
                not isinstance(ref, str) or not ref for ref in self.evidence_refs):
            raise ValueError("evidence references must be nonempty strings")


def failure(*, authority, observation, interpretation, reason_code, severity="MAJOR",
            evidence_refs=()):
    owner = REASON_OWNERS.get(reason_code)
    if owner is None:
        raise ValueError("unknown failure reason")
    return DimensionResult("FAIL", authority, observation, interpretation, (reason_code,),
                           severity, tuple(evidence_refs), owner, OWNER_ACTIONS[owner])


@dataclass(frozen=True)
class QCReport:
    binding: QCBinding
    layer: str
    profile: str
    dimensions: tuple[tuple[str, DimensionResult], ...]
    overall: str
    conditional_justification: str | None = None
    human_review: object | None = None

    @property
    def id(self):
        payload = asdict(self)
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @property
    def findings(self):
        return tuple((name, result) for name, result in self.dimensions if result.status == "FAIL")


def applicable_dimensions(layer, profile, shot=None):
    if layer not in LAYERS or profile not in PROFILES:
        raise ValueError("unknown QC layer or profile")
    names = set(PROFILES[profile][layer])
    constraints = (shot or {}).get("constraints", {})
    if not isinstance(constraints, dict):
        raise ValueError("shot constraints must be an object")
    if layer == "Q1":
        for key, dimension in (("exact_text", "exact_text"), ("interaction", "interaction"),
                               ("spatial_relations", "geometry"), ("must_preserve", "locked_properties")):
            if constraints.get(key):
                names.add(dimension)
    return tuple(sorted(names))


@dataclass(frozen=True)
class HumanReview:
    actor: str
    evidence_ref: str
    timestamp: str
    reviewed_dimensions: tuple[str, ...]

    def __post_init__(self):
        _nonempty(self.actor, "human actor")
        _nonempty(self.evidence_ref, "human review evidence")
        _timestamp(self.timestamp)
        if not isinstance(self.reviewed_dimensions, tuple) or not self.reviewed_dimensions or any(
                not isinstance(name, str) or not name for name in self.reviewed_dimensions):
            raise ValueError("human review dimensions required")


def evaluate_qc(binding, layer, profile, results, *, shot=None, conditional_justification=None,
                human_review=None, human_verifier=None):
    """Evaluate supplied observations; missing applicable dimensions remain NOT_REVIEWED."""
    if not isinstance(binding, QCBinding) or not isinstance(results, dict):
        raise ValueError("QC binding and dimension results required")
    applicable = applicable_dimensions(layer, profile, shot)
    if set(results) - set(applicable):
        raise ValueError("result includes a dimension outside the selected profile")
    if any(not isinstance(value, DimensionResult) for value in results.values()):
        raise ValueError("results must be DimensionResult values")
    if layer == "Q1":
        if (not isinstance(shot, dict) or shot.get("id") != binding.shot_id or
                binding.shot_hash is None or fingerprint(shot) != binding.shot_hash):
            raise ValueError("Q1 requires the ticket-bound canonical shot")
        constraints = shot.get("constraints", {})
        for key, dimension in (("exact_text", "exact_text"), ("interaction", "interaction"),
                               ("spatial_relations", "geometry"), ("must_preserve", "locked_properties")):
            if constraints.get(key) and results.get(dimension, DimensionResult("NOT_REVIEWED")).status == "NOT_APPLICABLE":
                raise ValueError("canonical constraint cannot be NOT_APPLICABLE")
    dimensions = tuple((name, results.get(name, DimensionResult("NOT_REVIEWED"))
                        if name in applicable else DimensionResult("NOT_APPLICABLE"))
                       for name in sorted(DIMENSIONS[layer]))
    if layer == "Q2" and any(result.status in {"PASS", "FAIL"} and result.authority != "HUMAN"
                             for _, result in dimensions):
        raise ValueError("creative QC requires human review")
    reviewed_by_human = {name for name, result in dimensions
                         if result.status in {"PASS", "FAIL"} and result.authority == "HUMAN"}
    if layer == "Q2" or conditional_justification:
        if reviewed_by_human:
            if (not isinstance(human_review, HumanReview) or not callable(human_verifier) or
                    not reviewed_by_human.issubset(set(human_review.reviewed_dimensions)) or
                    human_verifier(human_review, binding) is not True):
                raise ValueError("trusted human review is required")
        elif conditional_justification:
            raise ValueError("conditional pass requires trusted human review")
    statuses = [result.status for _, result in dimensions]
    critical = any(result.status == "FAIL" and result.severity == "CRITICAL"
                   for _, result in dimensions)
    failures = [result for _, result in dimensions if result.status == "FAIL"]
    if critical:
        overall = "FAIL"
    elif failures and conditional_justification:
        _nonempty(conditional_justification, "conditional justification")
        if any(result.status == "NOT_REVIEWED" for _, result in dimensions):
            overall = "NOT_REVIEWED"
        elif not {name for name, result in dimensions if result.status == "FAIL"}.issubset(
                set(human_review.reviewed_dimensions)):
            raise ValueError("human reviewer must assess every conditional failure")
        else:
            overall = "CONDITIONAL_PASS"
    elif failures:
        overall = "FAIL"
    elif "NOT_REVIEWED" in statuses:
        overall = "NOT_REVIEWED"
    elif statuses and all(status == "NOT_APPLICABLE" for status in statuses):
        overall = "NOT_APPLICABLE"
    elif not statuses:
        overall = "NOT_APPLICABLE"
    else:
        overall = "PASS"
    if conditional_justification and overall != "CONDITIONAL_PASS":
        raise ValueError("conditional justification cannot bypass critical or unreviewed dimensions")
    return QCReport(binding, layer, profile, dimensions, overall, conditional_justification,
                    human_review if reviewed_by_human else None)


def check_exact_text(expected, observed, *, origin, role="DIEGETIC", authority="HUMAN", evidence_refs=()):
    """Compare literal semantic content; callers supply the observed media transcription."""
    _nonempty(expected, "expected text")
    _nonempty(role, "semantic role")
    reason = {"SOURCE": "SOURCE_BAD_CONTENT", "GENERATION": "GENERATION_TEXT_ERROR",
              "POST": "POST_FIXABLE"}.get(origin)
    if reason is None:
        raise ValueError("text check needs SOURCE, GENERATION, or POST origin")
    if observed is None:
        return DimensionResult("NOT_REVIEWED")
    if expected == observed:
        return DimensionResult("PASS", authority, f"{role} text matched", evidence_refs=tuple(evidence_refs))
    return failure(authority=authority, observation=f"{role} text differs from expectation",
                   interpretation="Exact semantic content is not preserved",
                   reason_code=reason, severity="CRITICAL", evidence_refs=evidence_refs)


def check_interactions(required, observed, *, authority="HUMAN", evidence_refs=()):
    """Match structured subject/action/object relations, not free-form descriptions."""
    if not isinstance(required, (tuple, list)) or not required:
        raise ValueError("interaction constraints required")
    if observed is None:
        return DimensionResult("NOT_REVIEWED")
    def normalize(items):
        if not isinstance(items, (tuple, list)):
            raise ValueError("interactions must be structured records")
        return {tuple(item[key] for key in ("subject", "action", "object")) for item in items
                if isinstance(item, dict) and all(isinstance(item.get(key), str) and item[key]
                                                   for key in ("subject", "action", "object"))}
    expected_relations = normalize(required)
    observed_relations = normalize(observed)
    if len(expected_relations) != len(required) or len(observed_relations) != len(observed):
        raise ValueError("invalid interaction relation")
    if expected_relations.issubset(observed_relations):
        return DimensionResult("PASS", authority, "Required interactions observed",
                               evidence_refs=tuple(evidence_refs))
    return failure(authority=authority, observation="Required interaction relation is absent",
                   interpretation="Canonical interaction constraint failed",
                   reason_code="GENERATION_INTERACTION_ERROR", severity="CRITICAL",
                   evidence_refs=evidence_refs)


def check_locked_properties(must_preserve, baseline, revision, *, origin, authority="HUMAN",
                            evidence_refs=()):
    reason = {"SOURCE": "SOURCE_BAD_CONTENT", "REFERENCE": "REFERENCE_APPEARANCE_MISMATCH",
              "GENERATION": "GENERATION_LOCKED_PROPERTY", "POST": "POST_FIXABLE"}.get(origin)
    if reason is None:
        raise ValueError("locked-property check needs a production origin")
    if not isinstance(must_preserve, (tuple, list)) or not must_preserve or any(
            not isinstance(key, str) or not key for key in must_preserve):
        raise ValueError("must_preserve requires property names")
    if not isinstance(baseline, dict) or not isinstance(revision, dict):
        raise ValueError("baseline and revision property maps required")
    if any(key not in baseline or key not in revision for key in must_preserve):
        return DimensionResult("NOT_REVIEWED")
    changed = [key for key in must_preserve if baseline[key] != revision[key]]
    if not changed:
        return DimensionResult("PASS", authority, "Locked properties preserved",
                               evidence_refs=tuple(evidence_refs))
    return failure(authority=authority, observation="Locked properties changed: " + ", ".join(changed),
                   interpretation="Revision violates canonical must_preserve constraints",
                   reason_code=reason, severity="CRITICAL",
                   evidence_refs=evidence_refs)


def check_handle(clean, *, position, post_fixable=False, authority="HUMAN", evidence_refs=()):
    if position not in {"start", "end"}:
        raise ValueError("handle position must be start or end")
    if clean is None:
        return DimensionResult("NOT_REVIEWED")
    if not isinstance(clean, bool):
        raise ValueError("clean handle observation must be boolean")
    if clean:
        return DimensionResult("PASS", authority, f"Clean {position} handle",
                               evidence_refs=tuple(evidence_refs))
    return failure(authority=authority, observation=f"Unclean {position} handle",
                   interpretation="Edit handle cannot be used as specified",
                   reason_code="POST_HANDLE_ERROR" if post_fixable else "GENERATION_HANDLE_ERROR",
                   evidence_refs=evidence_refs)


def check_file_metadata(metadata, expected=None, *, origin, evidence_refs=()):
    """Q0 deterministic metadata comparison. Probing is an external adapter boundary."""
    if not isinstance(metadata, dict) or not isinstance(expected or {}, dict):
        raise ValueError("metadata and expectations must be objects")
    reason = {"SOURCE": "SOURCE_BAD_FILE", "GENERATION": "GENERATION_FILE_ERROR",
              "POST": "POST_DELIVERY_FORMAT"}.get(origin)
    if reason is None:
        raise ValueError("metadata check needs SOURCE, GENERATION, or POST origin")
    expected = expected or {}
    unknown = set(metadata) | set(expected)
    if unknown - DIMENSIONS["Q0"]:
        raise ValueError("unknown Q0 media property")
    out = {}
    for name in DIMENSIONS["Q0"]:
        actual = metadata.get(name)
        target = expected.get(name)
        if name in {"exists", "readable"}:
            if actual is False:
                out[name] = failure(authority="MACHINE", observation=f"File {name} check failed",
                                    interpretation="Source media cannot be inspected",
                                    reason_code=reason, severity="CRITICAL",
                                    evidence_refs=evidence_refs)
            elif actual is True:
                out[name] = DimensionResult("PASS", "MACHINE", f"File {name} check passed",
                                            evidence_refs=tuple(evidence_refs))
            else:
                out[name] = DimensionResult("NOT_REVIEWED")
        elif target is None:
            out[name] = DimensionResult("NOT_APPLICABLE")
        elif actual is None:
            out[name] = DimensionResult("NOT_REVIEWED")
        elif actual == target:
            out[name] = DimensionResult("PASS", "MACHINE", f"{name} matches expected value",
                                        evidence_refs=tuple(evidence_refs))
        else:
            out[name] = failure(authority="MACHINE", observation=f"{name} differs from expectation",
                                interpretation="Technical media requirement failed",
                                reason_code=reason, evidence_refs=evidence_refs)
    return out


def check_delivery_assets(engine, binding, assets, *, evidence_refs=()):
    """Read current canonical delivery list; I2 validation verifies local bytes."""
    if not isinstance(assets, (tuple, list)) or not isinstance(binding, QCBinding):
        raise ValueError("delivery assets and QC binding required")
    snapshot = engine.inspect_consistency()
    if (snapshot.document.get("project_id") != binding.project_id or
            snapshot.state_revision != binding.state_revision or
            snapshot.project_hash != binding.project_hash or snapshot.access != "WRITABLE_VERSION"):
        raise ValueError("delivery QC canonical binding is stale or invalid")
    canonical_document = snapshot.document
    required = {asset.get("id"): asset for asset in canonical_document.get("assets", [])
                if isinstance(asset, dict) and asset.get("criticality") == "REQUIRED_FOR_DELIVERY"}
    if any(not isinstance(asset, dict) or not isinstance(asset.get("id"), str) or
           not asset["id"] for asset in assets):
        raise ValueError("delivery asset records require nonempty IDs")
    actual = {asset.get("id") for asset in assets if isinstance(asset, dict)}
    if len(actual) != len(assets) or not set(required).issubset(actual):
        return failure(authority="MACHINE", observation="No required delivery assets",
                       interpretation="Canonical required delivery output is absent",
                       reason_code="POST_MISSING_DELIVERABLE", severity="CRITICAL",
                       evidence_refs=evidence_refs)
    if not required:
        return DimensionResult("NOT_APPLICABLE")
    for asset in (asset for asset in assets if asset["id"] in required):
        if asset["id"] in required and fingerprint(asset) != fingerprint(required[asset["id"]]):
            raise ValueError("delivery asset differs from canonical record")
        if not isinstance(asset, dict) or asset.get("lifecycle") != "FINAL":
            return failure(authority="MACHINE", observation="Required asset is not FINAL",
                           interpretation="Delivery asset has not reached final lifecycle",
                           reason_code="POST_MISSING_DELIVERABLE", severity="CRITICAL",
                           evidence_refs=evidence_refs)
        locators = asset.get("locators")
        locators = locators if isinstance(locators, list) else []
        if (not isinstance(asset.get("sha256"), str) or not SHA256.fullmatch(asset["sha256"]) or
                not asset.get("provenance") or not any(
                    isinstance(loc, dict) and loc.get("type") in {"LOCAL", "GOOGLE_DRIVE", "ARCHIVE"}
                    and loc.get("availability") == "AVAILABLE"
                    for loc in locators)):
            return failure(authority="MACHINE", observation="Final asset lacks durable materialization record",
                           interpretation="Provider/cloud output is not delivery-ready",
                           reason_code="POST_MATERIALIZATION", severity="CRITICAL",
                           evidence_refs=evidence_refs)
    return DimensionResult("PASS", "MACHINE", "Final assets have durable materialization records",
                           evidence_refs=tuple(evidence_refs))


@dataclass(frozen=True)
class StopLossDecision:
    status: str
    matching_candidate_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    owner: str | None
    recommended_action: str | None


def evaluate_stop_loss(current, history, *, strategy_verifier, threshold=3):
    """Count distinct candidates with the same structured failure under one strategy."""
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 2:
        raise ValueError("stop-loss threshold must be at least two")
    if not isinstance(current, QCReport) or not current.findings:
        return StopLossDecision("NO_MATCH", (), (), None, None)
    _nonempty(current.binding.strategy_id, "candidate-bound strategy ID")
    if not callable(strategy_verifier) or strategy_verifier(current.binding) is not True:
        raise ValueError("trusted strategy binding is required")
    for dimension, result in current.findings:
        identity = (current.binding.project_id, current.binding.shot_id, current.layer,
                    dimension, result.owner, tuple(sorted(result.reason_codes)))
        candidates = {current.binding.candidate_id}
        for report in history:
            if not isinstance(report, QCReport) or report.binding.strategy_id != current.binding.strategy_id:
                continue
            if strategy_verifier(report.binding) is not True:
                raise ValueError("untrusted historical strategy binding")
            for prior_dimension, prior in report.findings:
                prior_identity = (report.binding.project_id, report.binding.shot_id, report.layer,
                                  prior_dimension, prior.owner, tuple(sorted(prior.reason_codes)))
                if prior_identity == identity:
                    candidates.add(report.binding.candidate_id)
        if len(candidates) >= threshold:
            return StopLossDecision("REPLAN_REQUIRED", tuple(sorted(candidates)),
                                    identity[-1], result.owner, "REPLAN_STRATEGY")
    return StopLossDecision("BELOW_THRESHOLD", (), (), None, None)


@dataclass(frozen=True)
class HumanOverride:
    actor: str
    decision: str
    reason: str
    report_id: str
    dimension: str | None
    timestamp: str
    binding: QCBinding


def record_human_override(report, *, actor, decision, reason, timestamp, dimension=None):
    """Create an audit payload only; State Engine integration must record it explicitly."""
    if not isinstance(report, QCReport):
        raise ValueError("QC report required")
    for label, value in (("actor", actor), ("reason", reason)):
        _nonempty(value, label)
    _timestamp(timestamp)
    if decision not in {"ACCEPT", "REJECT", "REVIEW_REQUIRED"}:
        raise ValueError("unknown human override decision")
    if dimension is not None and dimension not in dict(report.dimensions):
        raise ValueError("override dimension is not in report")
    return HumanOverride(actor, decision, reason, report.id, dimension, timestamp, report.binding)


def _parse_fps(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str) and "/" in raw:
        num, den = raw.split("/", 1)
        try:
            n, d = float(num), float(den)
            if d > 0:
                val = round(n / d, 4)
                return int(val) if val.is_integer() else val
        except ValueError:
            return None
    try:
        val = float(raw)
        return int(val) if val.is_integer() else val
    except (ValueError, TypeError):
        return None


def _parse_int(raw):
    if raw is None:
        return None
    try:
        val = int(raw)
        return val if val >= 0 else None
    except (ValueError, TypeError):
        return None


def probe_media(file_path, *, timeout=10, ffprobe_path="ffprobe"):
    """Invoke local ffprobe with explicit argv and no shell to extract normalized Q0 metadata."""
    default_failed = {
        "exists": False, "readable": False, "container": None, "codec": None,
        "resolution": None, "fps": None, "frame_count": None, "duration": None,
        "audio_presence": False, "color_metadata": None,
    }
    path = Path(file_path)
    if not path.is_file():
        return default_failed

    argv = [
        ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        res = subprocess.run(argv, capture_output=True, text=True, check=False,
                             timeout=timeout, shell=False)
    except (subprocess.SubprocessError, OSError, ValueError, UnicodeError):
        return {**default_failed, "exists": True}

    if res.returncode != 0 or not res.stdout or not res.stdout.strip():
        return {**default_failed, "exists": True}

    try:
        data = json.loads(res.stdout)
    except (json.JSONDecodeError, UnicodeError, ValueError):
        return {**default_failed, "exists": True}

    if not isinstance(data, dict):
        return {**default_failed, "exists": True}

    fmt = data.get("format") if isinstance(data.get("format"), dict) else {}
    format_name = fmt.get("format_name")
    container = format_name.split(",")[0] if isinstance(format_name, str) and format_name.strip() else None

    duration = None
    if fmt.get("duration") is not None:
        try:
            d_val = float(fmt["duration"])
            if d_val >= 0:
                duration = int(d_val) if d_val.is_integer() else round(d_val, 4)
        except (ValueError, TypeError):
            pass

    streams = data.get("streams") if isinstance(data.get("streams"), list) else []
    video_stream = next((s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"), None)
    audio_presence = any(isinstance(s, dict) and s.get("codec_type") == "audio" for s in streams)

    codec = None
    resolution = None
    fps = None
    frame_count = None
    color_metadata = None

    if video_stream:
        codec_name = video_stream.get("codec_name")
        if isinstance(codec_name, str) and codec_name.strip():
            codec = codec_name.strip()

        w, h = _parse_int(video_stream.get("width")), _parse_int(video_stream.get("height"))
        if w is not None and h is not None and w > 0 and h > 0:
            resolution = f"{w}x{h}"

        fps = _parse_fps(video_stream.get("r_frame_rate")) or _parse_fps(video_stream.get("avg_frame_rate"))
        frame_count = _parse_int(video_stream.get("nb_frames"))

        if duration is None and video_stream.get("duration") is not None:
            try:
                d_val = float(video_stream["duration"])
                if d_val >= 0:
                    duration = int(d_val) if d_val.is_integer() else round(d_val, 4)
            except (ValueError, TypeError):
                pass

        color_space = video_stream.get("color_space")
        if isinstance(color_space, str) and color_space.strip() and color_space.lower() != "unknown":
            color_metadata = color_space.strip()

    return {
        "exists": True,
        "readable": True,
        "container": container,
        "codec": codec,
        "resolution": resolution,
        "fps": fps,
        "frame_count": frame_count,
        "duration": duration,
        "audio_presence": audio_presence,
        "color_metadata": color_metadata,
    }


def probe_q0(file_path, expected=None, *, origin="GENERATION", timeout=10, ffprobe_path="ffprobe", evidence_refs=()):
    """Probe media and evaluate Q0 findings against expected criteria."""
    metadata = probe_media(file_path, timeout=timeout, ffprobe_path=ffprobe_path)
    return metadata, check_file_metadata(metadata, expected, origin=origin, evidence_refs=evidence_refs)
