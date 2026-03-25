# Dependencies

This repo targets a **minimal** dependency set for the core indexer and keeps
“integration-heavy” dependencies in separate packages.

## Runtime (core)

- Python 3.10+ (3.11 recommended)
- Linux kernel with inotify (standard)
- SQLite3 with FTS5 enabled (verify in CI)

## Runtime (platform build)

### TriTRPC (SocioProphet)

- Required for the production RPC surface.
- Upstream repo: https://github.com/SocioProphet/TriTRPC
- In this sandbox snapshot, TriTRPC is stubbed (`lampstand/rpc/tritrpc.py`) because we cannot vendor external repos here.

Expected deliverable (distro policy):
- a Python runtime module (`import tritrpc`), **or**
- a sidecar binary (`tritrpcd`) + config.

### Standard storage (SocioProfit)

Recommended for consistent filesystem layout across the platform.

The code will auto-detect it if available; otherwise it falls back to XDG paths.

Environment hooks supported today:
- `SOCIOPROFIT_DATA_HOME`
- `SOCIOPROFIT_STATE_HOME`
- `SOCIOPROFIT_RUNTIME_HOME`

## Build-time

- None beyond a standard Python toolchain.

## Optional (future)

### GNOME adapter

One of:

- Python + PyGObject (`python3-gi`) + GLib/GIO
- Rust + zbus

### Extractors

These are intentionally optional and out-of-process:

- PDF text: `poppler-utils` (`pdftotext`)
- OCR: `tesseract-ocr`
- Office formats: converters (TBD, distro policy)
