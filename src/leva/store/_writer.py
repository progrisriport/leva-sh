"""Write a new index in one transaction: the only writer of the SQLite file."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final

from leva.model import (
    Example,
    IngestError,
    Kind,
    Note,
    Origin,
    Section,
    Subcommand,
    is_name,
)
from leva.store._schema import SCHEMA_VERSION, load_migrations

_INSERT_ENTRY: Final = (
    "INSERT INTO entry (name, section, kind, origin, summary, path, has_man, curated,"
    " explain, rank) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_ALIAS: Final = "INSERT OR IGNORE INTO alias (entry_id, alias) VALUES (?, ?)"
_INSERT_SECTION: Final = (
    "INSERT INTO doc_section (entry_id, ord, heading, body) VALUES (?, ?, ?, ?)"
)
_INSERT_EXAMPLE: Final = (
    "INSERT INTO example (entry_id, ord, id, description, cmd, source, verified, danger)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_SUBCOMMAND: Final = (
    "INSERT INTO subcommand (entry_id, ord, name, summary, entry_name, source, body)"
    " VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_NOTE: Final = "INSERT INTO note (entry_id, ord, kind, text) VALUES (?, ?, ?, ?)"
_INSERT_RELATED: Final = "INSERT INTO related (entry_id, ord, name) VALUES (?, ?, ?)"
_INSERT_INTENT: Final = "INSERT INTO intent (entry_id, ord, text) VALUES (?, ?, ?)"
_REPLACE_META: Final = "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)"

_UNIQUE: Final = "SQLITE_CONSTRAINT_UNIQUE"
_FOREIGN_KEY: Final = "SQLITE_CONSTRAINT_FOREIGNKEY"


def _check_member(field: str, value: object, enum_type: type[Kind] | type[Origin]) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"NewEntry.{field} must be a {enum_type.__name__} member: {value!r}")


@dataclass(frozen=True, slots=True)
class NewEntry:
    """An entry to add to a new index; ids are assigned by the writer.

    Attributes:
        name: Command name.
        section: Man section such as ``1``, or ``None``.
        kind: What the entry is.
        origin: Where it comes from.
        summary: One-line description, ``""`` when absent.
        path: Path of the binary, or ``None``.
        has_man: Whether a man page exists.
        curated: Whether curated content exists.
        rank: Position among entries of the same name; 0 is the primary one (D-005).
        explain: Curated explanation, ``""`` when absent.

    Raises:
        ValueError: If ``name`` or a set ``section`` is empty or contains whitespace, if
            ``kind`` or ``origin`` is not an enum member, or if ``rank`` is negative.
    """

    name: str
    section: str | None
    kind: Kind
    origin: Origin
    summary: str
    path: str | None
    has_man: bool
    curated: bool
    rank: int = 0
    explain: str = ""

    def __post_init__(self) -> None:
        if not is_name(self.name):
            raise ValueError(f"NewEntry.name must be non-empty without whitespace: {self.name!r}")
        if self.section is not None and not is_name(self.section):
            raise ValueError(
                f"NewEntry.section must be non-empty without whitespace: {self.section!r}"
            )
        _check_member("kind", self.kind, Kind)
        _check_member("origin", self.origin, Origin)
        if self.rank < 0:
            raise ValueError(f"NewEntry.rank must be >= 0: {self.rank!r}")


def _check_names(owner: str, values: Sequence[str]) -> None:
    for value in values:
        if not is_name(value):
            raise ValueError(f"{owner} must be non-empty without whitespace: {value!r}")


def _check_intents(texts: Sequence[str]) -> None:
    for text in texts:
        if not text.strip() or len(text.splitlines()) != 1:
            raise ValueError(f"intent must be one non-blank line: {text!r}")


class IndexWriter:
    """Unit of work that builds a new index file inside one transaction.

    Use it as a context manager. Entering creates the file with the schema; leaving commits
    when the block ends normally and rolls back when it raises. After a rollback the file
    exists but holds no tables and has ``user_version`` 0, so ``open_readonly`` rejects it and
    the caller removes it.

    Each ``add_*`` list method is called at most once per entry: a second call collides on the
    ``(entry_id, ord)`` key and raises ``IngestError``.
    """

    def __init__(self, path: Path) -> None:
        """Remember the target file; nothing is opened yet.

        Raises:
            ValueError: If `path` already exists (programmer error: remove a stale file first).
        """
        if path.exists() or path.is_symlink():
            raise ValueError(f"index file already exists: {path}")
        self._path = path
        self._conn: sqlite3.Connection | None = None
        self._entered = False

    def __enter__(self) -> IndexWriter:
        """Create the file, apply the schema and start the transaction.

        Raises:
            ValueError: If the writer was entered before.
            IngestError: If the file cannot be created or the schema cannot be applied
                (for example when SQLite has no FTS5).
        """
        if self._entered:
            raise ValueError("index writer already entered")
        self._entered = True
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(self._path, isolation_level=None)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript("BEGIN;\n" + "\n".join(load_migrations()))
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error as exc:
            if conn is not None:
                conn.close()
            raise self._failure() from exc
        self._conn = conn
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commit when no exception is pending, else roll back; always close the file.

        Raises:
            IngestError: If the commit fails.
        """
        conn = self._connection()
        self._conn = None
        try:
            if exc_type is None:
                conn.execute("COMMIT")
            else:
                with suppress(sqlite3.Error):
                    conn.execute("ROLLBACK")
        except sqlite3.Error as error:
            raise self._failure() from error
        finally:
            conn.close()

    def add_entry(self, entry: NewEntry) -> int:
        """Insert `entry` and return its id (1, 2, 3, ... in call order).

        Raises:
            ValueError: If the writer is not open.
            IngestError: If an entry with the same name, section and origin exists.
        """
        duplicate = f"duplicate entry: {entry.name} {entry.section or '-'} {entry.origin}"
        row = (
            entry.name,
            entry.section,
            entry.kind.value,
            entry.origin.value,
            entry.summary,
            entry.path,
            int(entry.has_man),
            int(entry.curated),
            entry.explain,
            entry.rank,
        )
        with self._writing(duplicate=duplicate) as conn:
            entry_id = conn.execute(_INSERT_ENTRY, row).lastrowid
        if entry_id is None:
            raise self._failure()
        return entry_id

    def add_alias(self, entry_id: int, alias: str) -> None:
        """Add an alias of an entry; repeating the same alias is ignored.

        Raises:
            ValueError: If `alias` is not a name or the writer is not open.
            IngestError: If `entry_id` is unknown.
        """
        _check_names("alias", [alias])
        with self._writing(entry_id=entry_id) as conn:
            conn.execute(_INSERT_ALIAS, (entry_id, alias))

    def add_sections(self, entry_id: int, sections: Sequence[Section]) -> None:
        """Add the man page sections of an entry, keeping each ``Section.ord``.

        Raises:
            ValueError: If the writer is not open.
            IngestError: If `entry_id` is unknown or the entry already has sections.
        """
        rows = [(entry_id, item.ord, item.heading, item.body) for item in sections]
        self._insert_many(_INSERT_SECTION, rows, entry_id)

    def add_examples(self, entry_id: int, examples: Sequence[Example]) -> None:
        """Add the examples of an entry; ``ord`` is the index in `examples`.

        Raises:
            ValueError: If the writer is not open.
            IngestError: If `entry_id` is unknown or the entry already has examples.
        """
        rows = [
            (entry_id, ord_, e.id, e.desc, e.cmd, e.source, e.verified, e.danger)
            for ord_, e in enumerate(examples)
        ]
        self._insert_many(_INSERT_EXAMPLE, rows, entry_id)

    def add_subcommands(self, entry_id: int, subs: Sequence[Subcommand]) -> None:
        """Add the subcommands of an entry; ``ord`` is the index in `subs`.

        Raises:
            ValueError: If the writer is not open.
            IngestError: If `entry_id` is unknown or the entry already has subcommands.
        """
        rows = [
            (entry_id, ord_, s.name, s.summary, s.entry_name, s.source, s.body)
            for ord_, s in enumerate(subs)
        ]
        self._insert_many(_INSERT_SUBCOMMAND, rows, entry_id)

    def add_notes(self, entry_id: int, notes: Sequence[Note]) -> None:
        """Add the notes of an entry; ``ord`` is the index in `notes`.

        Raises:
            ValueError: If the writer is not open.
            IngestError: If `entry_id` is unknown or the entry already has notes.
        """
        rows = [(entry_id, ord_, n.kind, n.text) for ord_, n in enumerate(notes)]
        self._insert_many(_INSERT_NOTE, rows, entry_id)

    def add_related(self, entry_id: int, names: Sequence[str]) -> None:
        """Add the related command names of an entry; ``ord`` is the index in `names`.

        Raises:
            ValueError: If a name is not a name or the writer is not open.
            IngestError: If `entry_id` is unknown or the entry already has related names.
        """
        _check_names("related", names)
        rows = [(entry_id, ord_, name) for ord_, name in enumerate(names)]
        self._insert_many(_INSERT_RELATED, rows, entry_id)

    def add_intents(self, entry_id: int, texts: Sequence[str]) -> None:
        """Add the curated intents of an entry; ``ord`` is the index in `texts` (D-029).

        Raises:
            ValueError: If a text is blank or spans several lines, or the writer is not open.
            IngestError: If `entry_id` is unknown or the entry already has intents.
        """
        _check_intents(texts)
        rows = [(entry_id, ord_, text) for ord_, text in enumerate(texts)]
        self._insert_many(_INSERT_INTENT, rows, entry_id)

    def set_meta(self, key: str, value: str) -> None:
        """Set a meta value, replacing an existing one.

        Raises:
            ValueError: If `key` is blank or the writer is not open.
        """
        if not key.strip():
            raise ValueError(f"meta key must not be blank: {key!r}")
        with self._writing() as conn:
            conn.execute(_REPLACE_META, (key, value))

    def _insert_many(self, sql: str, rows: Sequence[tuple[object, ...]], entry_id: int) -> None:
        with self._writing(entry_id=entry_id) as conn:
            conn.executemany(sql, rows)

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise ValueError("index writer is not open")
        return self._conn

    def _failure(self) -> IngestError:
        return IngestError(f"cannot write index: {self._path}")

    @contextmanager
    def _writing(
        self, *, entry_id: int | None = None, duplicate: str | None = None
    ) -> Iterator[sqlite3.Connection]:
        """Yield the open connection and map SQLite errors to `IngestError`.

        A text that cannot be encoded to UTF-8 (a lone surrogate) is mapped the same way, so
        only `IngestError` leaves a write.
        """
        conn = self._connection()
        try:
            yield conn
        except sqlite3.IntegrityError as exc:
            code = exc.sqlite_errorname
            if code == _FOREIGN_KEY and entry_id is not None:
                raise IngestError(f"unknown entry id: {entry_id}") from exc
            if code == _UNIQUE and duplicate is not None:
                raise IngestError(duplicate) from exc
            raise self._failure() from exc
        except (sqlite3.Error, UnicodeEncodeError) as exc:
            raise self._failure() from exc
