from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from .db import IndexDB
from .indexer import Indexer, IndexOptions
from .paths import default_db_path, default_socket_path, ensure_dirs
from .scan import full_scan, ScanOptions
from .watcher import TreeWatcher, WatchOptions
from .rpc.runtime import start_rpc_server, RpcHandle


def run_one_shot_index(roots: Iterable[Path], *, db_path: Path | None = None) -> dict:
    ensure_dirs()
    db_path = db_path or default_db_path()
    db = IndexDB(db_path)
    db.open()
    try:
        indexer = Indexer(db)
        res = full_scan(indexer, roots)
        return res
    finally:
        db.close()


def run_daemon(
    roots: Iterable[Path],
    *,
    db_path: Path | None = None,
    reconcile_interval_s: int = 300,
    max_content_bytes: int = 1_000_000,
    exclude_dir_names: tuple[str, ...] | None = None,
    rpc_transport: str = "unixjson",
    rpc_socket_path: Optional[Path] = None,
) -> None:
    """Run the foreground daemon.

    This is a user-session daemon (unprivileged) that combines:
    - a scan-based indexer
    - an inotify tree watcher
    - periodic reconciliation for correctness
    - an RPC surface (TriTRPC in production; unixjson fallback for dev/tests)

    Design rule:
      watchers provide freshness; reconciliation provides correctness.
    """
    ensure_dirs()
    db_path = db_path or default_db_path()
    sock_path = rpc_socket_path or default_socket_path()

    db = IndexDB(db_path)
    db.open()

    rpc: Optional[RpcHandle] = None

    try:
        opts = IndexOptions(max_content_bytes=max_content_bytes)
        indexer = Indexer(db, opts=opts)

        scan_opts = ScanOptions(
            exclude_dir_names=exclude_dir_names or ScanOptions().exclude_dir_names
        )
        watcher_opts = WatchOptions(scan_options=scan_opts, reconcile_interval_s=reconcile_interval_s)

        # Initial scan for baseline correctness.
        full_scan(indexer, roots, opts=scan_opts)

        # Start RPC server (read-mostly).
        # NOTE: rpc_transport can be 'auto'; the runtime will resolve it.
        # We want health() to report the resolved transport, so we stash it.
        resolved_transport = {'value': rpc_transport}

        rpc = start_rpc_server(
            transport=rpc_transport,
            db_path=db_path,
            socket_path=sock_path,
            request_reindex=None,  # wired later once we have a journal/work queue
            get_health_details=lambda: {
                "rpc_transport": resolved_transport['value'],
                "requested_rpc_transport": rpc_transport,
                "rpc_socket": str(sock_path),
                "roots": [str(p) for p in roots],
            },
        )

        # Record the actual transport selected by runtime (important if requested was 'auto').
        resolved_transport['value'] = getattr(rpc, 'transport', rpc_transport)

        tw = TreeWatcher(indexer, roots, opts=watcher_opts)
        try:
            tw.run()
        finally:
            tw.close()
    finally:
        if rpc is not None:
            try:
                rpc.stop()
            except Exception:
                pass
        db.close()
