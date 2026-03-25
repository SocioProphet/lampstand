from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .indexer import Indexer


@dataclass(frozen=True)
class ScanOptions:
    exclude_dir_names: tuple[str, ...] = (
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".cache",
        "__pycache__",
    )


def iter_files(roots: Iterable[Path], opts: ScanOptions) -> Iterable[Path]:
    for root in roots:
        root = root.expanduser().resolve()
        if not root.exists():
            continue
        if root.is_file():
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Prune excluded directories in-place.
            dirnames[:] = [d for d in dirnames if d not in opts.exclude_dir_names]
            for fn in filenames:
                yield Path(dirpath) / fn


def full_scan(indexer: Indexer, roots: Iterable[Path], *, opts: ScanOptions | None = None) -> dict:
    opts = opts or ScanOptions()
    scanned = 0
    indexed = 0
    skipped = 0
    for path in iter_files(roots, opts):
        scanned += 1
        res = indexer.index_file(path)
        if res is None:
            skipped += 1
        else:
            indexed += 1
    return {"scanned": scanned, "indexed": indexed, "skipped": skipped}

