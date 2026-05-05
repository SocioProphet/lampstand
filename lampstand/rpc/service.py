from __future__ import annotations

import hashlib
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from ..db import IndexDB
from .messages import (
    DryRunFinding,
    DryRunResult,
    FileMetadata,
    HealthResponse,
    LocalHit,
    LocalQueryPolicy,
    LocalQueryRequest,
    LocalQueryResponse,
    PromotionCandidate,
    QueryStats,
    ReindexRequest,
    ReindexResponse,
    RootHint,
    RootHintsResponse,
    SearchRequest,
    SearchResponse,
    SearchHit,
    StatsResponse,
)

# ---------------------------------------------------------------------------
# Dry-run validation helpers (no I/O)
# ---------------------------------------------------------------------------

_MAX_QUERY_BYTES = 4096
_VALID_VOLUME_POLICIES = {"off", "local", "portable-encrypted"}


def _validate_dry_run(req: LocalQueryRequest) -> DryRunResult:
    """Pure validation: no filesystem, SQLite, or socket access."""
    findings: list[DryRunFinding] = []
    validated: list[str] = []

    # --- query ---
    validated.append("query")
    if not req.query or not req.query.strip():
        findings.append(DryRunFinding(
            field="query",
            severity="error",
            message="query must be a non-empty string",
        ))
    elif len(req.query.encode()) > _MAX_QUERY_BYTES:
        findings.append(DryRunFinding(
            field="query",
            severity="error",
            message=f"query exceeds maximum length of {_MAX_QUERY_BYTES} bytes",
        ))

    # --- roots ---
    validated.append("roots")
    for i, root in enumerate(req.roots):
        if not root:
            findings.append(DryRunFinding(
                field=f"roots[{i}]",
                severity="error",
                message="root path must not be empty",
            ))
        elif not Path(root).is_absolute():
            findings.append(DryRunFinding(
                field=f"roots[{i}]",
                severity="error",
                message=f"root path must be absolute, got {root!r}",
            ))

    # --- limit ---
    validated.append("limit")
    if req.limit < 1:
        findings.append(DryRunFinding(
            field="limit",
            severity="error",
            message=f"limit must be >= 1, got {req.limit}",
        ))
    elif req.limit > 1000:
        findings.append(DryRunFinding(
            field="limit",
            severity="warning",
            message=f"limit {req.limit} is large; performance may be affected",
        ))

    # --- snippet ---
    validated.append("snippet")

    # --- policy ---
    validated.append("policy")
    policy = req.policy or LocalQueryPolicy()
    if policy.volume_policy not in _VALID_VOLUME_POLICIES:
        findings.append(DryRunFinding(
            field="policy.volume_policy",
            severity="error",
            message=(
                f"volume_policy must be one of {sorted(_VALID_VOLUME_POLICIES)}, "
                f"got {policy.volume_policy!r}"
            ),
        ))
    if policy.volume_policy == "off":
        findings.append(DryRunFinding(
            field="policy.volume_policy",
            severity="error",
            message="volume_policy='off' disables querying; request will be rejected",
        ))
    if policy.max_results < 1:
        findings.append(DryRunFinding(
            field="policy.max_results",
            severity="error",
            message=f"policy.max_results must be >= 1, got {policy.max_results}",
        ))

    valid = not any(f.severity == "error" for f in findings)
    return DryRunResult(
        valid=valid,
        findings=tuple(findings),
        validated_fields=tuple(validated),
    )


def _make_candidate_id(path: str, query: str) -> str:
    raw = f"{path}|{query}".encode()
    return "lampstand-local-query::sha256:" + hashlib.sha256(raw).hexdigest()[:32]


def _make_root_id(path: Path) -> str:
    return "lampstand-root::sha256:" + hashlib.sha256(str(path).encode()).hexdigest()[:32]


