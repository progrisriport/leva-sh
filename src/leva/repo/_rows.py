"""Row types returned by the repository and the converters from raw SQL rows to model types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast

from leva.model import (
    Entry,
    Example,
    ExampleSource,
    IndexUnavailableError,
    Kind,
    Note,
    NoteKind,
    Origin,
    Section,
    Subcommand,
    Verification,
)

FTS_WEIGHTS: Final = (10.0, 5.0, 2.0, 1.0)  # name, intents, summary, body

_REBUILD_HINT: Final = "run leva --rebuild"

Row = tuple[object, ...]


@dataclass(frozen=True, slots=True)
class NameRow:
    """One entry as the in-memory name list sees it (fuzzy search input).

    Attributes:
        entry_id: Index row id.
        name: Command name.
        section: Man section, or ``None``.
        kind: What the entry is.
        origin: Where it comes from.
        summary: One-line description, ``""`` when absent.
        curated: Whether curated content exists.
        aliases: Aliases in plain ``str`` order.
        intents: Curated intents by their stored order (D-029).
    """

    entry_id: int
    name: str
    section: str | None
    kind: Kind
    origin: Origin
    summary: str
    curated: bool
    aliases: tuple[str, ...]
    intents: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FtsHit:
    """A full-text match.

    Attributes:
        entry_id: Index row id of the matching entry.
        score: Negated ``bm25`` value: higher is better.
    """

    entry_id: int
    score: float


@dataclass(frozen=True, slots=True)
class IndexStats:
    """Counts describing the index.

    Attributes:
        entries: Rows in ``entry``.
        man_pages: Entries with a man page that are not builtins.
        builtins: Entries of kind builtin.
        curated: Entries with curated content.
        examples: Rows in ``example``.
        subcommands: Rows in ``subcommand``.
    """

    entries: int
    man_pages: int
    builtins: int
    curated: int
    examples: int
    subcommands: int


def corrupt(table: str, entry_id: int) -> IndexUnavailableError:
    """Return the error for a stored row the model rejects."""
    return IndexUnavailableError(f"index corrupt: {table} row {entry_id}", hint=_REBUILD_HINT)


def _optional(value: object) -> str | None:
    return None if value is None else str(value)


def to_entry(row: Row) -> Entry:
    """Convert an ``(id, name, section, kind, origin, summary, path, has_man, curated)`` row.

    Raises:
        IndexUnavailableError: If the model rejects a stored value.
    """
    entry_id, name, section, kind, origin, summary, path, has_man, curated = row
    try:
        return Entry(
            id=int(str(entry_id)),
            name=str(name),
            section=_optional(section),
            kind=Kind(str(kind)),
            origin=Origin(str(origin)),
            summary=str(summary),
            path=_optional(path),
            has_man=bool(has_man),
            curated=bool(curated),
        )
    except ValueError as exc:
        raise corrupt("entry", int(str(entry_id))) from exc


def to_name_row(row: Row, aliases: tuple[str, ...], intents: tuple[str, ...]) -> NameRow:
    """Convert an ``(id, name, section, kind, origin, summary, curated)`` row to a `NameRow`.

    Raises:
        IndexUnavailableError: If ``kind`` or ``origin`` is not a known value.
    """
    entry_id, name, section, kind, origin, summary, curated = row
    try:
        return NameRow(
            entry_id=int(str(entry_id)),
            name=str(name),
            section=_optional(section),
            kind=Kind(str(kind)),
            origin=Origin(str(origin)),
            summary=str(summary),
            curated=bool(curated),
            aliases=aliases,
            intents=intents,
        )
    except ValueError as exc:
        raise corrupt("entry", int(str(entry_id))) from exc


def to_section(entry_id: int, row: Row) -> Section:
    """Convert a ``(heading, body, ord)`` row to a `Section`."""
    heading, body, position = row
    try:
        return Section(str(heading), str(body), int(str(position)))
    except ValueError as exc:
        raise corrupt("doc_section", entry_id) from exc


def to_example(entry_id: int, row: Row) -> Example:
    """Convert an ``(id, description, cmd, source, verified, danger)`` row to an `Example`."""
    example_id, description, cmd, source, verified, danger = row
    try:
        return Example(
            str(example_id),
            str(description),
            str(cmd),
            # Example.__post_init__ validates the literal.
            cast(ExampleSource, str(source)),
            cast(Verification, str(verified)),
            _optional(danger),
        )
    except ValueError as exc:
        raise corrupt("example", entry_id) from exc


def to_note(entry_id: int, row: Row) -> Note:
    """Convert a ``(kind, text)`` row to a `Note`."""
    kind, text = row
    try:
        return Note(cast(NoteKind, str(kind)), str(text))  # Note.__post_init__ validates kind
    except ValueError as exc:
        raise corrupt("note", entry_id) from exc


def to_subcommand(entry_id: int, row: Row) -> Subcommand:
    """Convert a ``(name, summary, entry_name, source, body)`` row to a `Subcommand`."""
    name, summary, entry_name, source, body = row
    try:
        return Subcommand(str(name), str(summary), _optional(entry_name), str(source), str(body))
    except ValueError as exc:
        raise corrupt("subcommand", entry_id) from exc
