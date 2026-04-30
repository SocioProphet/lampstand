# Lampstand Local Query Adapter — Contract Spec

**Route identifier:** `lampstand-local-query`
**Lattice plane:** `FederatedQueryPlane`
**Version:** 1 (draft)

---

## 1. Overview

This document defines the contract between **Lampstand** (local desktop indexer) and the
**Lattice federated query plane** that models Lampstand as a first-class local backend.

Lampstand exposes a well-typed local query surface over:
- SQLite metadata + FTS5 full-text index
- TriTRPC (production transport, SocioProphet platform standard)
- Unix-socket JSON lines (`unixjson`, dev/test fallback)

The Lattice plane identifies this backend as `lampstand-local-query`.  Any promotion-ready
result from this adapter can flow into Lattice → Sherlock → DataHub catalog workflows via
the **PromotionCandidate** shape defined in §5.

---

## 2. Route metadata

Every request to `lampstand-local-query` carries a `LocalQueryRequest` envelope:

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | yes | FTS5-compatible query string (terms, Boolean, phrase, fielded) |
| `roots` | `string[]` | no | Absolute directory paths the caller wants searched. Empty = all indexed roots |
| `limit` | `int` | no (default 20) | Maximum result count |
| `snippet` | `bool` | no (default false) | Include FTS5 `snippet()` highlight in each hit |
| `include_file_metadata` | `bool` | no (default false) | Include full file metadata (size, mtime, mode, …) in results |
| `dry_run` | `bool` | no (default false) | Validate route + policy only; **no** SQLite / RPC socket / file path access |
| `policy` | `object` | no | Optional policy override (see §4) |

`LocalQueryResponse`:

| Field | Type | Description |
|---|---|---|
| `hits` | `LocalHit[]` | Ordered list of matching files (empty in dry-run) |
| `stats` | `object` | Query stats (see §3.2) |
| `dry_run_result` | `DryRunResult \| null` | Non-null only when `dry_run=true` |
| `promotion_candidates` | `PromotionCandidate[]` | DataHub-promotable subset (see §5) |

---

## 3. Field shapes

### 3.1 LocalHit

Represents a single matching file from the local index.

```json
{
  "path": "/home/user/docs/budget.xlsx",
  "score": -1.2345,
  "snippet": "quarterly [report] 2024…",
  "file_metadata": {
    "size": 204800,
    "mtime_ns": 1714500000000000000,
    "ctime_ns": 1714500000000000000,
    "inode": 131073,
    "dev": 2049,
    "mode": 33188,
    "ext": "xlsx",
    "dir": "/home/user/docs",
    "name": "budget.xlsx",
    "content_sha256": "e3b0c44298fc1c149afb…"
  }
}
```

`file_metadata` is present only when `include_file_metadata=true` is requested.

### 3.2 Query stats

Included in every response (including dry-run).

```json
{
  "hit_count": 3,
  "query_time_ms": 4,
  "index_files": 12043,
  "index_docs": 12043,
  "approx_db_bytes": 52428800,
  "roots_searched": ["/home/user"]
}
```

In **dry-run** mode the index fields (`index_files`, `index_docs`, `approx_db_bytes`) are
`null` (no SQLite access), and `hit_count` is `0`.

---

## 4. Policy

The `policy` object in `LocalQueryRequest` may override per-route behavior:

| Key | Type | Default | Description |
|---|---|---|---|
| `volume_policy` | `"off" \| "local" \| "portable-encrypted"` | `"local"` | Whether and how this volume may be queried |
| `max_results` | `int` | 20 | Hard cap applied before caller's `limit` |
| `allow_content_search` | `bool` | `true` | Allow searching file *content* tokens (not just metadata) |
| `exclude_dirs` | `string[]` | `[]` | Additional directories to suppress from results |

Dry-run validates that `volume_policy != "off"` and `max_results >= 1` without accessing
the filesystem or index.

---

## 5. DataHub promotion candidate

