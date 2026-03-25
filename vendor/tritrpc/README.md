# TriTRPC (SocioProphet) vendoring note

Upstream:
- https://github.com/SocioProphet/TriTRPC

Lampstand uses TriTRPC as its **production RPC transport**.

Because this sandbox environment cannot vendor external repositories, the actual
TriTRPC binding is stubbed in:
- `lampstand/rpc/tritrpc.py`

## Expected integration styles

Lampstand intentionally supports two integration styles so our distro can pick
what fits its toolchain:

### 1) Python runtime

If TriTRPC ships a Python runtime we can import, implement:
- `serve_tritrpc(service, config_path)`
- `TriTRPCClient.call(method, payload)`

and make `import tritrpc` (or `import tritrpc_py`) succeed.

### 2) Sidecar binary

If TriTRPC is primarily Rust/Go, we can ship a small daemon (e.g. `tritrpcd`)
and let `lampstandd` spawn it or connect to it.

In this style, `lampstandd` still exposes the same service contract, but the
wire protocol lives in the sidecar.

## Suggested vendoring approach

Platform builds can vendor TriTRPC as a git submodule:

```bash
git submodule add https://github.com/SocioProphet/TriTRPC vendor/tritrpc/src
```

or pin it as a package dependency in the distro.

