# Lampstand (prototype)

Lampstand is a **desktop file indexing + search** service for our GNOME-based Linux distribution.

Think: a pragmatic Linux-native cousin of *Spotlight* / *Windows Search* — but built to be:
- **correct** (periodic reconciliation, not “watcher superstition”)
- **inspectable** (health/stats are part of the contract)
- **platform-aligned** (SocioProphet TriTRPC + SocioProfit standard storage)

The name is deliberately biblical / millenarian: in Revelation, lampstands are literally devices that hold light.
We’re building the thing that “brings files to light.”

## Status

This repo is an MVP / spike. It already supports:
- one-shot indexing of roots (scan)
- incremental updates using **inotify**
- SQLite metadata store + SQLite **FTS5** text index
- a daemon with a **service boundary**:
  - **TriTRPC** in production builds (stubbed in this sandbox)
  - **unixjson** fallback (Unix socket + JSON lines) for dev/tests

## Quickstart (dev / sandbox)

```bash
# One-shot index
python -m lampstand.cli index --root "$HOME"

# Foreground daemon (watch + reconcile + unixjson RPC fallback)
python -m lampstand.cli daemon --root "$HOME" --rpc unixjson

# Query (tries RPC first; falls back to direct DB reads)
python -m lampstand.cli query 'report OR invoice' --limit 20 --snippet

# Health/stats (RPC if daemon running)
python -m lampstand.cli health --rpc unixjson
python -m lampstand.cli stats  --rpc unixjson
```

Default DB:
- `~/.local/share/lampstand/index.sqlite3` (unless overridden by SocioProfit storage)

Default unix socket (unixjson):
- `$XDG_RUNTIME_DIR/lampstand.sock`

## SocioProphet / SocioProfit platform integration

- **TriTRPC** (SocioProphet): see `lampstand/rpc/tritrpc.py` (adapter stub) and `docs/SOCIOPROFIT_PLATFORM.md`.
  - upstream: https://github.com/SocioProphet/TriTRPC
- **Standard storage** (SocioProfit): `lampstand/paths.py` supports:
  - `SOCIOPROFIT_DATA_HOME`
  - `SOCIOPROFIT_STATE_HOME`
  - `SOCIOPROFIT_RUNTIME_HOME`
  - and will also auto-detect a SocioProfit storage module if present.

## License

MIT (prototype code).
