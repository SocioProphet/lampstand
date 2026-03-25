# Lampstand Roadmap (Backlog)

This roadmap is written for a GNOME-based Linux distribution that wants a **reliable, inspectable desktop indexer**.

Milestones are designed to be shippable. Each milestone ends in something we can package, enable, and support.

## M0 — Repo hygiene and deterministic builds (DONE / ongoing)

- Packaging skeleton (pyproject + systemd units + GNOME provider registration placeholders)
- Basic CI script (lint/test hooks)
- Runtime guardrails (FTS5 availability checks, sane error messages)

## M1 — Stable RPC surface (platform standard: SocioProphet TriTRPC — https://github.com/SocioProphet/TriTRPC)

Goal: all consumers (CLI, GNOME adapter, future GUI tools) talk to the daemon via RPC.

- Define the RPC contract (request/response types) in a transport-agnostic way
- Implement LampstandService (transport-agnostic)
- Implement TriTRPC binding (production)
- Keep a unix-socket JSON fallback transport for dev/tests only
- Add `lampstand health` and `lampstand stats` over RPC
- Add basic “introspection” fields:
  - roots indexed
  - last reconcile time (placeholder initially)
  - watcher overflow counters (later)

## M2 — Change journal + checkpointing (correctness backbone)

Goal: survive lost events, restarts, crashes, power loss.

- Append-only event log (sequence IDs)
- Checkpoints per consumer
- Reconciliation emits repair events
- Reindex triggers on schema/extractor upgrades

## M3 — GNOME integration (SearchProvider2 adapter)

- DBus adapter that forwards to Lampstand RPC
- packaging assets installed in correct locations
- show top-N results fast; “show all results” path

## M4 — Extractor framework (out-of-process + sandboxed)

- Plugin registry + versioned extractors
- Time/memory caps
- PDF text, EXIF, basic code tokenization
- optional OCR as a separate package

## M5 — Ranking that feels modern

- Fuzzy filename match
- Frecency (frequency + recency)
- Directory boosting (Documents > Downloads > cache)
- Query parsing that hides raw FTS syntax from GUI callers

## M6 — Privileged collector (fanotify) (optional)

- System daemon collector for mount-level event capture
- Strong sandboxing + authorization checks
- Emits normalized events into journal

## M7 — Removable media policies + portable indexes

- Per-volume policy: off / local-only / portable-encrypted
- Explicit UX for indexing removable drives
- Encrypted portable index capsules (opt-in)
