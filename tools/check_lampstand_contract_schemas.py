#!/usr/bin/env python3
"""Validate Lampstand contract schema inventory."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
REQUIRED = {
    "lampstand.query.v0.schema.json": "LampstandQueryV0",
    "lampstand.index-publication.v0.schema.json": "LampstandIndexPublicationV0",
    "lampstand.mesh-publication-policy.v0.schema.json": "LampstandMeshPublicationPolicyV0",
    "lampstand.audit-receipt.v0.schema.json": "LampstandAuditReceiptV0",
}


def fail(message: str) -> int:
    print(f"ERR: {message}")
    return 2


def main() -> int:
    for filename, title in REQUIRED.items():
        path = SCHEMA_DIR / filename
        if not path.exists():
            return fail(f"missing schema: {path.relative_to(ROOT)}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return fail(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
        if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            return fail(f"{filename} must declare JSON Schema draft 2020-12")
        if data.get("title") != title:
            return fail(f"{filename} title {data.get('title')!r} != {title!r}")
        if data.get("type") != "object":
            return fail(f"{filename} must define an object schema")
        if data.get("additionalProperties") is not False:
            return fail(f"{filename} must set additionalProperties=false")
        required = data.get("required")
        if not isinstance(required, list) or not required:
            return fail(f"{filename} must declare required fields")
        properties = data.get("properties")
        if not isinstance(properties, dict):
            return fail(f"{filename} must declare properties")
        missing = [field for field in required if field not in properties]
        if missing:
            return fail(f"{filename} required fields missing from properties: {missing}")
        print(f"OK: {filename}")
    print(f"OK: Lampstand contract schema inventory valid ({len(REQUIRED)} schemas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