A `PromotionCandidate` represents a search hit that has been promoted to a catalog-level
entity ready for ingestion by DataHub / Lattice / Sherlock.

```json
{
  "candidate_id": "lampstand-local-query::sha256:<hex32>",
  "source": "lampstand-local-query",
  "lattice_plane": "FederatedQueryPlane",
  "entity_type": "LocalFile",
  "path": "/home/user/docs/budget.xlsx",
  "score": -1.2345,
  "snippet": "quarterly [report] 2024…",
  "file_metadata": { "...": "..." },
  "query": "quarterly report",
  "roots": ["/home/user/docs"],
  "promoted_at_ns": 1714500001000000000
}
```

`candidate_id` is deterministic:
```
"lampstand-local-query::sha256:" + SHA-256( path + "|" + query )[:32]
```

The caller (Lattice integration layer) is responsible for forwarding these objects to the
DataHub ingest API.  Lampstand does **not** make network calls.

---

## 6. Dry-run behavior

When `dry_run=true` Lampstand **must not**:
- Open or read any SQLite database
- Connect to or listen on any RPC socket
- `stat()`, `open()`, or read any file path listed in `roots`

Lampstand **must**:
- Parse and validate the `query` string (reject empty strings, oversized queries)
- Validate `roots` syntax (must be absolute paths if provided; rejects relative paths)
- Validate `policy` fields (type and range checks only)
- Return a `DryRunResult` with a list of validation findings

### DryRunResult shape

```json
{
  "valid": true,
  "findings": [],
  "validated_fields": ["query", "roots", "policy", "limit", "snippet"]
}
```

Finding shape:
```json
{
  "field": "roots[0]",
  "severity": "error",
  "message": "Root path must be absolute, got 'relative/path'"
}
```

Severity levels: `"error"` (request will be rejected), `"warning"` (request proceeds with
caveat), `"info"` (informational only).

---

## 7. Mapping to Lattice FederatedQueryPlane

```
FederatedQueryPlane.route("lampstand-local-query")
  .request  -> LocalQueryRequest
  .response -> LocalQueryResponse

FederatedQueryPlane.dry_run("lampstand-local-query")
  .request  -> LocalQueryRequest { dry_run: true }
  .response -> LocalQueryResponse { dry_run_result: DryRunResult }
```

The adapter registers itself as `lampstand-local-query` in the Lattice plane registry.
Lattice uses the `dry_run` flag to probe adapter health **without side effects** before
routing live queries.

---

## 8. Wire encoding

| Transport | Encoding |
|---|---|
| TriTRPC (production) | TriTRPC binary framing (platform standard) |
| unixjson (dev/test) | `{"method":"LocalQuery","params":{…}}\n` |

Both transports use the same field names as above.  The unixjson `DryRun` method is a
convenience alias for `LocalQuery` with `dry_run=true`.

---

## 9. Security and privacy notes

- Lampstand indexes are stored locally; no results leave the machine unless the caller
  (Lattice integration layer) explicitly promotes a `PromotionCandidate` to DataHub.
- The `candidate_id` hash is derived from path + query; it does **not** embed file
  content.
- In dry-run mode the adapter performs zero I/O; it is safe to call from sandboxed or
  policy-restricted contexts.
- `volume_policy="off"` causes the adapter to refuse the query entirely (returns an error,
  not empty results).

---

## 10. Reference implementation files

| File | Role |
|---|---|
| `lampstand/rpc/messages.py` | `LocalQueryRequest`, `LocalQueryResponse`, `LocalHit`, `FileMetadata`, `QueryStats`, `PromotionCandidate`, `DryRunRequest`, `DryRunResult`, `DryRunFinding` |
| `lampstand/rpc/service.py` | `LampstandService.LocalQuery()`, `LampstandService.DryRun()` |
| `lampstand/rpc/unixjson.py` | Dispatch for `LocalQuery` and `DryRun` methods |
| `tests/test_local_query_adapter.py` | Fixture-based validation tests |
