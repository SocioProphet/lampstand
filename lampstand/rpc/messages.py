from __future__ import annotations

from dataclasses import dataclass
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
