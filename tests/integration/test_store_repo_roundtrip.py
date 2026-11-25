"""Round trip: what `IndexWriter` writes is what `Repository` reads, for every table."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from leva.model import (
    Entry,
    Example,
    IndexUnavailableError,
    IngestError,
    Kind,
    Note,
    Origin,
    Section,
    Subcommand,
)
from leva.repo import IndexStats, Repository
from leva.store import IndexWriter, NewEntry, open_readonly

BUILT_AT = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)

SECTIONS = [
    Section("NAME", "pack - bundle files", 0),
    Section("DESCRIPTION", 'Line one.\n\nLine two with ünïcode and a "quote".', 3),
]
EXAMPLES = [
    Example("pack-all", "Bundle a folder", "pack {{folder}}", "curated", "exec"),
    Example("pack-rm", "Bundle then delete", "pack x && rm x", "curated", "skip", "deletes x"),
    Example("pack-tldr", "From a page", "pack -v", "tldr", "none"),
]
SUBCOMMANDS = [
    Subcommand("add", "Add a file.", None, "section", "Body of add."),
    Subcommand("log", "Show history.", "pack-log", "hyphen", ""),
]
NOTES = [Note("macos", "First note."), Note("bsd-gnu", "Second note.")]
RELATED = ["cat", "zip"]
INTENTS = ["bundle files", "make an archive"]


def write_roundtrip_index(path: Path) -> dict[str, int]:
    """Write two `pack` entries (rank 0 with every child, rank 1 bare) and a bare `cat`."""
    with IndexWriter(path) as writer:
        pack = writer.add_entry(
            NewEntry(
                "pack",
                "1",
                Kind.EXECUTABLE,
                Origin.MACOS,
                "bundle files",
                "/usr/bin/pack",
                True,
                True,
                rank=0,
                explain="Bundles files into one.",
            )
        )
        other = writer.add_entry(
            NewEntry("pack", None, Kind.EXECUTABLE, Origin.HOMEBREW, "", None, False, False, rank=1)
        )
        cat = writer.add_entry(
            NewEntry("cat", "1", Kind.EXECUTABLE, Origin.MACOS, "print files", None, True, False)
        )
        writer.add_alias(pack, "unpack")
        writer.add_alias(pack, "bundle")
        writer.add_sections(pack, SECTIONS)
        writer.add_examples(pack, EXAMPLES)
        writer.add_subcommands(pack, SUBCOMMANDS)
        writer.add_notes(pack, NOTES)
        writer.add_related(pack, RELATED)
        writer.add_intents(pack, INTENTS)
        writer.set_meta("attribution", "synthetic")
        writer.finalize(built_at=BUILT_AT)
    return {"pack": pack, "other": other, "cat": cat}


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repository]:
    path = tmp_path / "index.db"
    ids = write_roundtrip_index(path)
    assert ids == {"pack": 1, "other": 2, "cat": 3}
    repository = Repository(open_readonly(path))
    yield repository
    repository.close()


def test_entry_round_trips(repo: Repository) -> None:
    assert repo.get_entry("pack") == Entry(
        1, "pack", "1", Kind.EXECUTABLE, Origin.MACOS, "bundle files", "/usr/bin/pack", True, True
    )
    assert repo.get_entry_by_id(2) == Entry(
        2, "pack", None, Kind.EXECUTABLE, Origin.HOMEBREW, "", None, False, False
    )
    assert repo.explain(1) == "Bundles files into one."
    assert repo.explain(2) == ""


def test_children_round_trip_in_order(repo: Repository) -> None:
    assert repo.sections(1) == SECTIONS
    assert repo.examples(1) == EXAMPLES
    assert repo.subcommands(1) == SUBCOMMANDS
    assert repo.notes(1) == NOTES
    assert repo.related(1) == RELATED


def test_entries_without_children_read_back_empty(repo: Repository) -> None:
    for entry_id in (2, 3):
        assert repo.sections(entry_id) == []
        assert repo.examples(entry_id) == []
        assert repo.subcommands(entry_id) == []
        assert repo.notes(entry_id) == []
        assert repo.related(entry_id) == []


def test_name_rows_carry_aliases_and_intents(repo: Repository) -> None:
    rows = {row.entry_id: row for row in repo.names()}

    assert rows[1].aliases == ("bundle", "unpack")
    assert rows[1].intents == tuple(INTENTS)
    assert (rows[2].aliases, rows[2].intents) == ((), ())
    assert [row.entry_id for row in repo.names()] == [3, 1, 2]


def test_alias_resolves_to_its_entry(repo: Repository) -> None:
    entry = repo.get_entry("unpack")

    assert entry is not None
    assert entry.id == 1


def test_meta_and_stats_round_trip(repo: Repository) -> None:
    meta = repo.meta()

    assert meta["attribution"] == "synthetic"
    assert meta["built_at"] == "2026-03-04T05:06:07+00:00"
    assert meta["schema_version"] == "1"
    assert repo.stats() == IndexStats(
        entries=3, man_pages=2, builtins=0, curated=1, examples=3, subcommands=2
    )


def test_fts_finds_each_written_text(repo: Repository) -> None:
    for query in ("unpack", "archive", "ünïcode", "Line two", "bundle files"):
        assert [hit.entry_id for hit in repo.fts(query, 5)][:1] == [1], query
    assert [hit.entry_id for hit in repo.fts("print", 5)] == [3]


def add_duplicate_entries(path: Path) -> None:
    with IndexWriter(path) as writer:
        duplicate = NewEntry("a", None, Kind.EXECUTABLE, Origin.MACOS, "", None, False, False)
        writer.add_entry(duplicate)
        writer.add_entry(duplicate)


def test_a_rolled_back_build_is_not_readable(tmp_path: Path) -> None:
    path = tmp_path / "index.db"

    with pytest.raises(IngestError):
        add_duplicate_entries(path)

    with pytest.raises(IndexUnavailableError, match="index schema 0 is not 1"):
        open_readonly(path)
