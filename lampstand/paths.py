from __future__ import annotations

import importlib
import os
from pathlib import Path


APP_ID = "lampstand"


def _home_dir() -> Path:
    return Path.home()


def _xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", _home_dir() / ".local" / "share"))


def _xdg_state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", _home_dir() / ".local" / "state"))


def _xdg_runtime_dir() -> Path:
    # XDG_RUNTIME_DIR is preferred; fallback mirrors common systemd user-runtime layout.
    xrd = os.environ.get("XDG_RUNTIME_DIR")
    if xrd:
        return Path(xrd)
    return Path("/run/user") / str(os.getuid())


def _try_socioprofit_storage_module():
    """Best-effort integration with SocioProfit standard storage.

    We don't have the SocioProfit standard storage package available in this
    sandbox, so we use a duck-typed approach:

    If a module exists and exposes data_dir(app_id), state_dir(app_id),
    runtime_dir(app_id), we use it.
    """
    candidates = (
        "socioprofit.storage",
        "socioprofit.standard_storage",
        "socioprofit_storage",
        "socioprofit_standard_storage",
    )
    for name in candidates:
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        if hasattr(mod, "data_dir") and hasattr(mod, "state_dir"):
            return mod
    return None


_SP_STORAGE = _try_socioprofit_storage_module()


def data_dir() -> Path:
    # Highest priority: explicit SocioProfit env vars.
    sp = os.environ.get("SOCIOPROFIT_DATA_HOME")
    if sp:
        return Path(sp) / APP_ID

    # Next: SocioProfit standard storage module (if present).
    if _SP_STORAGE is not None and hasattr(_SP_STORAGE, "data_dir"):
        try:
            return Path(_SP_STORAGE.data_dir(APP_ID))  # type: ignore[attr-defined]
        except Exception:
            pass

    # Fallback: XDG.
    return _xdg_data_home() / APP_ID


def state_dir() -> Path:
    sp = os.environ.get("SOCIOPROFIT_STATE_HOME")
    if sp:
        return Path(sp) / APP_ID

    if _SP_STORAGE is not None and hasattr(_SP_STORAGE, "state_dir"):
        try:
            return Path(_SP_STORAGE.state_dir(APP_ID))  # type: ignore[attr-defined]
        except Exception:
            pass

    return _xdg_state_home() / APP_ID


def runtime_dir() -> Path:
    sp = os.environ.get("SOCIOPROFIT_RUNTIME_HOME")
    if sp:
        return Path(sp)

    if _SP_STORAGE is not None and hasattr(_SP_STORAGE, "runtime_dir"):
        try:
            return Path(_SP_STORAGE.runtime_dir(APP_ID))  # type: ignore[attr-defined]
        except Exception:
            pass

    return _xdg_runtime_dir()


def default_db_path() -> Path:
    return data_dir() / "index.sqlite3"


def default_socket_path() -> Path:
    return runtime_dir() / f"{APP_ID}.sock"


def ensure_dirs() -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)
    runtime_dir().mkdir(parents=True, exist_ok=True)
