from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .db import IndexDB
from .extract import extract_text_file, file_ext


@dataclass(frozen=True)
class IndexOptions:
    max_content_bytes: int = 1_000_000
    index_binary_names: bool = True  # if False, skip files with no extracted text


class Indexer:
    def __init__(self, db: IndexDB, opts: IndexOptions | None = None):
        self.db = db
        self.opts = opts or IndexOptions()

    def index_file(self, path: Path) -> Optional[int]:
        """Index a single file path; returns file_id or None if skipped."""
        try:
            if not path.exists():
                return None
            if not path.is_file():
                return None

            st = path.stat()
            mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
            ctime_ns = int(getattr(st, "st_ctime_ns", int(st.st_ctime * 1e9)))
            size = int(st.st_size)

            # Fast skip if metadata indicates no change.
            if not self.db.file_needs_reindex(str(path), mtime_ns=mtime_ns, size=size):
                return None

            ext = file_ext(path)
            name = path.name
            dir_ = str(path.parent)
            mode = int(st.st_mode)
            inode = int(st.st_ino)
            dev = int(st.st_dev)
            indexed_at_ns = time.time_ns()

            extracted = extract_text_file(path, max_bytes=self.opts.max_content_bytes)
            if extracted is None:
                if not self.opts.index_binary_names:
                    return None
                content_text = ""
                content_sha256 = ""
                content_len = 0
            else:
                content_text = extracted.content_text
                content_sha256 = extracted.content_sha256
                content_len = extracted.content_len

            file_id = self.db.upsert_file(
                path=str(path),
                dir=dir_,
                name=name,
                ext=ext,
                size=size,
                mtime_ns=mtime_ns,
                ctime_ns=ctime_ns,
                inode=inode,
                dev=dev,
                mode=mode,
                indexed_at_ns=indexed_at_ns,
                content_len=content_len,
                content_sha256=content_sha256,
                content_text=content_text,
            )
            return file_id
        except (OSError, PermissionError):
            return None

    def delete_path(self, path: Path) -> bool:
        return self.db.delete_path(str(path))
