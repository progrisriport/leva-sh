"""Typed read-only queries over the index: the only place outside the store that sees SQL."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Final

from leva.model import (
    Entry,
    Example,
    IndexUnavailableError,
    Note,
    Section,
    Subcommand,
)
from leva.repo._fts import fts_query
from leva.repo._rows import (
    FTS_WEIGHTS,
    FtsHit,
    IndexStats,
    NameRow,
    to_entry,
    to_example,
    to_name_row,
    to_note,
    to_section,
    to_subcommand,
)

_BM25: Final = "bm25(search_fts, " + ", ".join(str(weight) for weight in FTS_WEIGHTS) + ")"

_META: Final = "SELECT key, value FROM meta ORDER BY key"
_NAMES: Final = (
    "SELECT id, name, section, kind, origin, summary, curated FROM entry ORDER BY name, rank, id"
)
_ALIASES: Final = "SELECT entry_id, alias FROM alias ORDER BY entry_id, alias"
_INTENTS: Final = "SELECT entry_id, text FROM intent ORDER BY entry_id, ord"
_ENTRY_BY_NAME: Final = (
    "SELECT id, name, section, kind, origin, summary, path, has_man, curated FROM entry"
    " WHERE name = ? AND (? IS NULL OR section = ?) ORDER BY rank, id LIMIT 1"
)
_ENTRY_BY_ALIAS: Final = (
    "SELECT e.id, e.name, e.section, e.kind, e.origin, e.summary, e.path, e.has_man, e.curated"
    " FROM entry AS e JOIN alias AS a ON a.entry_id = e.id"
    " WHERE a.alias = ? AND (? IS NULL OR e.section = ?) ORDER BY e.rank, e.name, e.id LIMIT 1"
)
_ENTRY_BY_ID: Final = (
    "SELECT id, name, section, kind, origin, summary, path, has_man, curated FROM entry"
    " WHERE id = ?"
)
_EXPLAIN: Final = "SELECT explain FROM entry WHERE id = ?"
_SECTIONS: Final = "SELECT heading, body, ord FROM doc_section WHERE entry_id = ? ORDER BY ord"
_EXAMPLES: Final = (
    "SELECT id, description, cmd, source, verified, danger FROM example"
    " WHERE entry_id = ? ORDER BY ord"
)
_NOTES: Final = "SELECT kind, text FROM note WHERE entry_id = ? ORDER BY ord"
_SUBCOMMANDS: Final = (
    "SELECT name, summary, entry_name, source, body FROM subcommand WHERE entry_id = ? ORDER BY ord"
)
_RELATED: Final = "SELECT name FROM related WHERE entry_id = ? ORDER BY ord"
_FTS: Final = (
    "SELECT rowid, " + _BM25 + " AS s FROM search_fts"  # noqa: S608  # constant weights only
    " WHERE search_fts MATCH ? ORDER BY s, rowid LIMIT ?"
)
_STATS: Final = (
    "SELECT COUNT(*),"
    " COALESCE(SUM(has_man = 1 AND kind != 'builtin'), 0),"
    " COALESCE(SUM(kind = 'builtin'), 0),"
    " COALESCE(SUM(curated = 1), 0),"
    " (SELECT COUNT(*) FROM example),"
    " (SELECT COUNT(*) FROM subcommand)"
    " FROM entry"
)


class Repository:
    """Read-only typed access to an open index.

    The repository owns the connection it is given (from ``leva.store.open_readonly``) and closes
    it in `close`. Every ``sqlite3.Error`` becomes ``IndexUnavailableError``; a stored value the
    model rejects (an incoherent index) becomes ``IndexUnavailableError("index corrupt: ...")``.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def close(self) -> None:
        """Close the connection; calling it again does nothing."""
        self._conn.close()

    @contextmanager
    def _reading(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
        except sqlite3.Error as exc:
            raise IndexUnavailableError("index unreadable", hint="run leva --rebuild") from exc

    def meta(self) -> Mapping[str, str]:
        """Return every meta item as a new dict with sorted keys."""
        with self._reading() as conn:
            return {str(key): str(value) for key, value in conn.execute(_META)}

    def names(self) -> list[NameRow]:
        """Return one row per entry ordered by ``(name, rank, id)`` for in-memory fuzzy search."""
        with self._reading() as conn:
            entries = conn.execute(_NAMES).fetchall()
            aliases = _group(conn.execute(_ALIASES))
            intents = _group(conn.execute(_INTENTS))
        return [
            to_name_row(row, aliases.get(int(str(row[0])), ()), intents.get(int(str(row[0])), ()))
            for row in entries
        ]

    def get_entry(self, name: str, section: str | None = None) -> Entry | None:
        """Find an entry by name, else by alias.

        A name match wins over an alias match; among several the lowest ``rank`` wins (then the
        id for names, the entry name then the id for aliases). ``section=None`` means any section.

        Returns:
            The entry, or ``None`` when nothing matches or ``name`` is blank.
        """
        if not name.strip():
            return None
        with self._reading() as conn:
            row = conn.execute(_ENTRY_BY_NAME, (name, section, section)).fetchone()
            if row is None:
                row = conn.execute(_ENTRY_BY_ALIAS, (name, section, section)).fetchone()
        return None if row is None else to_entry(row)

    def get_entry_by_id(self, entry_id: int) -> Entry | None:
        """Return the entry with this id, or ``None`` when the id is unknown."""
        with self._reading() as conn:
            row = conn.execute(_ENTRY_BY_ID, (entry_id,)).fetchone()
        return None if row is None else to_entry(row)

    def explain(self, entry_id: int) -> str:
        """Return the curated explanation, ``""`` when absent or the id is unknown."""
        with self._reading() as conn:
            row = conn.execute(_EXPLAIN, (entry_id,)).fetchone()
        return "" if row is None else str(row[0])

    def sections(self, entry_id: int) -> list[Section]:
        """Return the man page sections of an entry by ``ord``."""
        with self._reading() as conn:
            rows = conn.execute(_SECTIONS, (entry_id,)).fetchall()
        return [to_section(entry_id, row) for row in rows]

    def examples(self, entry_id: int) -> list[Example]:
        """Return the examples of an entry by ``ord``, each with its ``danger``."""
        with self._reading() as conn:
            rows = conn.execute(_EXAMPLES, (entry_id,)).fetchall()
        return [to_example(entry_id, row) for row in rows]

    def notes(self, entry_id: int) -> list[Note]:
        """Return the notes of an entry by ``ord``."""
        with self._reading() as conn:
            rows = conn.execute(_NOTES, (entry_id,)).fetchall()
        return [to_note(entry_id, row) for row in rows]

    def subcommands(self, entry_id: int) -> list[Subcommand]:
        """Return the subcommands of an entry by ``ord``."""
        with self._reading() as conn:
            rows = conn.execute(_SUBCOMMANDS, (entry_id,)).fetchall()
        return [to_subcommand(entry_id, row) for row in rows]

    def related(self, entry_id: int) -> list[str]:
        """Return the names of related commands by ``ord``."""
        with self._reading() as conn:
            return [str(row[0]) for row in conn.execute(_RELATED, (entry_id,))]

    def fts(self, query: str, limit: int) -> list[FtsHit]:
        """Search the full-text index with user text.

        Every whitespace-separated token is matched as a quoted string (see ``fts_query``), so
        operators and punctuation in `query` never reach the FTS5 parser. Tokens combine with AND
        over the weighted columns name, intents, summary, body (``FTS_WEIGHTS``).

        Args:
            query: Raw user text.
            limit: Maximum number of hits, at least 1.

        Returns:
            Hits by descending score, ties by ascending entry id; ``[]`` for a blank query.

        Raises:
            ValueError: If ``limit`` is below 1.
        """
        if limit < 1:
            raise ValueError(f"limit must be >= 1: {limit!r}")
        expression = fts_query(query)
        if expression is None:
            return []
        with self._reading() as conn:
            rows = conn.execute(_FTS, (expression, limit)).fetchall()
        return [FtsHit(int(rowid), -float(score)) for rowid, score in rows]

    def stats(self) -> IndexStats:
        """Count entries, man pages, builtins, curated entries, examples and subcommands."""
        with self._reading() as conn:
            counts = conn.execute(_STATS).fetchone()
        return IndexStats(*(int(count) for count in counts))


def _group(rows: sqlite3.Cursor) -> dict[int, tuple[str, ...]]:
    grouped: defaultdict[int, list[str]] = defaultdict(list)
    for entry_id, text in rows:
        grouped[int(entry_id)].append(str(text))
    return {key: tuple(values) for key, values in grouped.items()}
