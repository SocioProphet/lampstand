"""Tests for the lampstand-local-query adapter contract.

Covers:
- DryRunResult shape and validation logic (no I/O)
- LocalQueryRequest / LocalQueryResponse / PromotionCandidate shapes
- LampstandService.DryRun() and LampstandService.LocalQuery()
- LampstandService.RootHints()
- unixjson dispatch for LocalQuery, DryRun, and RootHints methods
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from lampstand.db import IndexDB
from lampstand.indexer import Indexer
from lampstand.rpc.messages import (
    DryRunFinding,
    DryRunResult,
    LocalQueryPolicy,
    LocalQueryRequest,
    PromotionCandidate,
    QueryStats,
    RootHint,
    RootHintsResponse,
)
from lampstand.rpc.service import LampstandService, _make_candidate_id, _validate_dry_run
from lampstand.rpc.unixjson import UnixJsonClient, UnixJsonServer
from lampstand.scan import full_scan


# ---------------------------------------------------------------------------
# Dry-run validation unit tests (pure, no I/O)
# ---------------------------------------------------------------------------

class TestDryRunValidation(unittest.TestCase):
    """_validate_dry_run() must never touch the filesystem, SQLite, or sockets."""

    def _req(self, **kwargs) -> LocalQueryRequest:
        defaults = dict(query="hello", roots=("/home/user",), dry_run=True)
        defaults.update(kwargs)
        return LocalQueryRequest(**defaults)

    def test_valid_request_passes(self):
        result = _validate_dry_run(self._req())
        self.assertTrue(result.valid)
        self.assertEqual(result.findings, ())
        self.assertIn("query", result.validated_fields)
        self.assertIn("roots", result.validated_fields)
        self.assertIn("policy", result.validated_fields)

    def test_empty_query_is_error(self):
        result = _validate_dry_run(self._req(query=""))
        self.assertFalse(result.valid)
        errors = [f for f in result.findings if f.severity == "error" and f.field == "query"]
        self.assertTrue(errors, "expected an error finding on 'query'")

    def test_whitespace_only_query_is_error(self):
        result = _validate_dry_run(self._req(query="   "))
        self.assertFalse(result.valid)

    def test_oversized_query_is_error(self):
        big = "x" * 5000
        result = _validate_dry_run(self._req(query=big))
        self.assertFalse(result.valid)
        self.assertTrue(any(f.field == "query" for f in result.findings))

    def test_relative_root_is_error(self):
        result = _validate_dry_run(self._req(roots=("relative/path",)))
        self.assertFalse(result.valid)
        errors = [f for f in result.findings if "roots[0]" in f.field]
        self.assertTrue(errors)

    def test_empty_root_is_error(self):
        result = _validate_dry_run(self._req(roots=("",)))
        self.assertFalse(result.valid)

    def test_limit_zero_is_error(self):
        result = _validate_dry_run(self._req(limit=0))
        self.assertFalse(result.valid)

    def test_limit_large_is_warning_not_error(self):
        result = _validate_dry_run(self._req(limit=5000))
        warnings = [f for f in result.findings if f.field == "limit" and f.severity == "warning"]
        self.assertTrue(warnings)
        errors = [f for f in result.findings if f.severity == "error"]
        self.assertFalse(errors)
        self.assertTrue(result.valid)

    def test_volume_policy_off_is_error(self):
        policy = LocalQueryPolicy(volume_policy="off")
        result = _validate_dry_run(self._req(policy=policy))
        self.assertFalse(result.valid)
        self.assertTrue(any("off" in f.message for f in result.findings))

    def test_invalid_volume_policy_is_error(self):
        policy = LocalQueryPolicy(volume_policy="unknown")
        result = _validate_dry_run(self._req(policy=policy))
        self.assertFalse(result.valid)

    def test_policy_max_results_zero_is_error(self):
        policy = LocalQueryPolicy(max_results=0)
        result = _validate_dry_run(self._req(policy=policy))
        self.assertFalse(result.valid)

    def test_multiple_roots_mixed_validity(self):
        result = _validate_dry_run(self._req(roots=("/good/path", "bad/path")))
        self.assertFalse(result.valid)
        bad_findings = [f for f in result.findings if "roots[1]" in f.field]
        self.assertTrue(bad_findings)
        good_findings = [f for f in result.findings if "roots[0]" in f.field]
        self.assertFalse(good_findings)


# ---------------------------------------------------------------------------
# candidate_id determinism
# ---------------------------------------------------------------------------

class TestCandidateId(unittest.TestCase):
    def test_deterministic(self):
        cid1 = _make_candidate_id("/home/user/doc.txt", "report")
        cid2 = _make_candidate_id("/home/user/doc.txt", "report")
        self.assertEqual(cid1, cid2)

    def test_different_path_gives_different_id(self):
        cid1 = _make_candidate_id("/home/user/a.txt", "report")
        cid2 = _make_candidate_id("/home/user/b.txt", "report")
        self.assertNotEqual(cid1, cid2)

    def test_different_query_gives_different_id(self):
        cid1 = _make_candidate_id("/home/user/a.txt", "report")
        cid2 = _make_candidate_id("/home/user/a.txt", "invoice")
        self.assertNotEqual(cid1, cid2)

    def test_prefix(self):
        cid = _make_candidate_id("/home/user/a.txt", "q")
        self.assertTrue(cid.startswith("lampstand-local-query::sha256:"), cid)

    def test_hex_length(self):
        cid = _make_candidate_id("/home/user/a.txt", "q")
        hex_part = cid.split("sha256:")[1]
        self.assertEqual(len(hex_part), 32)


# ---------------------------------------------------------------------------
# Shape / dataclass integrity tests (no service needed)
# ---------------------------------------------------------------------------

class TestMessageShapes(unittest.TestCase):
    def test_local_query_request_defaults(self):
        req = LocalQueryRequest(query="test")
        self.assertEqual(req.roots, ())
        self.assertEqual(req.limit, 20)
        self.assertFalse(req.snippet)
        self.assertFalse(req.include_file_metadata)
        self.assertFalse(req.dry_run)
        self.assertIsNone(req.policy)

    def test_local_query_policy_defaults(self):
        p = LocalQueryPolicy()
        self.assertEqual(p.volume_policy, "local")
        self.assertEqual(p.max_results, 20)
        self.assertTrue(p.allow_content_search)
        self.assertEqual(p.exclude_dirs, ())

    def test_root_hint_fields(self):
        hint = RootHint(source_root_id="root-1", path="/home/user/dev", root_kind="local_root")
        self.assertEqual(hint.classification, "local_only")
        self.assertIn("local-only", hint.handling_tags)

    def test_root_hints_response_fields(self):
        hint = RootHint(source_root_id="root-1", path="/home/user/dev")
        resp = RootHintsResponse(roots=(hint,), adapter_mode="rpc")
        self.assertEqual(resp.adapter_mode, "rpc")
        self.assertEqual(len(resp.roots), 1)

    def test_dry_run_finding_fields(self):
        f = DryRunFinding(field="query", severity="error", message="bad")
        self.assertEqual(f.field, "query")
        self.assertEqual(f.severity, "error")

    def test_dry_run_result_fields(self):
        r = DryRunResult(valid=True, findings=(), validated_fields=("query",))
        self.assertTrue(r.valid)
        self.assertEqual(r.validated_fields, ("query",))

    def test_promotion_candidate_fields(self):
        pc = PromotionCandidate(
            candidate_id="lampstand-local-query::sha256:abc123",
            source="lampstand-local-query",
            lattice_plane="FederatedQueryPlane",
            entity_type="LocalFile",
            path="/home/user/doc.txt",
            score=-1.0,
            query="doc",
            roots=("/home/user",),
            promoted_at_ns=1_000_000,
        )
        self.assertEqual(pc.source, "lampstand-local-query")
        self.assertEqual(pc.lattice_plane, "FederatedQueryPlane")
        self.assertEqual(pc.entity_type, "LocalFile")
        self.assertIsNone(pc.snippet)
        self.assertIsNone(pc.file_metadata)

    def test_query_stats_dry_run_nulls(self):
        qs = QueryStats(hit_count=0, query_time_ms=0.5)
        self.assertIsNone(qs.index_files)
        self.assertIsNone(qs.index_docs)
        self.assertIsNone(qs.approx_db_bytes)


# ---------------------------------------------------------------------------
# LampstandService integration tests
# ---------------------------------------------------------------------------

class TestLampstandServiceLocalQuery(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        root = Path(self._td.name)
        (root / "report.txt").write_text("quarterly report 2024", encoding="utf-8")
        (root / "invoice.md").write_text("invoice total 500", encoding="utf-8")

        db_path = root / "index.sqlite3"
        db = IndexDB(db_path)
        db.open()
        indexer = Indexer(db)
        full_scan(indexer, [root])
        db.close()

        self._root = root.resolve()
        self._svc = LampstandService(db_path=db_path, get_roots=lambda: [self._root])

    def tearDown(self):
        self._svc.close()
        self._td.cleanup()

    def test_root_hints_returns_configured_roots(self):
        resp = self._svc.RootHints()
        self.assertEqual(resp.adapter_mode, "rpc")
        self.assertEqual(len(resp.roots), 1)
        hint = resp.roots[0]
        self.assertEqual(hint.path, str(self._root))
        self.assertTrue(hint.source_root_id.startswith("lampstand-root::sha256:"))
        self.assertEqual(hint.classification, "local_only")

    # --- dry-run via service ---

    def test_dry_run_returns_no_hits(self):
        req = LocalQueryRequest(query="report", dry_run=True)
        resp = self._svc.LocalQuery(req)
        self.assertEqual(resp.hits, ())
        self.assertEqual(resp.promotion_candidates, ())
        self.assertIsNotNone(resp.dry_run_result)
        assert resp.dry_run_result is not None
        self.assertTrue(resp.dry_run_result.valid)

    def test_dry_run_stats_has_no_index_fields(self):
        req = LocalQueryRequest(query="report", dry_run=True)
        resp = self._svc.LocalQuery(req)
        self.assertIsNone(resp.stats.index_files)
        self.assertIsNone(resp.stats.index_docs)
        self.assertIsNone(resp.stats.approx_db_bytes)

    def test_dry_run_invalid_query_reflected(self):
        req = LocalQueryRequest(query="", dry_run=True)
        resp = self._svc.LocalQuery(req)
        assert resp.dry_run_result is not None
        self.assertFalse(resp.dry_run_result.valid)

    def test_dry_run_method_alias(self):
        req = LocalQueryRequest(query="report")
        resp = self._svc.DryRun(req)
        self.assertIsNotNone(resp.dry_run_result)
        assert resp.dry_run_result is not None
        self.assertTrue(resp.dry_run_result.valid)

    # --- live query ---

    def test_live_query_returns_hits(self):
        req = LocalQueryRequest(query="report", limit=10)
        resp = self._svc.LocalQuery(req)
        self.assertGreater(len(resp.hits), 0)
        paths = [h.path for h in resp.hits]
        self.assertTrue(any("report.txt" in p for p in paths))

    def test_live_query_returns_promotion_candidates(self):
        req = LocalQueryRequest(query="report", limit=10)
        resp = self._svc.LocalQuery(req)
        self.assertEqual(len(resp.hits), len(resp.promotion_candidates))
        for pc in resp.promotion_candidates:
            self.assertEqual(pc.source, "lampstand-local-query")
            self.assertEqual(pc.lattice_plane, "FederatedQueryPlane")
            self.assertEqual(pc.entity_type, "LocalFile")
            self.assertTrue(pc.candidate_id.startswith("lampstand-local-query::sha256:"))

    def test_live_query_stats_populated(self):
        req = LocalQueryRequest(query="invoice", limit=10)
        resp = self._svc.LocalQuery(req)
        self.assertIsNotNone(resp.stats.index_files)
        self.assertGreater(resp.stats.index_files, 0)  # type: ignore[operator]
        self.assertIsNone(resp.dry_run_result)

    def test_live_query_with_snippet(self):
        req = LocalQueryRequest(query="report", limit=5, snippet=True)
        resp = self._svc.LocalQuery(req)
        self.assertTrue(any(h.snippet is not None for h in resp.hits))

    def test_live_query_with_file_metadata(self):
        req = LocalQueryRequest(query="report", limit=5, include_file_metadata=True)
        resp = self._svc.LocalQuery(req)
        for h in resp.hits:
            self.assertIsNotNone(h.file_metadata)

    def test_policy_off_raises(self):
        policy = LocalQueryPolicy(volume_policy="off")
        req = LocalQueryRequest(query="report", policy=policy)
        with self.assertRaises(ValueError):
            self._svc.LocalQuery(req)

    def test_policy_max_results_caps_limit(self):
        policy = LocalQueryPolicy(max_results=1)
        req = LocalQueryRequest(query="report", limit=100, policy=policy)
        resp = self._svc.LocalQuery(req)
        self.assertLessEqual(len(resp.hits), 1)

    def test_candidate_id_matches_helper(self):
        req = LocalQueryRequest(query="report", limit=10)
        resp = self._svc.LocalQuery(req)
        for hit, pc in zip(resp.hits, resp.promotion_candidates):
            expected = _make_candidate_id(hit.path, req.query)
            self.assertEqual(pc.candidate_id, expected)


# ---------------------------------------------------------------------------
# unixjson transport dispatch
# ---------------------------------------------------------------------------

class TestUnixJsonLocalQuery(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        root = Path(self._td.name)
        (root / "notes.txt").write_text("important notes here", encoding="utf-8")

        db_path = root / "index.sqlite3"
        db = IndexDB(db_path)
        db.open()
        indexer = Indexer(db)
        full_scan(indexer, [root])
        db.close()

        self._root = root.resolve()
        self._svc = LampstandService(db_path=db_path, get_roots=lambda: [self._root])
        self._socket_path = root / "lamp.sock"
        self._server = UnixJsonServer(
            socket_path=self._socket_path,
            service=self._svc,
        )
        self._server.start()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._client = UnixJsonClient(socket_path=self._socket_path)

    def tearDown(self):
        self._server.stop()
        self._svc.close()
        self._td.cleanup()

    def test_root_hints_dispatch(self):
        result = self._client.call("RootHints", {})
        self.assertIn("roots", result)
        self.assertEqual(result["adapter_mode"], "rpc")
        self.assertEqual(len(result["roots"]), 1)
        self.assertEqual(result["roots"][0]["path"], str(self._root))

    def test_local_query_dispatch(self):
        result = self._client.call("LocalQuery", {"query": "notes"})
        self.assertIn("hits", result)
        self.assertIn("stats", result)
        self.assertIn("promotion_candidates", result)

    def test_dry_run_dispatch(self):
        result = self._client.call("DryRun", {"query": "notes"})
        self.assertIn("dry_run_result", result)
        self.assertIsNotNone(result["dry_run_result"])
        self.assertTrue(result["dry_run_result"]["valid"])

    def test_dry_run_invalid_query_via_wire(self):
        result = self._client.call("DryRun", {"query": ""})
        self.assertIsNotNone(result["dry_run_result"])
        self.assertFalse(result["dry_run_result"]["valid"])

    def test_local_query_with_roots_list(self):
        # roots come over the wire as a JSON list; unixjson must convert to tuple.
        result = self._client.call("LocalQuery", {"query": "notes", "roots": ["/home"]})
        self.assertIn("hits", result)

    def test_dry_run_with_relative_root_via_wire(self):
        result = self._client.call("DryRun", {"query": "notes", "roots": ["relative/path"]})
        dr = result.get("dry_run_result", {})
        self.assertFalse(dr.get("valid"))


if __name__ == "__main__":
    unittest.main()
