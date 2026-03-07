# Lampstand: Desktop Search & Indexing Service — Design Spec (Draft)

> This document is a **working spec** for a best-of-breed, Linux-native desktop search/indexing capability for a GNOME-based distribution.
>
> We intentionally separate:
> 1) **Change detection** (what changed?)
> 2) **Extraction** (what does it mean?)
> 3) **Indexing & query** (how do we find it instantly?)
>
> This separation is the core reliability move: if one layer gets flaky, the others can continue and we can self-heal.

## 0. Problem statement

We want a first-class, low-latency desktop search experience comparable to macOS Spotlight and Windows Search, but built for Linux with:

- **Robustness**: no “index silently died” or “miners stuck forever” experiences.
- **Transparency**: inspectable state, clear policies, deterministic debugging.
- **Privacy by default**: avoid writing searchable shadows to removable media unless explicitly enabled.
- **Extensibility**: pluggable extractors and query operators.
- **Distribution control**: works even if GNOME ecosystem pieces are changed or replaced.

## 1. Goals

### G1 — Instant search
- Fast results for filenames, paths, metadata, and (optionally) full text.
- Query latency target: < 100 ms for typical desktop index sizes.

### G2 — Incremental updates
- Changes appear in search quickly (sub-second to a few seconds).
- Must remain correct after sleep/wake, crashes, and missed events.

### G3 — Policy control
- Per-volume policies: index off / local-only / portable-encrypted.
- Per-directory policies: include/exclude, priority tiers.

### G4 — Friendly integration surfaces
- CLI first.
- Clean local RPC API for GUI integration.
- Optional GNOME Shell SearchProvider2 adapter.

## 2. Non-goals (for now)

- Replacing `grep`.
- Indexing every network mount by default.
- Perfect semantic understanding of every file format on day 1.

## 3. Threat model / privacy principles

- Indexes are **data**. They can leak filenames, paths, tags, and even content tokens.
- Default should be **local-only** indexes stored in the user profile, not on removable media.
- Portable indexing is **opt-in** and must be encrypted.

## 4. Architecture overview

We implement a pipeline with explicit, crash-safe checkpoints:

1) **Event collector** produces a change feed (create/modify/delete/move)
2) **Reconciler** periodically scans to correct drift (“trust but verify”)
3) **Extractor** reads content/metadata safely
4) **Indexer** updates metadata + full-text stores transactionally
5) **Query service** answers searches and returns ranked results

### 4.1 Components

#### A) Change feed
We support multiple collectors:

- **Collector A1 (unprivileged): inotify-based**
  - Good for user session.
  - Limitations: directory watch scaling, watch limits.

- **Collector A2 (privileged): fanotify mount marks**
  - System service or capability-enabled service.
  - Mount-level observation avoids per-directory watches.
  - Emits events into an append-only journal.

- **Collector A3 (fallback): periodic reconciliation scan**
  - Correctness safety net.
  - Also handles “events dropped” and “watch overflow”.

#### B) Journal (recommended)
Even if we use inotify/fanotify, we write normalized events to a local journal:

- Append-only, sequence-numbered events (monotonic `seq`)
- Durable checkpoint for the consumer (`last_applied_seq`)
- Allows:
  - crash recovery
  - backpressure
  - consistent replays

#### C) Index stores
We separate:

- **Metadata store** (paths, stat data, file IDs, tags): SQLite or similar
- **Inverted index** (text search): pluggable
  - MVP: SQLite FTS5
  - Future: Tantivy/Xapian/Lucene-like engine

#### D) API surfaces
- CLI (always; also used for debugging and CI)
- **TriTRPC** (SocioProfit platform standard) for all first-class clients
- Dev/test fallback: local RPC over Unix socket (unixjson)
- Optional DBus adapter for GNOME Shell (`org.gnome.Shell.SearchProvider2`) that forwards to RPC


#### E) Storage
- Prefer SocioProfit standard storage for all persistent state when available
- Fall back to XDG Base Directory spec paths in generic Linux environments