class LampstandService:
    """Transport-agnostic service implementation.

    NOTE: This class intentionally does *not* know about inotify, fanotify, GNOME,
    or any desktop environment. It speaks only in terms of RPC requests and
    responses.

    A transport adapter (TriTRPC, unix-json, etc.) binds these methods.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        request_reindex: Optional[Callable[[list[Path]], int]] = None,
        get_health_details: Optional[Callable[[], dict]] = None,
        get_roots: Optional[Callable[[], list[Path]]] = None,
    ) -> None:
        self._db = IndexDB(db_path)
        self._db.open()
        self._request_reindex = request_reindex
        self._get_health_details = get_health_details
        self._get_roots = get_roots

    def close(self) -> None:
        self._db.close()

    # ---- RPC methods ----

    def Search(self, req: SearchRequest) -> SearchResponse:
        rows = self._db.query(req.query, limit=int(req.limit))
        hits: list[SearchHit] = []
        for r in rows:
            hits.append(
                SearchHit(
                    path=str(r["path"]),
                    score=float(r["score"]),
                    snippet=str(r["snippet"]) if req.snippet and r.get("snippet") else None,
                )
            )
        return SearchResponse(hits=hits)

    def Stats(self) -> StatsResponse:
        return StatsResponse(stats=self._db.stats())

    def Health(self) -> HealthResponse:
        details: dict = {"db_path": str(self._db.path)}
        if self._get_health_details:
            try:
                details.update(self._get_health_details())
            except Exception as e:  # pragma: no cover
                details["health_cb_error"] = repr(e)
        return HealthResponse(ok=True, details=details)

    def RootHints(self) -> RootHintsResponse:
        """Return Lampstand-owned root hints without granting authorization.

        Downstream enrichers such as Smart Tree must still apply their own
        Policy Fabric profile before scanning any returned root.
        """
        roots = []
        if self._get_roots:
            for raw in self._get_roots():
                path = Path(raw).expanduser().resolve()
                roots.append(
                    RootHint(
                        source_root_id=_make_root_id(path),
                        path=str(path),
                        root_kind="local_root",
                        freshness=None,
                        classification="local_only",
                        handling_tags=("local-only", "lampstand-root"),
                    )
                )
        return RootHintsResponse(roots=tuple(roots), adapter_mode="rpc")

    def Reindex(self, req: ReindexRequest) -> ReindexResponse:
        if not self._request_reindex:
            return ReindexResponse(accepted=0)
        paths = [Path(p).expanduser() for p in req.paths]
        accepted = int(self._request_reindex(paths))
        return ReindexResponse(accepted=accepted)

    def DryRun(self, req: LocalQueryRequest) -> LocalQueryResponse:
        """Validate route + policy without opening SQLite, sockets, or files."""
        dry_req = LocalQueryRequest(
            query=req.query,
            roots=req.roots,
            limit=req.limit,
            snippet=req.snippet,
            include_file_metadata=req.include_file_metadata,
            dry_run=True,
            policy=req.policy,
        )
        return self.LocalQuery(dry_req)

    def LocalQuery(self, req: LocalQueryRequest) -> LocalQueryResponse:
        """Execute a local query or (when dry_run=True) validate without I/O.

        Lattice FederatedQueryPlane route: lampstand-local-query
        """
        t0_ns = time.monotonic_ns()

        # --- dry-run: validate only, no I/O ---
        if req.dry_run:
            dry_result = _validate_dry_run(req)
            elapsed_ms = (time.monotonic_ns() - t0_ns) / 1_000_000
            return LocalQueryResponse(
                hits=(),
                stats=QueryStats(
                    hit_count=0,
                    query_time_ms=elapsed_ms,
                    # No SQLite access in dry-run.
                    index_files=None,
                    index_docs=None,
                    approx_db_bytes=None,
                    roots_searched=req.roots,
                ),
                promotion_candidates=(),
                dry_run_result=dry_result,
            )

        # --- policy check (before any I/O) ---
        policy = req.policy or LocalQueryPolicy()
        if policy.volume_policy == "off":
            raise ValueError(
                "volume_policy='off': querying is disabled by policy for this route"
            )

        effective_limit = min(req.limit, policy.max_results)

        # --- live query ---
        rows = self._db.query(req.query, limit=effective_limit)
        db_stats = self._db.stats()

        hits: list[LocalHit] = []
        candidates: list[PromotionCandidate] = []
        now_ns = time.monotonic_ns()

        for r in rows:
            file_meta: Optional[FileMetadata] = None
            if req.include_file_metadata:
                file_meta = FileMetadata(
                    size=int(r["size"]),
                    mtime_ns=int(r["mtime_ns"]),
                    ctime_ns=int(r.get("ctime_ns", 0)),
                    inode=int(r.get("inode", 0)),
                    dev=int(r.get("dev", 0)),
                    mode=int(r.get("mode", 0)),
                    ext=str(r.get("ext", "")),
                    dir=str(r.get("dir", "")),
                    name=str(r.get("name", "")),
                    content_sha256=str(r.get("content_sha256", "")),
                )

            raw_snip = r.get("snippet")
            snip: Optional[str] = str(raw_snip) if req.snippet and raw_snip else None

            hits.append(LocalHit(
                path=str(r["path"]),
                score=float(r["score"]),
                snippet=snip,
                file_metadata=file_meta,
            ))

            candidates.append(PromotionCandidate(
                candidate_id=_make_candidate_id(str(r["path"]), req.query),
                source="lampstand-local-query",
                lattice_plane="FederatedQueryPlane",
                entity_type="LocalFile",
                path=str(r["path"]),
                score=float(r["score"]),
                query=req.query,
                roots=req.roots,
                promoted_at_ns=now_ns,
                snippet=snip,
                file_metadata=file_meta,
            ))

        elapsed_ms = (time.monotonic_ns() - t0_ns) / 1_000_000
        return LocalQueryResponse(
            hits=tuple(hits),
            stats=QueryStats(
                hit_count=len(hits),
                query_time_ms=elapsed_ms,
                index_files=int(db_stats.get("files", 0)),
                index_docs=int(db_stats.get("docs", 0)),
                approx_db_bytes=int(db_stats.get("approx_db_bytes", 0)),
                roots_searched=req.roots,
            ),
            promotion_candidates=tuple(candidates),
            dry_run_result=None,
        )
