# Distro integration guide (draft)

This document describes how we ship **Lampstand** as part of a GNOME-based Linux distribution.

The non-negotiables for “distro-grade” shipping:
- deterministic install locations
- systemd user service integration
- stable RPC surface for GNOME Shell + other clients
- debuggability (logs, stats, health endpoints)
- policy for removable media and privacy

## Packaging split

Ship multiple packages so the base system stays minimal and optional features remain optional:

1) **lampstand-core**
   - `lampstandd` daemon (user service)
   - `lampstand` CLI
   - SQLite schema + indexing engine
   - watcher + reconciler

2) **lampstand-rpc-tritrpc**
   - SocioProphet TriTRPC bindings / generated stubs
   - TriTRPC server/client wiring for LampstandService
   - upstream: https://github.com/SocioProphet/TriTRPC

3) **lampstand-gnome**
   - GNOME Shell SearchProvider2 adapter (DBus)
   - `.ini` and `.desktop` registration assets (`packaging/gnome/*`)
   - optional Nautilus integration later

4) **lampstand-extractors** (optional)
   - PDF/OCR/Office extractors, sandbox profiles

## systemd user service

The user daemon should be started via systemd user services.

Prototype unit:
- `packaging/systemd/user/lampstandd.service`

In platform builds, we standardize on TriTRPC, but we recommend using `--rpc auto` so the same unit works in dev and rescue environments:

```ini
ExecStart=/usr/bin/lampstandd --root %h --rpc auto
```

If we want to hard-pin transports in specialized images:

```ini
# TriTRPC explicitly
ExecStart=/usr/bin/lampstandd --root %h --rpc tritrpc

# unixjson explicitly (dev)
ExecStart=/usr/bin/lampstandd --root %h --rpc unixjson
```

## RPC surface

All clients (GNOME adapter, CLI, future GUI tools) should talk to `lampstandd` over RPC.

Production:
- **TriTRPC** (SocioProphet) — platform standard

Dev/test fallback:
- `unixjson` transport (Unix socket + JSON lines), implemented in `lampstand/rpc/unixjson.py`.

### Service interface

The transport-agnostic implementation lives here:
- `lampstand/rpc/service.py` (`LampstandService`)

Methods (current draft):
- `Search(SearchRequest) -> SearchResponse`
- `Stats() -> StatsResponse`
- `Health() -> HealthResponse`
- `Reindex(ReindexRequest) -> ReindexResponse` (stub until journal/work-queue exists)

## Storage / filesystem layout

We follow SocioProfit standard storage when available, otherwise XDG paths.

The storage resolution logic is in:
- `lampstand/paths.py`

Default (XDG):
- DB: `$XDG_DATA_HOME/lampstand/index.sqlite3`
- Socket: `$XDG_RUNTIME_DIR/lampstand.sock`

SocioProfit overrides (today):
- `SOCIOPROFIT_DATA_HOME`, `SOCIOPROFIT_STATE_HOME`, `SOCIOPROFIT_RUNTIME_HOME`

## GNOME integration (future package: lampstand-gnome)

GNOME Shell expects SearchProvider2 DBus services with registration assets.

We keep GNOME integration as a *thin adapter* so the search engine remains distro-owned and GNOME is just a client.
