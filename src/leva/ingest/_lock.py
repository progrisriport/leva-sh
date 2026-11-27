"""Hold the exclusive lock that keeps two builds from writing the index at once."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from leva.model import IngestError

LOCK_NAME: Final = "index.lock"
BUSY: Final = "another leva is building the index"
_BUSY_HINT: Final = "wait for it to finish, then try again"
_LOCK_MODE: Final = 0o644


@contextmanager
def index_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive, non-blocking ``flock`` on `path` for the duration of the block.

    The file is created (mode 0o644) when missing and never deleted. The lock is released
    when the block ends, however it ends.

    Raises:
        IngestError: `BUSY` (hint "wait for it to finish, then try again") when another open
            file description holds the lock; ``cannot lock index: <path>`` for any other
            `OSError` (chained).
    """
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, _LOCK_MODE)
    except OSError as exc:
        raise IngestError(f"cannot lock index: {path}") from exc
    try:
        _acquire(fd, path)
        yield
    finally:
        os.close(fd)


def _acquire(fd: int, path: Path) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise IngestError(BUSY, hint=_BUSY_HINT) from exc
    except OSError as exc:
        raise IngestError(f"cannot lock index: {path}") from exc
