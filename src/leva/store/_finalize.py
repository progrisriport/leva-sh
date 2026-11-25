"""Finish a new index: fill the FTS table, write meta, compute the digest, check integrity."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from leva.model import IngestError
from leva.store._schema import SCHEMA_VERSION

_INSERT_FTS: Final = (
    "INSERT INTO search_fts (rowid, name, intents, summary, body) VALUES (?, ?, ?, ?, ?)"
)
_OPTIMIZE_FTS: Final = "INSERT INTO search_fts (search_fts) VALUES ('optimize')"
_REPLACE_META: Final = "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)"

_SELECT_ENTRIES: Final = "SELECT id, name, summary FROM entry ORDER BY id"
_SELECT_ALIASES: Final = "SELECT entry_id, alias FROM alias ORDER BY entry_id, alias"
_SELECT_INTENTS: Final = "SELECT entry_id, text FROM intent ORDER BY entry_id, ord"
_SELECT_BODIES: Final = "SELECT entry_id, body FROM doc_section ORDER BY entry_id, ord"

# Fixed order and explicit columns: the digest recipe of D-048.
_DIGEST_QUERIES: Final[tuple[tuple[str, str], ...]] = (
    (
        "meta",
        "SELECT key, value FROM meta WHERE key NOT IN ('built_at', 'index_digest') ORDER BY key",
    ),
    (
        "entry",
        "SELECT id, name, section, kind, origin, summary, path, has_man, curated, explain, rank"
        " FROM entry ORDER BY id",
    ),
    ("alias", "SELECT entry_id, alias FROM alias ORDER BY entry_id, alias"),
    (
        "doc_section",
        "SELECT entry_id, ord, heading, body FROM doc_section ORDER BY entry_id, ord",
    ),
    (
        "example",
        "SELECT entry_id, ord, id, description, cmd, source, verified, danger"
        " FROM example ORDER BY entry_id, ord",
    ),
    ("note", "SELECT entry_id, ord, kind, text FROM note ORDER BY entry_id, ord"),
    (
        "subcommand",
        "SELECT entry_id, ord, name, summary, entry_name, source, body"
        " FROM subcommand ORDER BY entry_id, ord",
    ),
    ("related", "SELECT entry_id, ord, name FROM related ORDER BY entry_id, ord"),
    ("intent", "SELECT entry_id, ord, text FROM intent ORDER BY entry_id, ord"),
    ("content_item", "SELECT id, kind, key, payload FROM content_item ORDER BY id"),
)


def finalize_index(conn: sqlite3.Connection, path: Path, built_at: datetime) -> str:
    """Make the index complete and return its digest.

    Runs inside the writer's open transaction, in this order: fill and optimize `search_fts`,
    write ``schema_version``, compute the digest, write ``index_digest`` and ``built_at``,
    ``ANALYZE`` and ``PRAGMA integrity_check``.

    Args:
        conn: The writer's connection, inside its transaction.
        path: Index file, used in the error message.
        built_at: Timezone-aware build time; stored in UTC, never part of the digest.

    Returns:
        The index digest as 64 lowercase hex characters.

    Raises:
        IngestError: If the integrity check does not return a single ``ok`` row.
        sqlite3.Error: On any SQLite failure (the writer maps it).
    """
    _fill_fts(conn)
    conn.execute(_OPTIMIZE_FTS)
    conn.execute(_REPLACE_META, ("schema_version", str(SCHEMA_VERSION)))
    digest = _digest(conn)
    conn.execute(_REPLACE_META, ("index_digest", digest))
    conn.execute(
        _REPLACE_META, ("built_at", built_at.astimezone(UTC).isoformat(timespec="seconds"))
    )
    conn.execute("ANALYZE")
    check_integrity(conn.execute("PRAGMA integrity_check").fetchall(), path)
    return digest


def check_integrity(rows: Sequence[tuple[str]], path: Path) -> None:
    """Accept only the single row ``ok`` of ``PRAGMA integrity_check``.

    Raises:
        IngestError: For any other result.
    """
    if list(rows) != [("ok",)]:
        raise IngestError(f"index integrity check failed: {path}")


def _group(rows: Iterable[tuple[int, str]]) -> dict[int, list[str]]:
    grouped: dict[int, list[str]] = {}
    for entry_id, text in rows:
        grouped.setdefault(entry_id, []).append(text)
    return grouped


def _fill_fts(conn: sqlite3.Connection) -> None:
    """Insert one `search_fts` row per entry with ``rowid`` = entry id, in id order."""
    aliases = _group(conn.execute(_SELECT_ALIASES))
    intents = _group(conn.execute(_SELECT_INTENTS))
    bodies = _group(conn.execute(_SELECT_BODIES))
    entries: list[tuple[int, str, str]] = conn.execute(_SELECT_ENTRIES).fetchall()
    rows = [
        (
            entry_id,
            " ".join([name, *aliases.get(entry_id, [])]),
            "\n".join(intents.get(entry_id, [])),
            summary,
            "\n\n".join(bodies.get(entry_id, [])),
        )
        for entry_id, name, summary in entries
    ]
    conn.executemany(_INSERT_FTS, rows)


def _digest(conn: sqlite3.Connection) -> str:
    """Hash a canonical dump of the content tables (D-048)."""
    sha = hashlib.sha256()
    for table, select in _DIGEST_QUERIES:
        sha.update(f"#{table}\n".encode())
        for row in conn.execute(select):
            line = json.dumps(list(row), ensure_ascii=False, separators=(",", ":"))
            sha.update(f"{line}\n".encode())
    return sha.hexdigest()
