from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SearchRequest:
    query: str
    limit: int = 20
    snippet: bool = False


@dataclass(frozen=True)
class SearchHit:
    path: str
    score: float
    snippet: Optional[str] = None


@dataclass(frozen=True)
class SearchResponse:
    hits: list[SearchHit]


@dataclass(frozen=True)
class StatsResponse:
    stats: dict[str, Any]


@dataclass(frozen=True)
class HealthResponse:
    ok: bool
    details: dict[str, Any]


@dataclass(frozen=True)
class ReindexRequest:
    # Paths to (re)index. Directories imply recursive.
    paths: list[str]


@dataclass(frozen=True)
class ReindexResponse:
    accepted: int


# ---------------------------------------------------------------------------
# Root hints — local-state root discovery for Smart Tree and other adapters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RootHint:
    """A Lampstand-owned local root that may be enriched by downstream tools."""

    source_root_id: str
    path: str
    root_kind: str = "local_root"
    freshness: Optional[dict[str, Any]] = None
    classification: str = "local_only"
    handling_tags: tuple[str, ...] = ("local-only",)


@dataclass(frozen=True)
class RootHintsResponse:
    """Read-only list of Lampstand-owned roots.

    Downstream tools must treat these as hints, not authorization. Policy Fabric
    still decides whether a specific root may be enriched.
    """

    roots: tuple[RootHint, ...]
    adapter_mode: str = "rpc"


# ---------------------------------------------------------------------------
# Local query adapter — Lattice FederatedQueryPlane / lampstand-local-query
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LocalQueryPolicy:
    """Per-request policy overrides for the local query adapter."""

    volume_policy: str = "local"          # "off" | "local" | "portable-encrypted"
    max_results: int = 20
    allow_content_search: bool = True
    exclude_dirs: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalQueryRequest:
    """Request envelope for the lampstand-local-query Lattice route.

    When *dry_run* is True the service validates route + policy without
    opening SQLite, RPC sockets, or any file path.
    """

    query: str
    roots: tuple[str, ...] = ()
    limit: int = 20
    snippet: bool = False
    include_file_metadata: bool = False
    dry_run: bool = False
    policy: Optional[LocalQueryPolicy] = None


@dataclass(frozen=True)
class FileMetadata:
    """Per-file stat metadata returned with search hits."""

    size: int
    mtime_ns: int
    ctime_ns: int
    inode: int
    dev: int
    mode: int
    ext: str
    dir: str
    name: str
    content_sha256: str


@dataclass(frozen=True)
class LocalHit:
    """A single file match from the local index."""

    path: str
    score: float
    snippet: Optional[str] = None
    file_metadata: Optional[FileMetadata] = None


@dataclass(frozen=True)
class QueryStats:
    """Per-query statistics included in every LocalQueryResponse."""

    hit_count: int
    query_time_ms: float
    # These are None in dry-run mode (no SQLite access).
    index_files: Optional[int] = None
    index_docs: Optional[int] = None
    approx_db_bytes: Optional[int] = None
    roots_searched: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromotionCandidate:
    """DataHub-promotable entity representing a local-index search hit.

    Suitable for ingestion into Lattice / Sherlock / DataHub catalog workflows.
    The caller (Lattice integration layer) is responsible for forwarding these
    objects to the DataHub ingest API; Lampstand makes no network calls.
    """

    candidate_id: str           # "lampstand-local-query::sha256:<hex32>"
    source: str                 # always "lampstand-local-query"
    lattice_plane: str          # always "FederatedQueryPlane"
    entity_type: str            # "LocalFile"
    path: str
    score: float
    query: str
    roots: tuple[str, ...]
    promoted_at_ns: int
    snippet: Optional[str] = None
    file_metadata: Optional[FileMetadata] = None


@dataclass(frozen=True)
class DryRunFinding:
    """A single validation finding from a dry-run check."""

    field: str
    severity: str       # "error" | "warning" | "info"
    message: str


@dataclass(frozen=True)
class DryRunResult:
    """Outcome of a dry-run validation (no I/O performed)."""

    valid: bool
    findings: tuple[DryRunFinding, ...]
    validated_fields: tuple[str, ...]


@dataclass(frozen=True)
class LocalQueryResponse:
    """Response envelope for the lampstand-local-query Lattice route."""

    hits: tuple[LocalHit, ...]
    stats: QueryStats
    promotion_candidates: tuple[PromotionCandidate, ...]
    dry_run_result: Optional[DryRunResult] = None
