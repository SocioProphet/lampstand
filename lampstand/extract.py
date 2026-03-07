from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Extracted:
    content_text: str
    content_sha256: str
    content_len: int


def _looks_binary(sample: bytes) -> bool:
    # Heuristic: if there are NUL bytes, it's almost certainly binary.
    if b"\x00" in sample:
        return True
    # If a large fraction of bytes are outside common text ranges, treat as binary.
    if not sample:
        return False
    weird = 0
    for b in sample:
        if b in (9, 10, 13):  # tab/newline/carriage-return
            continue
        if 32 <= b <= 126:
            continue
        if b >= 128:
            # could be UTF-8; allow
            continue
        weird += 1
    return weird / len(sample) > 0.30


def extract_text_file(path: Path, *, max_bytes: int = 1_000_000) -> Optional[Extracted]:
    """Extract text from a file.

    MVP behavior:
    - only indexes files that appear to be text
    - reads up to max_bytes
    - decodes as UTF-8 with replacement
    """
    try:
        st = path.stat()
        if not path.is_file():
            return None
        # Skip huge files for MVP; we can add streaming/chunked indexing later.
        if st.st_size > max_bytes:
            # Still index the name/dir/ext; content is empty.
            return Extracted(content_text="", content_sha256="", content_len=0)
        with path.open("rb") as f:
            data = f.read(max_bytes)
        if _looks_binary(data[:8192]):
            return None
        # Decode best-effort.
        text = data.decode("utf-8", errors="replace")
        sha = hashlib.sha256(data).hexdigest()
        return Extracted(content_text=text, content_sha256=sha, content_len=len(data))
    except (OSError, PermissionError):
        return None


def file_ext(path: Path) -> str:
    suf = path.suffix.lower()
    if suf.startswith("."):
        suf = suf[1:]
    return suf
