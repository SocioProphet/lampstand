#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEXER = ROOT / "tools/index_prophet_understanding.py"


def fail(message: str) -> None:
    print(f"ERR: {message}", file=sys.stderr)
    raise SystemExit(2)


def artifact() -> dict[str, Any]:
    return {
        "schema_version": "prophet-understanding.v0",
        "repo": {"full_name": "SocioProphet/lampstand-fixture", "default_branch": "main", "commit": "abcdef1", "generated_at": "2026-05-05T00:00:00Z", "artifact_hash": "sha256:fixture"},
        "generator": {"name": "smart-tree", "version": "fixture", "parser_versions": {"fixture": "v0"}},
        "agent_identity": {"kind": "fixture", "id": "agent://fixture", "did": None},
        "nodes": [
            {"id": "repo:SocioProphet/lampstand-fixture", "kind": "repo", "label": "repo", "path": ".", "confidence": 1.0, "provenance_receipt_ids": ["receipt:run"], "metadata": {}},
            {"id": "contract:demo", "kind": "contract", "label": "demo contract", "path": "contracts/demo.json", "source_anchor": {"path": "contracts/demo.json", "start_line": 1, "end_line": 1, "content_hash": "sha256:demo"}, "confidence": 1.0, "provenance_receipt_ids": ["receipt:contract"], "metadata": {}},
        ],
        "edges": [{"id": "edge:repo-contains-contract", "kind": "contains", "source": "repo:SocioProphet/lampstand-fixture", "target": "contract:demo", "confidence": 1.0, "provenance_receipt_ids": ["receipt:run"], "metadata": {}}],
        "summaries": [{"id": "summary:demo", "node_id": "contract:demo", "text": "demo contract summary", "confidence": 0.9, "provenance_receipt_ids": ["receipt:contract"]}],
        "tours": [],
        "diff_impact_sets": [],
        "provenance_receipts": [
            {"id": "receipt:run", "claim_type": "repo-scan", "generator": "smart-tree", "parser_version": "fixture", "input_source_hash": "sha256:run", "generated_at": "2026-05-05T00:00:00Z", "confidence": 1.0, "validation_state": "valid", "warnings": []},
            {"id": "receipt:contract", "claim_type": "contract-node", "generator": "smart-tree", "parser_version": "fixture", "input_source_hash": "sha256:contract", "generated_at": "2026-05-05T00:00:00Z", "confidence": 1.0, "validation_state": "valid", "warnings": []},
        ],
        "validation_results": [],
        "policy_status": {"state": "allow", "checks": [{"id": "policy:fixture", "state": "allow", "message": "fixture", "evidence_receipt_ids": ["receipt:run"]}]},
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lampstand-prophet-understand-") as raw_tmp:
        tmp = Path(raw_tmp)
        artifact_path = tmp / "prophet-understanding.json"
        out = tmp / "index.json"
        artifact_path.write_text(json.dumps(artifact(), indent=2, sort_keys=True), encoding="utf-8")
        result = subprocess.run([sys.executable, str(INDEXER), "--artifact", str(artifact_path), "--out", str(out)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if result.returncode != 0:
            print(result.stdout, file=sys.stderr)
            fail("indexer exited nonzero")
        if not out.exists():
            fail("indexer did not create output")
        records = json.loads(out.read_text(encoding="utf-8"))
        if not isinstance(records, list) or len(records) < 5:
            fail("indexer emitted too few records")
        families = {record.get("record_family") for record in records if isinstance(record, dict)}
        for family in {"repo_graph_node", "repo_graph_edge", "repo_graph_summary", "repo_graph_policy", "repo_graph_receipt"}:
            if family not in families:
                fail(f"missing indexed family: {family}")
        print("OK: Lampstand Prophet Understand index smoke passed")


if __name__ == "__main__":
    main()
