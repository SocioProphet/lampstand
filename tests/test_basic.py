import os
import tempfile
import unittest
from pathlib import Path

from lampstand.db import IndexDB
from lampstand.indexer import Indexer
from lampstand.scan import full_scan


class TestBasicIndexing(unittest.TestCase):
    def test_index_and_query(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("hello world", encoding="utf-8")
            (root / "b.md").write_text("quarterly report 2024", encoding="utf-8")

            db_path = root / "index.sqlite3"
            db = IndexDB(db_path)
            db.open()
            try:
                indexer = Indexer(db)
                res = full_scan(indexer, [root])
                self.assertGreaterEqual(res["indexed"], 2)

                out = db.query("report", limit=10)
                paths = [r["path"] for r in out]
                self.assertTrue(any(p.endswith("b.md") for p in paths))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
