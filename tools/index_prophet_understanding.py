#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    print(f"ERR: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"missing artifact: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid artifact JSON: {exc}")
    if not isinstance(value, dict):
        fail("artifact root must be an object")
    if value.get("schema_version") != "prophet-understanding.v0":
        fail("unsupported schema_version; expected prophet-understanding.v0")
    return value


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def compact(obj: Any) -> Any:
    return obj


def base_record(artifact: dict[str, Any], family: str, record_id: str, title: str, text: str, raw: dict[str, Any]) -> dict[str, Any]:
    repo = artifact.get("repo", {})
    policy = artifact.get("policy_status", {})
    return {
        "repo_full_name": repo.get("full_name", "unknown"),
        "repo_commit": repo.get("commit", "unknown"),
        "schema_version": artifact.get("schema_version", "unknown"),
        "record_family": family,
        "record_id": record_id,
        "title": title,
        "text": text,
        "policy_state": policy.get("state", "unknown"),
        "raw": compact(raw),
    }


def index_artifact(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    nodes = {node.get("id"): node for node in as_list(artifact.get("nodes")) if isinstance(node, dict)}
    edges = {edge.get("id"): edge for edge in as_list(artifact.get("edges")) if isinstance(edge, dict)}

    for node_id, node in sorted(nodes.items()):
        title = f"{node.get('kind', 'node')}: {node.get('label', node_id)}"
        text = " ".join(str(part) for part in [node.get("label"), node.get("kind"), node.get("path"), node.get("metadata", {})] if part)
        record = base_record(artifact, "repo_graph_node", str(node_id), title, text, node)
        record.update(
            {
                "node_id": node_id,
                "path": node.get("path"),
                "source_anchor": node.get("source_anchor"),
                "confidence": node.get("confidence"),
                "provenance_receipt_ids": node.get("provenance_receipt_ids", []),
            }
        )
        records.append(record)

    for edge_id, edge in sorted(edges.items()):
        source = edge.get("source")
        target = edge.get("target")
        title = f"{edge.get('kind', 'edge')}: {source} -> {target}"
        source_label = nodes.get(source, {}).get("label", source)
        target_label = nodes.get(target, {}).get("label", target)
        text = f"{edge.get('kind')} relationship from {source_label} to {target_label}"
        record = base_record(artifact, "repo_graph_edge", str(edge_id), title, text, edge)
        record.update(
            {
                "edge_id": edge_id,
                "source_node_id": source,
                "target_node_id": target,
                "confidence": edge.get("confidence"),
                "provenance_receipt_ids": edge.get("provenance_receipt_ids", []),
            }
        )
        records.append(record)

    for summary in [item for item in as_list(artifact.get("summaries")) if isinstance(item, dict)]:
        node_id = summary.get("node_id")
        node = nodes.get(node_id, {})
        record = base_record(artifact, "repo_graph_summary", summary.get("id", "summary:unknown"), f"summary: {node.get('label', node_id)}", summary.get("text", ""), summary)
        record.update({"node_id": node_id, "confidence": summary.get("confidence"), "provenance_receipt_ids": summary.get("provenance_receipt_ids", [])})
        records.append(record)

    for tour in [item for item in as_list(artifact.get("tours")) if isinstance(item, dict)]:
        for step in [item for item in as_list(tour.get("steps")) if isinstance(item, dict)]:
            record_id = f"{tour.get('id', 'tour:unknown')}#step-{step.get('order')}"
            record = base_record(artifact, "repo_graph_tour", record_id, tour.get("title", record_id), step.get("summary", ""), {"tour": tour, "step": step})
            record.update({"node_id": step.get("node_id"), "edge_ids": step.get("edge_ids", []), "provenance_receipt_ids": tour.get("provenance_receipt_ids", [])})
            records.append(record)

    for diff in [item for item in as_list(artifact.get("diff_impact_sets")) if isinstance(item, dict)]:
        text = "changed paths: " + ", ".join(diff.get("changed_paths", []))
        record = base_record(artifact, "repo_graph_diff_impact", diff.get("id", "diff-impact:unknown"), f"diff impact: {diff.get('risk', 'unknown')}", text, diff)
        record.update({"risk": diff.get("risk"), "requires_review": diff.get("requires_review"), "provenance_receipt_ids": diff.get("provenance_receipt_ids", [])})
        records.append(record)

    for result in [item for item in as_list(artifact.get("validation_results")) if isinstance(item, dict)]:
        record = base_record(artifact, "repo_graph_validation", result.get("id", "validation:unknown"), f"validation: {result.get('check_id')}", result.get("message", ""), result)
        record.update({"validation_status": result.get("status"), "severity": result.get("severity"), "target_id": result.get("target_id")})
        records.append(record)

    policy = artifact.get("policy_status", {}) if isinstance(artifact.get("policy_status"), dict) else {}
    for check in [item for item in as_list(policy.get("checks")) if isinstance(item, dict)]:
        record = base_record(artifact, "repo_graph_policy", check.get("id", "policy:unknown"), f"policy: {check.get('state')}", check.get("message", ""), check)
        record.update({"policy_state": check.get("state"), "provenance_receipt_ids": check.get("evidence_receipt_ids", [])})
        records.append(record)

    for receipt in [item for item in as_list(artifact.get("provenance_receipts")) if isinstance(item, dict)]:
        title = f"receipt: {receipt.get('claim_type')}"
        text = " ".join(str(receipt.get(key, "")) for key in ["claim_type", "generator", "parser_version", "validation_state"])
        record = base_record(artifact, "repo_graph_receipt", receipt.get("id", "receipt:unknown"), title, text, receipt)
        record.update({"confidence": receipt.get("confidence"), "validation_status": receipt.get("validation_state")})
        records.append(record)

    return sorted(records, key=lambda item: (item["record_family"], item["record_id"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Index Prophet Understand repo graph artifact for Lampstand.")
    parser.add_argument("--artifact", required=True, help="Path to .prophet/prophet-understanding.json")
    parser.add_argument("--out", required=True, help="Output path for deterministic JSON index records")
    args = parser.parse_args()

    artifact = load_artifact(Path(args.artifact))
    records = index_artifact(artifact)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} records to {out}")


if __name__ == "__main__":
    main()
