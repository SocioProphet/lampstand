from __future__ import annotations

import json
import os
import socket
import threading
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .messages import HealthResponse, ReindexRequest, SearchRequest, StatsResponse
from .service import LampstandService


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    return obj


class UnixJsonServer:
    """Tiny dev/test transport: Unix domain socket + JSON lines.

    This exists only so we can run the service boundary without depending on
    TriTRPC in the build environment.

    Production should use TriTRPC.
    """

    def __init__(self, *, socket_path: Path, service: LampstandService) -> None:
        self.socket_path = socket_path
        self.service = service
        self._sock: Optional[socket.socket] = None
        self._stop = threading.Event()

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        # Best-effort cleanup of stale socket.
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(str(self.socket_path))
        s.listen(16)
        self._sock = s

    def serve_forever(self) -> None:
        assert self._sock is not None, "call start() first"
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                break
            try:
                self._handle_conn(conn)
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _handle_conn(self, conn: socket.socket) -> None:
        # Request is a single JSON line.
        data = b""
        while b"\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                return
            data += chunk
            if len(data) > 10_000_000:
                # Hard cap: avoid unbounded memory in dev transport.
                return
        line, _rest = data.split(b"\n", 1)
        try:
            req = json.loads(line.decode("utf-8"))
        except Exception:
            self._send(conn, {"ok": False, "error": "invalid_json"})
            return

        method = req.get("method")
        params = req.get("params") or {}

        try:
            result = self._dispatch(method, params)
        except Exception as e:  # pragma: no cover
            self._send(conn, {"ok": False, "error": repr(e)})
            return

        self._send(conn, {"ok": True, "result": _to_jsonable(result)})

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "Search":
            r = SearchRequest(**params)
            return self.service.Search(r)
        if method == "Stats":
            return self.service.Stats()
        if method == "Health":
            return self.service.Health()
        if method == "Reindex":
            r = ReindexRequest(**params)
            return self.service.Reindex(r)
        raise ValueError(f"unknown method: {method}")

    def _send(self, conn: socket.socket, payload: dict[str, Any]) -> None:
        msg = json.dumps(payload, sort_keys=True).encode("utf-8") + b"\n"
        conn.sendall(msg)

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass


class UnixJsonClient:
    def __init__(self, *, socket_path: Path) -> None:
        self.socket_path = socket_path

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        req = {"method": method, "params": params}
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(str(self.socket_path))
        try:
            s.sendall(json.dumps(req).encode("utf-8") + b"\n")
            data = b""
            while b"\n" not in data:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                if len(data) > 10_000_000:
                    raise RuntimeError("response too large")
            line = data.split(b"\n", 1)[0]
            resp = json.loads(line.decode("utf-8"))
            if not resp.get("ok"):
                raise RuntimeError(resp.get("error") or "rpc_error")
            return resp.get("result")
        finally:
            try:
                s.close()
            except OSError:
                pass
