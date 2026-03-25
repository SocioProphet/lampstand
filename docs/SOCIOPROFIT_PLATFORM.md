# SocioProfit / SocioProphet platform integration notes (draft)

This document captures the *hooks* Lampstand uses to integrate into the SocioProfit platform.

We have two platform constraints:
1) RPC must align with the platform standard (**TriTRPC**, from SocioProphet).
2) Persistent storage paths should align with SocioProfit standard storage.

In this sandbox environment we cannot vendor external repos, so both integrations are implemented via thin adapters + duck-typing.

## TriTRPC (SocioProphet)

Upstream repo (user-provided):
- https://github.com/SocioProphet/TriTRPC

Integration points in Lampstand:
- Transport-agnostic service implementation: `lampstand/rpc/service.py`
- TriTRPC adapter shim: `lampstand/rpc/tritrpc.py`

Expected work when TriTRPC is vendored locally:
1) Decide the canonical integration style:
   - **Python runtime** (importable module), or
   - **Sidecar binary** (Rust/Go) spawned by `lampstandd`.
2) Implement `serve_tritrpc(service, config_path)` and `TriTRPCClient.call()`.
3) Wire a stable service identity and endpoint configuration (socket vs tcp, auth, interceptors).
4) Add a dedicated distro package:
   - `lampstand-rpc-tritrpc` (pulls TriTRPC + generated stubs/config)

### Transport contract we expose

Regardless of transport, callers use these methods (see `lampstand/rpc/messages.py`):
- `Search(query, limit, snippet) -> hits[]`
- `Stats() -> db + watcher + reconcile stats`
- `Health() -> ok + details`
- `Reindex(paths[])` (placeholder until we have a journal/work queue)

This is intentionally small so GNOME adapters and CLIs stay stable while we evolve internals.

## Standard storage (SocioProfit)

We route all persistent paths through `lampstand/paths.py`.

Priority order today:
1) Environment overrides:
   - `SOCIOPROFIT_DATA_HOME`
   - `SOCIOPROFIT_STATE_HOME`
   - `SOCIOPROFIT_RUNTIME_HOME`
2) If a SocioProfit storage module is importable and exposes:
   - `data_dir(app_id)`
   - `state_dir(app_id)`
   - optional: `runtime_dir(app_id)`
   then we use that.
3) Fallback to XDG Base Directory paths.

Rationale: this lets us build/test without platform dependencies, but ship tightly integrated builds.

## Naming / identity

Product name: **Lampstand**
- thematic rationale: Revelation’s lampstands “hold light”; we “bring files to light”
- functional rationale: it’s the biblical version of “Spotlight” without being a pun
