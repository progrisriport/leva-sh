"""Build the synthetic fixture index (``fixtures/index/entries.json``) with ``IndexWriter``."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from leva.model import Example, Kind, Note, Origin, Section, Subcommand
from leva.store import IndexWriter, NewEntry

FIXTURE_JSON: Final = Path(__file__).resolve().parent.parent / "fixtures" / "index" / "entries.json"
FIXED_BUILT_AT: Final = datetime(2026, 1, 1, tzinfo=UTC)

_TOP_KEYS: Final = frozenset({"meta", "entries"})
_REQUIRED_KEYS: Final = frozenset(
    {"name", "section", "kind", "origin", "summary", "path", "has_man", "curated", "rank"}
)
_LIST_KEYS: Final = frozenset(
    {"aliases", "intents", "sections", "examples", "notes", "subcommands", "related"}
)
_ENTRY_KEYS: Final = _REQUIRED_KEYS | _LIST_KEYS | {"explain"}
_SECTION_KEYS: Final = frozenset({"heading", "body"})
_EXAMPLE_KEYS: Final = frozenset({"id", "desc", "cmd", "source", "verified", "danger"})
_EXAMPLE_REQUIRED: Final = _EXAMPLE_KEYS - {"danger"}
_NOTE_KEYS: Final = frozenset({"kind", "text"})
_SUBCOMMAND_KEYS: Final = frozenset({"name", "summary", "entry_name", "source", "body"})
_SUBCOMMAND_REQUIRED: Final = _SUBCOMMAND_KEYS - {"body"}

Raw = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class FixtureEntry:
    """One entry of the fixture index with every child list."""

    entry: NewEntry
    aliases: tuple[str, ...] = ()
    intents: tuple[str, ...] = ()
    sections: tuple[Section, ...] = ()
    examples: tuple[Example, ...] = ()
    notes: tuple[Note, ...] = ()
    subcommands: tuple[Subcommand, ...] = ()
    related: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FixtureData:
    """The whole fixture: meta items and entries in write order (ids are 1-based positions)."""

    meta: Mapping[str, str]
    entries: tuple[FixtureEntry, ...]


def _check_keys(where: str, item: Raw, allowed: frozenset[str], required: frozenset[str]) -> None:
    for key in item:
        if key not in allowed:
            raise ValueError(f"{where}: unknown key {key!r}")
    for key in sorted(required - item.keys()):
        raise ValueError(f"{where}: missing key {key!r}")


def _object(where: str, value: object) -> Raw:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected an object")
    return value


def _text(where: str, raw: Raw, key: str, default: str | None = None) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{where}: {key!r} must be a string")
    return value


def _optional_text(where: str, raw: Raw, key: str) -> str | None:
    return None if raw.get(key) is None else _text(where, raw, key)


def _flag(where: str, raw: Raw, key: str) -> bool:
    value = raw[key]
    if not isinstance(value, bool):
        raise ValueError(f"{where}: {key!r} must be a boolean")
    return value


def _items(where: str, raw: Raw, key: str) -> list[object]:
    value = raw.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{where}: {key!r} must be a list")
    return value


def _strings(where: str, raw: Raw, key: str) -> tuple[str, ...]:
    items = _items(where, raw, key)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{where}: {key!r} must be a list of strings")
    return tuple(map(str, items))


def _objects(where: str, raw: Raw, key: str) -> list[Raw]:
    return [_object(f"{where} {key}", item) for item in _items(where, raw, key)]


def _section(where: str, ord_: int, raw: Raw) -> Section:
    where = f"{where} section {ord_}"
    _check_keys(where, raw, _SECTION_KEYS, _SECTION_KEYS)
    body = raw["body"]
    text = "\n".join(_strings(where, raw, "body")) if isinstance(body, list) else body
    if not isinstance(text, str):
        raise ValueError(f"{where}: 'body' must be a string or a list of strings")
    return Section(_text(where, raw, "heading"), text, ord_)


def _example(where: str, raw: Raw) -> Example:
    where = f"{where} example {raw.get('id')}"
    _check_keys(where, raw, _EXAMPLE_KEYS, _EXAMPLE_REQUIRED)
    return Example(
        _text(where, raw, "id"),
        _text(where, raw, "desc"),
        _text(where, raw, "cmd"),
        _text(where, raw, "source"),  # type: ignore[arg-type]  # Example validates the literal
        _text(where, raw, "verified"),  # type: ignore[arg-type]  # Example validates the literal
        _optional_text(where, raw, "danger"),
    )


def _note(where: str, raw: Raw) -> Note:
    where = f"{where} note"
    _check_keys(where, raw, _NOTE_KEYS, _NOTE_KEYS)
    kind = _text(where, raw, "kind")
    return Note(kind, _text(where, raw, "text"))  # type: ignore[arg-type]  # Note validates kind


def _subcommand(where: str, raw: Raw) -> Subcommand:
    where = f"{where} subcommand {raw.get('name')}"
    _check_keys(where, raw, _SUBCOMMAND_KEYS, _SUBCOMMAND_REQUIRED)
    return Subcommand(
        _text(where, raw, "name"),
        _text(where, raw, "summary"),
        _optional_text(where, raw, "entry_name"),
        _text(where, raw, "source"),
        _text(where, raw, "body", ""),
    )


def _new_entry(where: str, raw: Raw) -> NewEntry:
    rank = raw["rank"]
    if not isinstance(rank, int) or isinstance(rank, bool):
        raise ValueError(f"{where}: 'rank' must be an integer")
    return NewEntry(
        name=_text(where, raw, "name"),
        section=_optional_text(where, raw, "section"),
        kind=Kind(_text(where, raw, "kind")),
        origin=Origin(_text(where, raw, "origin")),
        summary=_text(where, raw, "summary"),
        path=_optional_text(where, raw, "path"),
        has_man=_flag(where, raw, "has_man"),
        curated=_flag(where, raw, "curated"),
        rank=rank,
        explain=_text(where, raw, "explain", ""),
    )


def _entry(item: object) -> FixtureEntry:
    raw = _object("entry", item)
    where = f"entry {raw.get('name')}"
    _check_keys(where, raw, _ENTRY_KEYS, _REQUIRED_KEYS)
    return FixtureEntry(
        _new_entry(where, raw),
        aliases=_strings(where, raw, "aliases"),
        intents=_strings(where, raw, "intents"),
        sections=tuple(
            _section(where, i, s) for i, s in enumerate(_objects(where, raw, "sections"))
        ),
        examples=tuple(_example(where, e) for e in _objects(where, raw, "examples")),
        notes=tuple(_note(where, n) for n in _objects(where, raw, "notes")),
        subcommands=tuple(_subcommand(where, s) for s in _objects(where, raw, "subcommands")),
        related=_strings(where, raw, "related"),
    )


def load_fixture(path: Path = FIXTURE_JSON) -> FixtureData:
    """Read and validate the fixture JSON.

    Raises:
        ValueError: On an unknown or missing key or a value of the wrong JSON type at any level
            (the message names the entry and the key), or when a value breaks a model invariant.
    """
    raw = _object("fixture", json.loads(path.read_text(encoding="utf-8")))
    _check_keys("fixture", raw, _TOP_KEYS, _TOP_KEYS)
    meta = _object("meta", raw["meta"])
    values = {key: _text("meta", meta, key) for key in meta}
    return FixtureData(values, tuple(_entry(item) for item in _items("fixture", raw, "entries")))


def _write_entry(writer: IndexWriter, item: FixtureEntry) -> None:
    entry_id = writer.add_entry(item.entry)
    for alias in item.aliases:
        writer.add_alias(entry_id, alias)
    writer.add_sections(entry_id, item.sections)
    writer.add_examples(entry_id, item.examples)
    writer.add_subcommands(entry_id, item.subcommands)
    writer.add_notes(entry_id, item.notes)
    writer.add_related(entry_id, item.related)
    writer.add_intents(entry_id, item.intents)


def build_fixture_index(target: Path, data: FixtureData | None = None) -> Path:
    """Write the fixture index to `target` (its parent is created) and return `target`.

    Entries are written in order, so entry ids are 1-based positions; `built_at` is
    `FIXED_BUILT_AT`, so two builds of the same data have the same digest.
    """
    data = load_fixture() if data is None else data
    target.parent.mkdir(parents=True, exist_ok=True)
    with IndexWriter(target) as writer:
        for item in data.entries:
            _write_entry(writer, item)
        for key, value in data.meta.items():
            writer.set_meta(key, value)
        writer.finalize(built_at=FIXED_BUILT_AT)
    return target
