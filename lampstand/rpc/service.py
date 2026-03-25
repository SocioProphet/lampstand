from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from ..db import IndexDB
from .messages import (
    HealthResponse,
    ReindexRequest,
    ReindexResponse,
    SearchRequest,
    SearchResponse,
    SearchHit,
    StatsResponse,
)


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
    ) -> None:
        self._db = IndexDB(db_path)
        self._db.open()
        self._request_reindex = request_reindex
        self._get_health_details = get_health_details

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

    def Reindex(self, req: ReindexRequest) -> ReindexResponse:
        if not self._request_reindex:
            return ReindexResponse(accepted=0)
        paths = [Path(p).expanduser() for p in req.paths]
        accepted = int(self._request_reindex(paths))
        return ReindexResponse(accepted=accepted)
