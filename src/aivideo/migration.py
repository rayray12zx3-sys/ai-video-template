"""Explicit, dry-run-first adjacent migration boundary.

No historical migration is registered in I1. A future version must provide
source validation and a deterministic transform before it becomes writable.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from .schema import CURRENT_PROJECT_SCHEMA, MigrationRequired, SchemaError, UnsupportedNewerSchema, schema_access, validate


@dataclass(frozen=True)
class MigrationStep:
    source: str
    target: str
    validate_source: Callable[[dict], None]
    transform: Callable[[dict], dict]
    allowed_changed_fields: tuple[str, ...] = ("schema_version",)


def preview_migration(document: dict, steps: tuple[MigrationStep, ...]):
    """Return migrated copy and audit report; never mutate the input."""
    version = document.get("schema_version")
    access = schema_access(document, CURRENT_PROJECT_SCHEMA, "schema_version")
    if access == "UNSUPPORTED_NEWER_SCHEMA":
        raise UnsupportedNewerSchema("unknown newer project schema")
    if access == "WRITABLE_VERSION":
        raise MigrationRequired("project is already at the writable version")
    current = deepcopy(document)
    changes = []
    visited = set()
    while version != CURRENT_PROJECT_SCHEMA:
        if version in visited:
            raise MigrationRequired("migration chain contains a cycle")
        visited.add(version)
        matches = [step for step in steps if step.source == version]
        if len(matches) != 1:
            raise MigrationRequired(f"no unique migration step from {version}")
        step = matches[0]
        step.validate_source(deepcopy(current))
        updated = step.transform(deepcopy(current))
        if not isinstance(updated, dict) or updated.get("schema_version") != step.target:
            raise SchemaError("migration returned invalid target version")
        removed = set(current) - set(updated)
        if removed:
            raise SchemaError(f"migration removed fields: {sorted(removed)}")
        changed = {key for key in set(current) | set(updated)
                   if current.get(key) != updated.get(key)}
        if set(step.allowed_changed_fields) - {"schema_version"}:
            raise SchemaError("field-changing migration requires a reviewed future implementation")
        unauthorized = changed - {"schema_version"}
        if unauthorized:
            raise SchemaError(f"migration changed unapproved fields: {sorted(unauthorized)}")
        changes.append({"source": version, "target": step.target,
                        "changed_fields": sorted(changed)})
        current = updated
        version = step.target
        if schema_access(current, CURRENT_PROJECT_SCHEMA, "schema_version") == "UNSUPPORTED_NEWER_SCHEMA":
            raise UnsupportedNewerSchema("migration overshot current schema")
    current["state_revision"] = document["state_revision"] + 1
    validate(current, "project")
    report = {"source_version": document["schema_version"], "target_version": version,
              "steps": changes, "warnings": [], "unresolved_items": []}
    return current, report
