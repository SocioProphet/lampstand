from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .daemon import run_daemon, run_one_shot_index
from .db import IndexDB
from .paths import default_db_path, default_socket_path, ensure_dirs
from .rpc.client import RpcClient
from .rpc import tritrpc as tritrpc_transport


def _parse_roots(values: list[str]) -> list[Path]:
    if not values:
        return [Path.home()]  # sensible default
    return [Path(v).expanduser() for v in values]


def _choose_rpc_transport(value: str) -> str:
    v = (value or "auto").lower().strip()
    if v == "auto":
        return "tritrpc" if tritrpc_transport.is_available() else "unixjson"
    return v


def _try_rpc_client(transport: str, socket_path: Path) -> Optional[RpcClient]:
    try:
        return RpcClient(transport=transport, socket_path=socket_path)
    except Exception:
        return None


def cmd_index(args: argparse.Namespace) -> int:
    roots = _parse_roots(args.root)
    res = run_one_shot_index(roots, db_path=Path(args.db) if args.db else None)
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    roots = _parse_roots(args.root)
    run_daemon(
        roots,
        db_path=Path(args.db) if args.db else None,
        reconcile_interval_s=args.reconcile_interval,
        max_content_bytes=args.max_content_bytes,
        rpc_transport=_choose_rpc_transport(args.rpc),
        rpc_socket_path=Path(args.socket) if args.socket else None,
    )
    return 0


def _direct_db_query(db_path: Path, query: str, *, limit: int, snippet: bool) -> int:
    ensure_dirs()
    db = IndexDB(db_path)
    db.open()
    try:
        results = db.query(query, limit=limit)
        for r in results:
            print(f"{r['path']}\t(score={r['score']:.3f})")
            if snippet and r.get("snippet"):
                print(f"  {r['snippet']}")
        return 0
    finally:
        db.close()


def cmd_query(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else default_db_path()
    transport = _choose_rpc_transport(args.rpc)
    sock = Path(args.socket) if args.socket else default_socket_path()

    if args.direct:
        return _direct_db_query(db_path, args.query, limit=args.limit, snippet=args.snippet)

    client = _try_rpc_client(transport, sock)
    if client is None:
        # Daemon not running (or transport missing); fallback to direct DB read.
        return _direct_db_query(db_path, args.query, limit=args.limit, snippet=args.snippet)

    out = client.search(args.query, limit=args.limit, snippet=args.snippet)
    for h in out.get("hits", []):
        print(f"{h['path']}\t(score={h['score']:.3f})")
        if args.snippet and h.get("snippet"):
            print(f"  {h['snippet']}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else default_db_path()
    transport = _choose_rpc_transport(args.rpc)
    sock = Path(args.socket) if args.socket else default_socket_path()

    if args.direct:
        ensure_dirs()
        db = IndexDB(db_path)
        db.open()
        try:
            print(json.dumps(db.stats(), indent=2, sort_keys=True))
            return 0
        finally:
            db.close()

    client = _try_rpc_client(transport, sock)
    if client is None:
        ensure_dirs()
        db = IndexDB(db_path)
        db.open()
        try:
            print(json.dumps(db.stats(), indent=2, sort_keys=True))
            return 0
        finally:
            db.close()

    print(json.dumps(client.stats(), indent=2, sort_keys=True))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    transport = _choose_rpc_transport(args.rpc)
    sock = Path(args.socket) if args.socket else default_socket_path()
    client = _try_rpc_client(transport, sock)
    if client is None:
        print(json.dumps({"ok": False, "error": "daemon_unreachable"}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(client.health(), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lampstand", description="Local file indexer/search prototype")
    p.add_argument("--db", help="Path to sqlite DB (default: ~/.local/share/lampstand/index.sqlite3)")
    p.add_argument(
        "--rpc",
        default="auto",
        help="RPC transport: auto|tritrpc|unixjson|none (none implies direct DB access)",
    )
    p.add_argument(
        "--socket",
        help="Unix socket path for unixjson transport (default: $XDG_RUNTIME_DIR/lampstand.sock)",
    )
    p.add_argument(
        "--direct",
        action="store_true",
        help="Bypass RPC and query the DB directly (debug / emergency mode)",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index", help="One-shot index of roots")
    p_index.add_argument("--root", action="append", default=[], help="Root path to index (repeatable)")
    p_index.set_defaults(fn=cmd_index)

    p_daemon = sub.add_parser("daemon", help="Run daemon (watch + reconcile + RPC)")
    p_daemon.add_argument("--root", action="append", default=[], help="Root path to watch/index (repeatable)")
    p_daemon.add_argument("--reconcile-interval", type=int, default=300, help="Seconds between reconcile scans")
    p_daemon.add_argument("--max-content-bytes", type=int, default=1_000_000, help="Max bytes to read for content")
    p_daemon.set_defaults(fn=cmd_daemon)

    p_query = sub.add_parser("query", help="Query the index (FTS5 syntax)")
    p_query.add_argument("query", help="FTS query string")
    p_query.add_argument("--limit", type=int, default=20)
    p_query.add_argument("--snippet", action="store_true", help="Show content snippet")
    p_query.set_defaults(fn=cmd_query)

    p_stats = sub.add_parser("stats", help="Index statistics")
    p_stats.set_defaults(fn=cmd_stats)

    p_health = sub.add_parser("health", help="Daemon health (RPC)")
    p_health.set_defaults(fn=cmd_health)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Special-case: "--rpc none" means "act direct"
    if getattr(args, "rpc", None) and str(args.rpc).lower().strip() == "none":
        args.direct = True
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
