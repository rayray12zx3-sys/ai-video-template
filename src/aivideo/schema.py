"""Small, dependency-free validator for the I0 JSON/YAML-subset schemas."""

import json
from pathlib import Path


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
CURRENT_PROJECT_SCHEMA = "2.0"
CURRENT_EVENT_SCHEMA = "1.0"


class SchemaError(ValueError):
    pass


class UnsupportedNewerSchema(SchemaError):
    code = "UNSUPPORTED_NEWER_SCHEMA"


class MigrationRequired(SchemaError):
    code = "MIGRATION_REQUIRED"


def _version(value):
    if not isinstance(value, str):
        raise SchemaError("schema_version must be a string")
    parts = value.split(".")
    if len(parts) != 2 or any(not part.isdecimal() for part in parts):
        raise SchemaError("schema_version must be MAJOR.MINOR")
    return tuple(map(int, parts))


def schema_access(document, current_version, field):
    if not isinstance(document, dict):
        raise SchemaError("document must be an object")
    actual = _version(document.get(field))
    current = _version(current_version)
    if actual > current:
        return "UNSUPPORTED_NEWER_SCHEMA"
    if actual < current:
        return "MIGRATION_REQUIRED"
    return "WRITABLE_VERSION"


def _validate(value, spec, location="$", depth=0):
    if depth > 64:
        raise SchemaError(f"{location}: nesting too deep")
    kinds = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}
    kind = spec.get("type")
    if kind and (not isinstance(value, kinds[kind]) or (kind in ("integer", "number") and isinstance(value, bool))):
        raise SchemaError(f"{location}: expected {kind}")
    if "enum" in spec and value not in spec["enum"]:
        raise SchemaError(f"{location}: invalid value")
    if kind == "object":
        for name in spec.get("required", []):
            if name not in value:
                raise SchemaError(f"{location}: missing {name}")
        properties = spec.get("properties", {})
        for name, item in value.items():
            if name in properties:
                _validate(item, properties[name], f"{location}.{name}", depth + 1)
            elif spec.get("additionalProperties") is False:
                raise SchemaError(f"{location}: unexpected {name}")
            elif isinstance(spec.get("additionalProperties"), dict):
                _validate(item, spec["additionalProperties"], f"{location}.{name}", depth + 1)
    if kind == "array":
        for index, item in enumerate(value):
            _validate(item, spec["items"], f"{location}[{index}]", depth + 1)
    if kind == "integer" and "minimum" in spec and value < spec["minimum"]:
        raise SchemaError(f"{location}: below minimum")
    if kind == "string" and "minLength" in spec and len(value) < spec["minLength"]:
        raise SchemaError(f"{location}: empty string")


def validate(document, schema_name):
    if schema_name not in ("project", "event"):
        raise ValueError("unknown schema")
    schema = json.loads((SCHEMA_DIR / f"{schema_name}.schema.json").read_text(encoding="utf-8"))
    field = "schema_version" if schema_name == "project" else "event_schema_version"
    version = CURRENT_PROJECT_SCHEMA if schema_name == "project" else CURRENT_EVENT_SCHEMA
    access = schema_access(document, version, field)
    if access == "UNSUPPORTED_NEWER_SCHEMA":
        raise UnsupportedNewerSchema(f"{field}: unknown newer version")
    if access == "MIGRATION_REQUIRED":
        raise MigrationRequired(f"{field}: explicit migration required")
    _validate(document, schema)
    return document
