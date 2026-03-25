from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .service import LampstandService
from .unixjson import UnixJsonServer
from . import tritrpc as tritrpc_transport


@dataclass(frozen=True)
class RpcHandle:
    transport: str
    thread: Optional[threading.Thread]
    stop: Callable[[], None]


def start_rpc_server(
    *,
    transport: str,
    db_path: Path,
    socket_path: Optional[Path],
    request_reindex: Optional[Callable[[list[Path]], int]] = None,
    get_health_details: Optional[Callable[[], dict]] = None,
) -> RpcHandle:
    """Start the RPC server.

    Supported transports:
      - `tritrpc` : SocioProphet TriTRPC (platform standard; stubbed here)
      - `unixjson`: Unix socket + JSON lines (dev/test fallback)
      - `none`    : disables RPC entirely
      - `auto`    : tritrpc if available else unixjson

    Notes:
      - unixjson runs in a background thread and returns a stop() function.
      - tritrpc binding is expected to block in production; in this sandbox we
        run it in a thread but the implementation is a stub.
    """
    transport = (transport or "auto").lower().strip()

    if transport == "auto":
        transport = "tritrpc" if tritrpc_transport.is_available() else "unixjson"

    if transport == "none":
        return RpcHandle(transport="none", thread=None, stop=lambda: None)

    if transport == "tritrpc":
        if not tritrpc_transport.is_available():
            raise RuntimeError("TriTRPC requested but TriTRPC is not available in this environment.")
        svc = LampstandService(
            db_path=db_path,
            request_reindex=request_reindex,
            get_health_details=get_health_details,
        )

        def _stop() -> None:
            try:
                svc.close()
            except Exception:
                pass

        t = threading.Thread(
            target=tritrpc_transport.serve_tritrpc,
            kwargs={"service": svc, "config_path": None},
            daemon=True,
            name="lampstand-tritrpc-server",
        )
        t.start()
        return RpcHandle(transport="tritrpc", thread=t, stop=_stop)

    if transport == "unixjson":
        if socket_path is None:
            raise ValueError("socket_path required for unixjson transport")
        svc = LampstandService(
            db_path=db_path,
            request_reindex=request_reindex,
            get_health_details=get_health_details,
        )
        server = UnixJsonServer(socket_path=socket_path, service=svc)
        server.start()

        t = threading.Thread(target=server.serve_forever, daemon=True, name="lampstand-unixjson")
        t.start()

        def _stop() -> None:
            try:
                server.stop()
            finally:
                try:
                    svc.close()
                except Exception:
                    pass

        return RpcHandle(transport="unixjson", thread=t, stop=_stop)

    raise ValueError(f"unknown rpc transport: {transport}")
