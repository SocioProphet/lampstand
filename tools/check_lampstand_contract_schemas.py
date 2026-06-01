#!/usr/bin/env python3
"""Validate Lampstand contract schema inventory and examples.

This checker intentionally implements only the JSON Schema subset used by the
Lampstand contracts. It avoids adding a runtime dependency while still catching
missing required fields, unexpected fields, basic type mismatches, enum failures,
array uniqueness, and simple numeric/string bounds.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
EXAMPLE_DIR = ROOT / "contracts" / "examples"
REQUIRED = {
    "lampstand.query.v0.schema.json": {
        "title": "LampstandQueryV0",
        "example": "lampstand.query.v0.example.json",
    },
    "lampstand.index-publication.v0.schema.json": {
        "title": "LampstandIndexPublicationV0",
        "example": "lampstand.index-publication.v0.example.json",
    },
    "lampstand.mesh-publication-policy.v0.schema.json": {
        "title": "LampstandMeshPublicationPolicyV0",
        "example": "lampstand.mesh-publication-policy.v0.example.json",
    },
    "lampstand.audit-receipt.v0.schema.json": {
        "title": "LampstandAuditReceiptV0",
        "example": "lampstand.audit-receipt.v0.example.json",
    },
}


def fail(message: str) -> int:
    print(f"ERR: {message}")
    return 2


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def validate_value(schema: dict[str, Any], value: Any, path: str) -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not type_matches(value, expected_type):
        return [f"{path}: expected {expected_type}, got {type(value).__name__}"]

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']!r}")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"{path}: string shorter than minLength={min_length}")
    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int) and value < minimum:
            errors.append(f"{path}: integer below minimum={minimum}")
        if isinstance(maximum, int) and value > maximum:
            errors.append(f"{path}: integer above maximum={maximum}")

    if isinstance(value, list):
        if schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            if len(serialized) != len(set(serialized)):
                errors.append(f"{path}: array items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate_value(item_schema, item, f"{path}[{index}]"))

    if isinstance(value, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            required = schema.get("required", [])
            if isinstance(required, list):
                for field in required:
                    if field not in value:
                        errors.append(f"{path}: missing required field {field!r}")
            if schema.get("additionalProperties") is False:
                extra = sorted(set(value) - set(properties))
                if extra:
                    errors.append(f"{path}: unexpected fields {extra!r}")
            for field, child_value in value.items():
                child_schema = properties.get(field) if isinstance(properties, dict) else None
                if isinstance(child_schema, dict):
                    errors.extend(validate_value(child_schema, child_value, f"{path}.{field}"))
    return errors


def validate_schema_shape(filename: str, schema: dict[str, Any], title: str) -> list[str]:
    errors: list[str] = []
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append(f"{filename}: must declare JSON Schema draft 2020-12")
    if schema.get("title") != title:
        errors.append(f"{filename}: title {schema.get('title')!r} != {title!r}")
    if schema.get("type") != "object":
        errors.append(f"{filename}: must define an object schema")
    if schema.get("additionalProperties") is not False:
        errors.append(f"{filename}: must set additionalProperties=false")
    required = schema.get("required")
    if not isinstance(required, list) or not required:
        errors.append(f"{filename}: must declare required fields")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append(f"{filename}: must declare properties")
    elif isinstance(required, list):
        missing = [field for field in required if field not in properties]
        if missing:
            errors.append(f"{filename}: required fields missing from properties: {missing}")
    return errors


def main() -> int:
    for filename, metadata in REQUIRED.items():
        schema_path = SCHEMA_DIR / filename
        if not schema_path.exists():
            return fail(f"missing schema: {schema_path.relative_to(ROOT)}")
        try:
            schema = load_json(schema_path)
        except json.JSONDecodeError as exc:
            return fail(f"invalid JSON in {schema_path.relative_to(ROOT)}: {exc}")
        if not isinstance(schema, dict):
            return fail(f"schema must be a JSON object: {schema_path.relative_to(ROOT)}")

        errors = validate_schema_shape(filename, schema, str(metadata["title"]))
        if errors:
            return fail("; ".join(errors))

        example_path = EXAMPLE_DIR / str(metadata["example"])
        if not example_path.exists():
            return fail(f"missing example: {example_path.relative_to(ROOT)}")
        try:
            example = load_json(example_path)
        except json.JSONDecodeError as exc:
            return fail(f"invalid JSON in {example_path.relative_to(ROOT)}: {exc}")

        example_errors = validate_value(schema, example, metadata["example"])
        if example_errors:
            return fail("; ".join(example_errors))
        print(f"OK: {filename} + {metadata['example']}")

    print(f"OK: Lampstand contract schema inventory valid ({len(REQUIRED)} schemas and examples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
