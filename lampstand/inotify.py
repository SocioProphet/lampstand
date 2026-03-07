from __future__ import annotations

import ctypes
import errno
import os
import struct
from dataclasses import dataclass
from typing import Iterator, Optional

# inotify constants (subset)
IN_ACCESS = 0x00000001
IN_MODIFY = 0x00000002
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_CLOSE_NOWRITE = 0x00000010
IN_OPEN = 0x00000020
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800

IN_UNMOUNT = 0x00002000
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000

IN_ONLYDIR = 0x01000000
IN_DONT_FOLLOW = 0x02000000
IN_EXCL_UNLINK = 0x04000000
IN_MASK_ADD = 0x20000000
IN_ISDIR = 0x40000000
IN_ONESHOT = 0x80000000

IN_ALL_EVENTS = (
    IN_ACCESS
    | IN_MODIFY
    | IN_ATTRIB
    | IN_CLOSE_WRITE
    | IN_CLOSE_NOWRITE
    | IN_OPEN
    | IN_MOVED_FROM
    | IN_MOVED_TO
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MOVE_SELF
)

libc = ctypes.CDLL("libc.so.6", use_errno=True)


@dataclass(frozen=True)
class InotifyEvent:
    wd: int
    mask: int
    cookie: int
    name: str


class Inotify:
    def __init__(self) -> None:
        # inotify_init1 is preferred (nonblocking, close-on-exec)
        flags = os.O_NONBLOCK | os.O_CLOEXEC
        fd = libc.inotify_init1(flags)
        if fd < 0:
            e = ctypes.get_errno()
            raise OSError(e, os.strerror(e))
        self.fd = int(fd)

        # Buffer to handle partial reads (inotify_event is variable-length).
        self._buf = bytearray()

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def add_watch(self, path: str, mask: int) -> int:
        wd = libc.inotify_add_watch(self.fd, ctypes.c_char_p(path.encode("utf-8")), ctypes.c_uint32(mask))
        if wd < 0:
            e = ctypes.get_errno()
            raise OSError(e, f"inotify_add_watch failed for {path}: {os.strerror(e)}")
        return int(wd)

    def rm_watch(self, wd: int) -> None:
        res = libc.inotify_rm_watch(self.fd, ctypes.c_int(wd))
        if res < 0:
            e = ctypes.get_errno()
            raise OSError(e, os.strerror(e))

    def read_events(self) -> Iterator[InotifyEvent]:
        """Yield all available events (nonblocking).

        This method:
        - drains the inotify fd until EAGAIN
        - buffers partial reads so we never drop a truncated inotify_event
        """
        # struct inotify_event { int wd; uint32_t mask; uint32_t cookie; uint32_t len; char name[len]; }
        header_fmt = "iIII"
        header_size = struct.calcsize(header_fmt)

        # Drain fd into buffer.
        while True:
            try:
                chunk = os.read(self.fd, 16384)
                if not chunk:
                    break
                self._buf.extend(chunk)
            except BlockingIOError:
                break
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
                raise

        # Parse as many complete events as are available in the buffer.
        i = 0
        n = len(self._buf)
        while i + header_size <= n:
            wd, mask, cookie, name_len = struct.unpack_from(header_fmt, self._buf, i)
            if i + header_size + name_len > n:
                break  # wait for more bytes next call
            i += header_size
            name_bytes = bytes(self._buf[i : i + name_len])
            i += name_len
            name = name_bytes.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
            yield InotifyEvent(int(wd), int(mask), int(cookie), name)

        # Drop parsed bytes, keep any remainder for next call.
        if i:
            del self._buf[:i]
