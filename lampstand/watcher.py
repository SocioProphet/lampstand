from __future__ import annotations

import os
import selectors
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .inotify import (
    IN_ALL_EVENTS,
    IN_CREATE,
    IN_DELETE,
    IN_DELETE_SELF,
    IN_ISDIR,
    IN_MOVED_FROM,
    IN_MOVED_TO,
    IN_Q_OVERFLOW,
    IN_IGNORED,
    IN_UNMOUNT,
    IN_CLOSE_WRITE,
    Inotify,
)
from .scan import ScanOptions
from .indexer import Indexer


@dataclass(frozen=True)
class WatchOptions:
    scan_options: ScanOptions = ScanOptions()
    reconcile_interval_s: int = 300


MOVE_TTL_S = 30.0  # seconds; unmatched IN_MOVED_FROM treated as delete after this


class TreeWatcher:
    def __init__(self, indexer: Indexer, roots: Iterable[Path], opts: WatchOptions | None = None):
        self.indexer = indexer
        self.roots = [r.expanduser().resolve() for r in roots]
        self.opts = opts or WatchOptions()
        self.inotify = Inotify()
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.inotify.fd, selectors.EVENT_READ)
        self.wd_to_dir: dict[int, Path] = {}
        self.pending_moves: dict[int, tuple[Path, float]] = {}
        self._needs_reconcile = False

    def close(self) -> None:
        try:
            self.sel.unregister(self.inotify.fd)
        except Exception:
            pass
        self.inotify.close()

    def _should_exclude_dir(self, p: Path) -> bool:
        return p.name in self.opts.scan_options.exclude_dir_names

    def _add_watch_dir(self, d: Path) -> None:
        if self._should_exclude_dir(d):
            return
        try:
            wd = self.inotify.add_watch(str(d), IN_ALL_EVENTS)
            self.wd_to_dir[wd] = d
        except OSError:
            # Likely permissions or watch limit; request reconcile fallback.
            self._needs_reconcile = True

    def _build_initial_watches(self) -> None:
        for root in self.roots:
            if not root.exists():
                continue
            if root.is_file():
                # File roots: just index once.
                self.indexer.index_file(root)
                continue
            for dirpath, dirnames, _filenames in os.walk(root, followlinks=False):
                d = Path(dirpath)
                # Prune excluded dirs in-place.
                dirnames[:] = [x for x in dirnames if x not in self.opts.scan_options.exclude_dir_names]
                self._add_watch_dir(d)

    def run(self) -> None:
        """Run the watcher loop forever."""
        self._build_initial_watches()

        last_reconcile = time.time()
        while True:
            # Periodic reconcile.
            now = time.time()
            if self._needs_reconcile or (now - last_reconcile) >= self.opts.reconcile_interval_s:
                self._needs_reconcile = False
                self._reconcile_deleted()
                # A cheap full scan that only reindexes changed files.
                from .scan import full_scan

                full_scan(self.indexer, self.roots, opts=self.opts.scan_options)
                last_reconcile = now

            # Purge stale rename cookies that never got a matching MOVED_TO.
            stale_cookies = [c for c, (_p, ts) in self.pending_moves.items() if (now - ts) > MOVE_TTL_S]
            for c in stale_cookies:
                old_p, _ts = self.pending_moves.pop(c, (None, None))
                if old_p is not None:
                    # Conservative: treat as delete; reconcile will fix if needed.
                    self.indexer.delete_path(old_p)

            events = self.sel.select(timeout=1.0)
            if not events:
                continue

            for _key, _mask in events:
                for ev in self.inotify.read_events():
                    if ev.mask & IN_Q_OVERFLOW:
                        self._needs_reconcile = True
                        continue

                    # Watch got removed (directory deleted/unmounted); drop mapping to avoid wd reuse confusion.
                    if ev.mask & (IN_IGNORED | IN_UNMOUNT):
                        if ev.wd in self.wd_to_dir:
                            self.wd_to_dir.pop(ev.wd, None)
                        self._needs_reconcile = True
                        continue

                    base = self.wd_to_dir.get(ev.wd)
                    if base is None:
                        continue

                    # If ev.name is empty, the event refers to the watched dir itself.
                    p = base if not ev.name else base / ev.name

                    is_dir = bool(ev.mask & IN_ISDIR)

                    # Handle renames (pair moved_from/moved_to by cookie).
                    if ev.mask & IN_MOVED_FROM:
                        if ev.cookie:
                            # store old path with timestamp; pairing with MOVED_TO is racy
                            self.pending_moves[ev.cookie] = (p, time.time())
                        else:
                            # treat as delete
                            self.indexer.delete_path(p)
                        continue

                    if ev.mask & IN_MOVED_TO:
                        old_rec = self.pending_moves.pop(ev.cookie, None) if ev.cookie else None
                        old = old_rec[0] if old_rec else None
                        if old is not None:
                            self.indexer.delete_path(old)
                        if is_dir:
                            # New directory: add watch and reconcile.
                            self._add_watch_dir(p)
                            self._needs_reconcile = True
                        else:
                            self.indexer.index_file(p)
                        continue

                    if ev.mask & IN_CREATE:
                        if is_dir:
                            self._add_watch_dir(p)
                            # Directory creates can hide many children; reconcile soon.
                            self._needs_reconcile = True
                        else:
                            self.indexer.index_file(p)
                        continue

                    if ev.mask & (IN_DELETE | IN_DELETE_SELF):
                        if is_dir:
                            self._needs_reconcile = True
                        else:
                            self.indexer.delete_path(p)
                        continue

                    # Prefer indexing on close_write for fewer partial writes.
                    if ev.mask & IN_CLOSE_WRITE:
                        if not is_dir:
                            self.indexer.index_file(p)
                        continue

    def _reconcile_deleted(self) -> None:
        """Remove entries that no longer exist on disk."""
        db = self.indexer.db
        removed = 0
        for path_str in list(db.iter_all_paths()):
            try:
                if not Path(path_str).exists():
                    if db.delete_path(path_str):
                        removed += 1
            except Exception:
                # If something is funky (permissions, transient), ignore.
                continue
        # We don't log yet; daemon can optionally print stats.
