from __future__ import annotations

import argparse
from pathlib import Path

from .daemon import run_daemon
from .paths import default_socket_path
from .rpc import tritrpc as tritrpc_transport


def _parse_roots(values: list[str]) -> list[Path]:
    if not values:
        return [Path.home()]
    return [Path(v).expanduser() for v in values]


def _choose_rpc_transport(value: str) -> str:
    v = (value or "auto").lower().strip()
    if v == "auto":
        return "tritrpc" if tritrpc_transport.is_available() else "unixjson"
    return v


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lampstandd", description="Lampstand daemon (watch + reconcile)")
    p.add_argument("--db", help="Path to sqlite DB (default: ~/.local/share/lampstand/index.sqlite3)")
    p.add_argument("--root", action="append", default=[], help="Root path to watch/index (repeatable)")
    p.add_argument("--reconcile-interval", type=int, default=300, help="Seconds between reconcile scans")
    p.add_argument("--max-content-bytes", type=int, default=1_000_000, help="Max bytes to read for content")

    p.add_argument(
        "--rpc",
        default="auto",
        help="RPC transport: auto|tritrpc|unixjson|none (none disables RPC)",
    )
    p.add_argument(
        "--socket",
        help=f"Unix socket path (unixjson transport). Default: {default_socket_path()}",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    roots = _parse_roots(args.root)
    run_daemon(
        roots,
        db_path=Path(args.db) if args.db else None,
        reconcile_interval_s=int(args.reconcile_interval),
        max_content_bytes=int(args.max_content_bytes),
        rpc_transport=_choose_rpc_transport(args.rpc),
        rpc_socket_path=Path(args.socket) if args.socket else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
