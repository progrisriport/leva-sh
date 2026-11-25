"""Open an existing index for reading only, checking its schema version."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Final

from leva.model import IndexUnavailableError
from leva.store._schema import SCHEMA_VERSION

_REBUILD_HINT: Final = "run leva --rebuild"


def _unavailable(message: str) -> IndexUnavailableError:
    return IndexUnavailableError(message, hint=_REBUILD_HINT)


def _read_user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def open_readonly(path: Path) -> sqlite3.Connection:
    """Open the index at `path` read-only.

    Args:
        path: Location of the index file; a relative path is resolved against the
            current directory.

    Returns:
        An open connection that rejects writes. The caller owns it and closes it.

    Raises:
        IndexUnavailableError: If the file is missing, is not a readable SQLite database (also
            when a parent directory cannot be searched) or has a ``user_version`` other than
            ``SCHEMA_VERSION``; the hint is ``run leva --rebuild``.
    """
    try:
        is_file = path.is_file()
    except OSError as exc:
        raise _unavailable(f"index unreadable: {path}") from exc
    if not is_file:
        raise _unavailable(f"index missing: {path}")
    try:
        conn = sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise _unavailable(f"index unreadable: {path}") from exc
    try:
        found = _read_user_version(conn)
    except sqlite3.Error as exc:
        conn.close()
        raise _unavailable(f"index unreadable: {path}") from exc
    if found != SCHEMA_VERSION:
        conn.close()
        raise _unavailable(f"index schema {found} is not {SCHEMA_VERSION}: {path}")
    return conn
