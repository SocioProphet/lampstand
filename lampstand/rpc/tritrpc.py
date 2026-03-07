from __future__ import annotations

"""TriTRPC transport adapter (SocioProphet).

This module is the *intended* production RPC transport for Lampstand.

Repo (user-provided): https://github.com/SocioProphet/TriTRPC

In this sandbox we can't vendor or import TriTRPC, so this file is a thin shim
with a strict contract:
  - expose LampstandService methods over TriTRPC
  - provide a client with a simple `.call(method, payload)` interface

Why the shim matters:
  - LampstandService stays transport-agnostic
  - we can ship unixjson as a dev/test fallback
  - the distro build can bind TriTRPC without rewriting the core

NOTE: We intentionally avoid guessing TriTRPC's Python API surface here.
Once TriTRPC is vendored/available in the build environment, implement
`serve_tritrpc()` and `TriTRPCClient` using the real APIs.
"""

import importlib.util
import shutil
from pathlib import Path
from typing import Any, Optional

from .service import LampstandService


def is_available() -> bool:
    """Best-effort availability check.

    We consider TriTRPC available if:
      - a Python module named `tritrpc` (or `tritrpc_py`) can be imported, OR
      - a helper binary `tritrpc`/`tritrpcd` exists on PATH.

    This covers both "library" and "sidecar" integration styles.
    """
    try:
        if importlib.util.find_spec("tritrpc") is not None:
            return True
        if importlib.util.find_spec("tritrpc_py") is not None:
            return True
    except Exception:
        pass

    return bool(shutil.which("tritrpc") or shutil.which("tritrpcd"))


def serve_tritrpc(*, service: LampstandService, config_path: Optional[Path] = None) -> None:
    """Start a TriTRPC server exposing LampstandService.

    Expected to block forever (or until interrupted).

    Implementation options (distro policy):
      1) Pure-Python binding, if TriTRPC ships Python runtime.
      2) Sidecar binary (Rust/Go) that we spawn here, forwarding to `service`.

    `config_path` is intentionally transport-owned (TriTRPC decides semantics).
    """
    raise NotImplementedError(
        "TriTRPC transport not wired in this sandbox. "
        "Vendor SocioProphet/TriTRPC in the build environment and implement serve_tritrpc()."
    )


class TriTRPCClient:
    """TriTRPC client stub.

    We standardize our callers on a small surface:
      - call(method: str, payload: dict) -> dict

    That keeps CLI, GNOME adapter, etc. decoupled from the transport.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "TriTRPC transport not wired in this sandbox. "
            "Vendor SocioProphet/TriTRPC and implement TriTRPCClient."
        )

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
