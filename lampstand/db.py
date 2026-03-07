from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class FileRow:
    id: int
    path: str
    dir: str
    name: str
    ext: str
    size: int
    mtime_ns: int
    ctime_ns: int
    inode: int
    dev: int
    mode: int
    indexed_at_ns: int
    content_len: int
    content_sha256: str


class IndexDB:
    """SQLite-backed metadata + FTS store.

    Design goals:
    - no external deps
    - crash-safe via WAL
    - small, simple schema that we can evolve
    """

    def __init__(self, path: Path):
        self.path = path
        self.con: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), timeout=5.0)
        self.con.row_factory = sqlite3.Row
        cur = self.con.cursor()
        # Pragmas: WAL for crash safety and decent perf.
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA busy_timeout=5000;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        cur.execute("PRAGMA foreign_keys=ON;")
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
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                dir TEXT NOT NULL,
                name TEXT NOT NULL,
                ext TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                ctime_ns INTEGER NOT NULL,
                inode INTEGER NOT NULL,
                dev INTEGER NOT NULL,
                mode INTEGER NOT NULL,
                indexed_at_ns INTEGER NOT NULL,
                content_len INTEGER NOT NULL,
                content_sha256 TEXT NOT NULL
            );
            """
        )

        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_dir ON files(dir);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_name ON files(name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime_ns);")

        # FTS5 table. We manage rowids explicitly (rowid == files.id).
        #
        # Note: we intentionally keep the FTS table *with stored content* (not contentless)
        # in this prototype so we can use FTS5's built-in `snippet()` for highlighting.
        try:
            cur.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
                    path UNINDEXED,
                    dir,
                    name,
                    ext,
                    content,
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            # Common failure if distro sqlite3 is built without FTS5.
            if "fts5" in msg or "no such module" in msg:
                raise RuntimeError(
                    "SQLite FTS5 is required but not available in this Python/sqlite3 build. "
                    "Install a distro sqlite3 package with FTS5 enabled or rebuild sqlite3 with FTS5. "
                    "(Symptom: 'no such module: fts5')"
                ) from e
            raise

        # Store schema version.
        cur.execute("SELECT value FROM meta WHERE key='schema_version';")
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?);",
                (str(SCHEMA_VERSION),),
            )
        else:
            old_ver = int(row["value"])
            if old_ver == SCHEMA_VERSION:
                pass
            elif old_ver == 1 and SCHEMA_VERSION == 2:
                # Migration 1 -> 2: fts table changed from contentless to stored-content.
                # We drop and recreate FTS, then rely on reconciliation scan to repopulate.
                cur.execute("DROP TABLE IF EXISTS fts;")
                try:
                    cur.execute(
                        """
                        CREATE VIRTUAL TABLE fts USING fts5(
                            path UNINDEXED,
                            dir,
                            name,
                            ext,
                            content,
                            tokenize='unicode61 remove_diacritics 2'
                        );
                        """
                    )
                except sqlite3.OperationalError as e:
                    msg = str(e).lower()
                    if "fts5" in msg or "no such module" in msg:
                        raise RuntimeError(
                            "SQLite FTS5 is required but not available in this Python/sqlite3 build. "
                            "Install a distro sqlite3 package with FTS5 enabled or rebuild sqlite3 with FTS5."
                        ) from e
                    raise
                cur.execute("UPDATE meta SET value=? WHERE key='schema_version';", (str(SCHEMA_VERSION),))
            else:
                raise RuntimeError(
                    f"Unsupported schema_version {old_ver} (expected {SCHEMA_VERSION})."
                )

        self.con.commit()

    def upsert_file(
        self,
        *,
        path: str,
        dir: str,
        name: str,
        ext: str,
        size: int,
        mtime_ns: int,
        ctime_ns: int,
        inode: int,
        dev: int,
        mode: int,
        indexed_at_ns: int,
        content_len: int,
        content_sha256: str,
        content_text: str,
    ) -> int:
        """Insert or update a file row and its FTS document. Returns files.id."""
        assert self.con is not None
        cur = self.con.cursor()
        cur.execute("BEGIN;")
        try:
            cur.execute(
                """
                INSERT INTO files(
                    path, dir, name, ext, size, mtime_ns, ctime_ns, inode, dev, mode,
                    indexed_at_ns, content_len, content_sha256
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                    dir=excluded.dir,
                    name=excluded.name,
                    ext=excluded.ext,
                    size=excluded.size,
                    mtime_ns=excluded.mtime_ns,
                    ctime_ns=excluded.ctime_ns,
                    inode=excluded.inode,
                    dev=excluded.dev,
                    mode=excluded.mode,
                    indexed_at_ns=excluded.indexed_at_ns,
                    content_len=excluded.content_len,
                    content_sha256=excluded.content_sha256
                ;
                """,
                (
                    path,
                    dir,
                    name,
                    ext,
                    int(size),
                    int(mtime_ns),
                    int(ctime_ns),
                    int(inode),
                    int(dev),
                    int(mode),
                    int(indexed_at_ns),
                    int(content_len),
                    str(content_sha256),
                ),
            )

            cur.execute("SELECT id FROM files WHERE path=?;", (path,))
            file_id = int(cur.fetchone()["id"])

            # Replace the FTS document for that file.
            cur.execute("DELETE FROM fts WHERE rowid=?;", (file_id,))
            cur.execute(
                "INSERT INTO fts(rowid, path, dir, name, ext, content) VALUES(?,?,?,?,?,?);",
                (file_id, path, dir, name, ext, content_text),
            )

            cur.execute("COMMIT;")
        except Exception:
            try:
                cur.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        return file_id

    def delete_path(self, path: str) -> bool:
        """Delete a file by path. Returns True if it existed."""
        assert self.con is not None
        cur = self.con.cursor()
        cur.execute("SELECT id FROM files WHERE path=?;", (path,))
        row = cur.fetchone()
        if row is None:
            return False
        file_id = int(row["id"])
        cur.execute("BEGIN;")
        try:
            cur.execute("DELETE FROM fts WHERE rowid=?;", (file_id,))
            cur.execute("DELETE FROM files WHERE id=?;", (file_id,))
            cur.execute("COMMIT;")
        except Exception:
            try:
                cur.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        return True

    def file_needs_reindex(self, path: str, mtime_ns: int, size: int) -> bool:
        """Fast check: has mtime/size changed vs stored metadata?"""
        assert self.con is not None
        cur = self.con.cursor()
        cur.execute("SELECT id, mtime_ns, size FROM files WHERE path=?;", (path,))
        row = cur.fetchone()
        if row is None:
            return True
        file_id = int(row["id"])
        if int(row["mtime_ns"]) != int(mtime_ns) or int(row["size"]) != int(size):
            return True
        # Defensive: if metadata exists but the FTS doc is missing, reindex.
        cur.execute("SELECT 1 FROM fts WHERE rowid=?;", (file_id,))
        return cur.fetchone() is None

    def iter_all_paths(self) -> Iterable[str]:
        assert self.con is not None
        cur = self.con.cursor()
        cur.execute("SELECT path FROM files;")
        for row in cur.fetchall():
            yield str(row["path"])

    def query(self, fts_query: str, limit: int = 20) -> list[dict]:
        """Query the FTS index; returns list of dict results."""
        assert self.con is not None
        cur = self.con.cursor()
        cur.execute(
            """
            SELECT
                files.path AS path,
                files.size AS size,
                files.mtime_ns AS mtime_ns,
                bm25(fts) AS score,
                snippet(fts, 4, '[', ']', '…', 10) AS snippet
            FROM fts
            JOIN files ON files.id = fts.rowid
            WHERE fts MATCH ?
            ORDER BY score
            LIMIT ?;
            """,
            (fts_query, int(limit)),
        )
        out: list[dict] = []
        for row in cur.fetchall():
            out.append(
                {
                    "path": row["path"],
                    "size": int(row["size"]),
                    "mtime_ns": int(row["mtime_ns"]),
                    "score": float(row["score"]),
                    "snippet": row["snippet"],
                }
            )
        return out

    def stats(self) -> dict:
        assert self.con is not None
        cur = self.con.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM files;")
        n_files = int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM fts;")
        n_docs = int(cur.fetchone()["n"])
        # Page count * page_size is an approximation of database size.
        cur.execute("PRAGMA page_count;")
        page_count = int(cur.fetchone()[0])
        cur.execute("PRAGMA page_size;")
        page_size = int(cur.fetchone()[0])
        return {
            "files": n_files,
            "docs": n_docs,
            "approx_db_bytes": page_count * page_size,
            "db_path": str(self.path),
        }