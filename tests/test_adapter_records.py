from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from lampstand.records import AdapterRecordStore, derive_record_id, normalize_record
from lampstand.rpc.messages import AdapterRecord, PublishAdapterRecordsRequest, QueryAdapterRecordsRequest
from lampstand.rpc.service import LampstandService
from lampstand.rpc.unixjson import UnixJsonClient, UnixJsonServer


def sample_record(**overrides):
    record = {
        "record_type": "sourceos.lampstand.repo_context_record.v1",
        "title": "Repo context: smart-tree",
        "object_kind": "repo_context",
        "path_ref": "~/dev/smart-tree",
        "snippet": "Smart Tree SourceOS adapter context record",
        "handling_tags": ["local-only", "smart-tree"],
        "policy_decision": {"decision": "allow"},
        "source": {"system": "sourceos-smart-tree-adapter"},
        "classification": "local_only",
    }
    record.update(overrides)
    return record


class TestAdapterRecordStore(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._db_path = Path(self._td.name) / "index.sqlite3"
        self._store = AdapterRecordStore(self._db_path)
        self._store.open()

    def tearDown(self):
        self._store.close()
        self._td.cleanup()

    def test_normalize_derives_stable_record_id(self):
        one = normalize_record(sample_record())
        two = normalize_record(sample_record())
        self.assertEqual(one["record_id"], two["record_id"])
        self.assertTrue(one["record_id"].startswith("lampstand-adapter-record::sha256:"))

    def test_explicit_record_id_is_preserved(self):
        record = normalize_record(sample_record(record_id="explicit-id"))
        self.assertEqual(record["record_id"], "explicit-id")

    def test_missing_required_field_fails(self):
        bad = sample_record()
        bad.pop("title")
        with self.assertRaises(ValueError):
            normalize_record(bad)

    def test_upsert_is_idempotent(self):
        rid1 = self._store.upsert_record(sample_record())
        rid2 = self._store.upsert_record(sample_record())
        self.assertEqual(rid1, rid2)
        stats = self._store.stats()
        self.assertEqual(stats["adapter_records"], 1)
        self.assertEqual(stats["adapter_records_fts"], 1)

    def test_query_records_finds_published_summary(self):
        self._store.upsert_record(sample_record())
        hits = self._store.query_records("smart-tree", limit=10)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["object_kind"], "repo_context")
        self.assertIn("smart-tree", hits[0]["path_ref"])


class TestLampstandServiceAdapterRecords(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._db_path = Path(self._td.name) / "index.sqlite3"
        self._svc = LampstandService(db_path=self._db_path)

    def tearDown(self):
        self._svc.close()
        self._td.cleanup()

    def _adapter_record(self) -> AdapterRecord:
        payload = sample_record()
        payload["handling_tags"] = tuple(payload["handling_tags"])
        return AdapterRecord(**payload)

    def test_publish_dry_run_does_not_write(self):
        req = PublishAdapterRecordsRequest(records=(self._adapter_record(),), dry_run=True)
        resp = self._svc.PublishAdapterRecords(req)
        self.assertTrue(resp.dry_run)
        self.assertEqual(resp.accepted, 1)
        self.assertEqual(resp.published, 0)
        self.assertEqual(self._svc.AdapterRecordStats().stats["adapter_records"], 0)

    def test_publish_writes_and_query_finds_record(self):
        req = PublishAdapterRecordsRequest(records=(self._adapter_record(),), dry_run=False)
        resp = self._svc.PublishAdapterRecords(req)
        self.assertFalse(resp.dry_run)
        self.assertEqual(resp.accepted, 1)
        self.assertEqual(resp.published, 1)

        query = self._svc.QueryAdapterRecords(QueryAdapterRecordsRequest(query="smart-tree", limit=10))
        self.assertEqual(len(query.hits), 1)
        self.assertEqual(query.hits[0].object_kind, "repo_context")

    def test_repeated_publish_is_idempotent(self):
        req = PublishAdapterRecordsRequest(records=(self._adapter_record(),), dry_run=False)
        first = self._svc.PublishAdapterRecords(req)
        second = self._svc.PublishAdapterRecords(req)
        self.assertEqual(first.record_ids, second.record_ids)
        self.assertEqual(self._svc.AdapterRecordStats().stats["adapter_records"], 1)


class TestUnixJsonAdapterRecords(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        root = Path(self._td.name)
        self._svc = LampstandService(db_path=root / "index.sqlite3")
        self._socket_path = root / "lamp.sock"
        self._server = UnixJsonServer(socket_path=self._socket_path, service=self._svc)
        self._server.start()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._client = UnixJsonClient(socket_path=self._socket_path)

    def tearDown(self):
        self._server.stop()
        self._svc.close()
        self._td.cleanup()

    def test_publish_query_and_stats_via_unixjson(self):
        publish = self._client.call(
            "PublishAdapterRecords",
            {"records": [sample_record()], "dry_run": False},
        )
        self.assertEqual(publish["accepted"], 1)
        self.assertEqual(publish["published"], 1)

        query = self._client.call("QueryAdapterRecords", {"query": "smart-tree", "limit": 10})
        self.assertEqual(len(query["hits"]), 1)
        self.assertEqual(query["hits"][0]["object_kind"], "repo_context")

        stats = self._client.call("AdapterRecordStats", {})
        self.assertEqual(stats["stats"]["adapter_records"], 1)


if __name__ == "__main__":
    unittest.main()
