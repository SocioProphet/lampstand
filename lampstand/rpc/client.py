from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .unixjson import UnixJsonClient
from . import tritrpc as tritrpc_transport


class RpcClient:
    """High-level RPC client used by the CLI and future adapters.

    We hide transport specifics behind a minimal `.call(method, payload)`
    contract so everything above this layer stays stable.
    """

    def __init__(self, *, transport: str, socket_path: Optional[Path] = None) -> None:
        self.transport = (transport or "auto").lower().strip()
        self.socket_path = socket_path

        if self.transport == "auto":
            self.transport = "tritrpc" if tritrpc_transport.is_available() else "unixjson"

        if self.transport == "unixjson":
            if socket_path is None:
                raise ValueError("socket_path required for unixjson client")
            self._client = UnixJsonClient(socket_path=socket_path)
        elif self.transport == "tritrpc":
            if not tritrpc_transport.is_available():
                raise RuntimeError("TriTRPC client requested but TriTRPC is not available in this environment.")
            self._client = tritrpc_transport.TriTRPCClient()
        else:
            raise ValueError(f"unknown transport: {transport}")

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Both UnixJsonClient and TriTRPCClient are expected to implement `.call`.
        return self._client.call(method, payload)

    def search(self, query: str, *, limit: int = 20, snippet: bool = False) -> dict[str, Any]:
        return self._call(
            "Search",
            {"query": query, "limit": int(limit), "snippet": bool(snippet)},
        )

    def stats(self) -> dict[str, Any]:
        return self._call("Stats", {})

    def health(self) -> dict[str, Any]:
        return self._call("Health", {})

    def reindex(self, paths: list[str]) -> dict[str, Any]:
        return self._call("Reindex", {"paths": paths})