## 5. Data model

### 5.1 File identity
We should not rely on “path == identity” because renames happen.

Preferred ID:

- `(dev, inode, ctime_ns)`  (ctime changes on metadata updates; helps mitigate inode reuse)

We maintain:

- `file_id` (stable-ish)
- `path` (current location)
- `seen_paths` (optional for rename history)

### 5.2 Metadata schema (baseline)
- path, directory, name, extension
- size, mtime, ctime, mode
- inode, dev
- content hash (optional; for “index is stale” detection)
- extractor version (for re-extraction when parser changes)

### 5.3 Index schema (baseline)
Text fields we want searchable:

- `name`
- `dir` tokens
- `ext`
- `content` (optional, policy-dependent)

## 6. Query model

### 6.1 Query syntax
We should support:

- Basic terms: `invoice 2024`
- Boolean: `invoice OR receipt`
- Phrase: `"quarterly report"`
- Fielded search:
  - `name:budget`
  - `ext:pdf`
  - `dir:taxes`

### 6.2 Ranking
- Filename hits get a boost.
- Recent files get a mild boost.
- Exact phrase gets a boost.

## 7. Policy design

### 7.1 Volume policies
- `off`: no indexing, no journal
- `local`: index stored in user profile; no writes to volume
- `portable-encrypted`: write index capsule to volume encrypted

### 7.2 Directory policies
- allow/deny patterns
- priority tiers (home docs > downloads > cache)

## 8. Reliability rules

- Any event-driven watcher must be paired with reconciliation scanning.
- Database updates are transactional.
- Extractors must be time-limited and killable.
- The system must expose health:
  - last event seq processed
  - last scan time
  - backlog length
  - extractor failures


## 10. Production-critical details we must specify (not fully covered above)

These items are where “desktop search” projects usually get brittle. We should nail them down early.

### 10.1 Privilege model (fanotify, file descriptors, and safety)
- **Default stance:** keep the *query* and *UI integration* in the user session, but treat *mount-level event capture* as a distinct component that may require elevated privileges depending on kernel/support.
- If we use `fanotify` with mount/filesystem marks, we must treat the daemon as **security-sensitive**:
  - fanotify can deliver file descriptors for accessed objects; when running with elevated capabilities this can become a cross-user data exposure hazard if not carefully constrained.
  - Any privileged collector must enforce “only emit events the target user should know about” or run per-user with restricted capabilities.

### 10.2 Mount lifecycle and removable media
- We need a first-class concept of **volumes** (stable IDs) and their lifecycle:
  - mount/unmount
  - bind mounts and overlay mounts
  - “same path, different filesystem” scenarios
- Policy must be evaluated at the **volume** boundary (off / local-only / portable-encrypted).

### 10.3 Watcher realities (event loss and non-recursive monitoring)
- Any watch-based approach can drop events (queue overflow) and directory watching is not recursive, so we *must* pair it with reconciliation scans and drift repair.

### 10.4 File identity, hardlinks, and inode reuse
- Path is not identity.
- We should decide explicitly how to handle:
  - hardlinks (multiple paths to same inode)
  - inode reuse (especially on busy temp dirs)
  - cross-device moves (rename becomes copy+delete)

### 10.5 Index lifecycle management
- When the index grows too large, or schemas/extractors change:
  - reindex strategies (full vs incremental)
  - vacuum/compaction policy
  - corruption detection and self-heal (wipe & rebuild with clear UX)


## 9. Implementation plan (phased)

### Phase 0 (today): MVP
- Metadata + FTS5 index
- Scanner + inotify watcher
- CLI: index/query/stats

### Phase 1: GNOME integration
- Thin DBus adapter implementing SearchProvider2
- GNOME results mapping to file opener actions

### Phase 2: Journaling collector
- fanotify mount-level collector (systemd service)
- append-only journal

### Phase 3: Extractor plugins + sandbox
- separate process per extractor
- resource limits

### Phase 4: Portable encrypted index capsules
- encrypted container on removable media
- explicit opt-in

