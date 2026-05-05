from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class StoredAdapterRecord:
    record_id: str
    record_type: str
    title: str
    object_kind: str
    path_ref: str
    classification: str
    updated_at_ns: int


class AdapterRecordStore:
    """SQLite-backed store for governed local adapter/search records.

    This is intentionally separate from the canonical `files` table. Adapter
    records represent summaries, symbols, security signals, and memory candidates
    produced by controlled tools such as Smart Tree. They are local-search records,
    not filesystem truth.
    """

    def __init__(self, path: Path):
        self.path = path
        self.con: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), timeout=5.0, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        cur = self.con.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA busy_timeout=5000;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        self.con.commit()
        self._ensure_schema()

    def close(self) -> None:
        if self.con is not None:
            self.con.close()
            self.con = None

    def _ensure_schema(self) -> None:
        assert self.con is not None
        cur = self.con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS adapter_records (
                record_id TEXT PRIMARY KEY,
                record_type TEXT NOT NULL,
                title TEXT NOT NULL,
                object_kind TEXT NOT NULL,
                path_ref TEXT NOT NULL,
                source_root_id TEXT,
                content_hash TEXT,
                metadata_hash TEXT,
                snippet TEXT,
                handling_tags_json TEXT NOT NULL,
                freshness_json TEXT,
                policy_decision_json TEXT NOT NULL,
                source_json TEXT NOT NULL,
                classification TEXT NOT NULL,
                updated_at_ns INTEGER NOT NULL
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_adapter_records_type ON adapter_records(record_type);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_adapter_records_kind ON adapter_records(object_kind);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_adapter_records_path_ref ON adapter_records(path_ref);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_adapter_records_updated ON adapter_records(updated_at_ns);")
        try:
            cur.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS adapter_records_fts USING fts5(
                    record_id UNINDEXED,
                    title,
                    object_kind,
                    path_ref,
                    snippet,
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "fts5" in msg or "no such module" in msg:
                raise RuntimeError(
                    "SQLite FTS5 is required for adapter record search. "
                    "Install a sqlite3 build with FTS5 enabled."
                ) from e
            raise
        self.con.commit()

    def upsert_record(self, record: dict[str, Any]) -> str:
        """Insert/update a governed adapter record and FTS document."""
        assert self.con is not None
        normalized = normalize_record(record)
        now_ns = time.time_ns()
        cur = self.con.cursor()
        cur.execute("BEGIN;")
        try:
            cur.execute(
                """
                INSERT INTO adapter_records(
                    record_id,
                    record_type,
                    title,
                    object_kind,
                    path_ref,
                    source_root_id,
                    content_hash,
                    metadata_hash,
                    snippet,
                    handling_tags_json,
                    freshness_json,
                    policy_decision_json,
                    source_json,
                    classification,
                    updated_at_ns
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(record_id) DO UPDATE SET
                    record_type=excluded.record_type,
                    title=excluded.title,
                    object_kind=excluded.object_kind,
                    path_ref=excluded.path_ref,
                    source_root_id=excluded.source_root_id,
                    content_hash=excluded.content_hash,
                    metadata_hash=excluded.metadata_hash,
                    snippet=excluded.snippet,
                    handling_tags_json=excluded.handling_tags_json,
                    freshness_json=excluded.freshness_json,
                    policy_decision_json=excluded.policy_decision_json,
                    source_json=excluded.source_json,
                    classification=excluded.classification,
                    updated_at_ns=excluded.updated_at_ns;
                """,
                (
                    normalized["record_id"],
                    normalized["record_type"],
                    normalized["title"],
                    normalized["object_kind"],
                    normalized["path_ref"],
                    normalized.get("source_root_id"),
                    normalized.get("content_hash"),
                    normalized.get("metadata_hash"),
                    normalized.get("snippet"),
                    json.dumps(normalized.get("handling_tags", []), sort_keys=True),
                    json.dumps(normalized.get("freshness"), sort_keys=True),
                    json.dumps(normalized.get("policy_decision", {}), sort_keys=True),
                    json.dumps(normalized.get("source", {}), sort_keys=True),
                    normalized.get("classification", "local_only"),
                    now_ns,
                ),
            )
            cur.execute("DELETE FROM adapter_records_fts WHERE record_id=?;", (normalized["record_id"],))
            cur.execute(
                """
                INSERT INTO adapter_records_fts(record_id, title, object_kind, path_ref, snippet)
                VALUES(?,?,?,?,?);
                """,
                (
                    normalized["record_id"],
                    normalized["title"],
                    normalized["object_kind"],
                    normalized["path_ref"],
                    normalized.get("snippet") or "",
                ),
            )
            cur.execute("COMMIT;")
        except Exception:
            try:
                cur.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        return str(normalized["record_id"])

    def upsert_records(self, records: Iterable[dict[str, Any]]) -> list[str]:
        return [self.upsert_record(record) for record in records]

    def query_records(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        assert self.con is not None
        cur = self.con.cursor()
        cur.execute(
            """
            SELECT
                adapter_records.record_id AS record_id,
                adapter_records.record_type AS record_type,
                adapter_records.title AS title,
                adapter_records.object_kind AS object_kind,
                adapter_records.path_ref AS path_ref,
                adapter_records.classification AS classification,
                bm25(adapter_records_fts) AS score,
                snippet(adapter_records_fts, 4, '[', ']', '…', 10) AS snippet
            FROM adapter_records_fts
            JOIN adapter_records ON adapter_records.record_id = adapter_records_fts.record_id
            WHERE adapter_records_fts MATCH ?
            ORDER BY score
            LIMIT ?;
            """,
            (query, int(limit)),
        )
        return [dict(row) for row in cur.fetchall()]

    def stats(self) -> dict[str, Any]:
        assert self.con is not None
        cur = self.con.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM adapter_records;")
        n_records = int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM adapter_records_fts;")
        n_fts = int(cur.fetchone()["n"])
        return {"adapter_records": n_records, "adapter_records_fts": n_fts}


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    required = ("record_type", "title", "object_kind", "path_ref")
    missing = [field for field in required if not record.get(field)]
    if missing:
        raise ValueError(f"adapter record missing required fields: {', '.join(missing)}")

    handling_tags = record.get("handling_tags") or []
    if not isinstance(handling_tags, list):
        raise ValueError("handling_tags must be a list")

    normalized = dict(record)
    normalized.setdefault("classification", "local_only")
    normalized.setdefault("policy_decision", {})
    normalized.setdefault("source", {})
    normalized["handling_tags"] = [str(tag) for tag in handling_tags]
    if not normalized.get("record_id"):
        normalized["record_id"] = derive_record_id(normalized)
    return normalized


def derive_record_id(record: dict[str, Any]) -> str:
    parts = {
        "record_type": record.get("record_type"),
        "object_kind": record.get("object_kind"),
        "path_ref": record.get("path_ref"),
        "title": record.get("title"),
        "metadata_hash": record.get("metadata_hash"),
        "content_hash": record.get("content_hash"),
        "source": record.get("source", {}),
    }
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "lampstand-adapter-record::sha256:" + hashlib.sha256(raw).hexdigest()[:32]
