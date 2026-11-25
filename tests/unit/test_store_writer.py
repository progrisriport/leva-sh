"""Tests for the index schema, `IndexWriter`, `NewEntry` and `open_readonly`."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from contextlib import closing
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

from leva.model import (
    Example,
    IndexUnavailableError,
    IngestError,
    Kind,
    Note,
    Origin,
    Section,
    Subcommand,
)
from leva.store import SCHEMA_VERSION, IndexWriter, NewEntry, open_readonly
from leva.store._schema import load_migrations, order_migrations

REBUILD_HINT = "run leva --rebuild"


def new_entry(
    name: str = "ls",
    section: str | None = None,
    origin: Origin = Origin.MACOS,
    **fields: Any,
) -> NewEntry:
    """Return a valid `NewEntry`, overriding any field."""
    values: dict[str, Any] = {
        "kind": Kind.EXECUTABLE,
        "summary": "List files.",
        "path": "/bin/ls",
        "has_man": True,
        "curated": False,
    }
    values.update(fields)
    return NewEntry(name=name, section=section, origin=origin, **values)


def example(id_: str, danger: str | None = None) -> Example:
    """Return a valid `Example` with the given id and danger."""
    return Example(
        id=id_,
        desc=f"desc {id_}",
        cmd=f"cmd {id_}",
        source="curated",
        verified="exec",
        danger=danger,
    )


def rows(path: Path, sql: str) -> list[tuple[Any, ...]]:
    """Run a read-only query on the file at `path` and return every row."""
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(sql).fetchall()


def user_version(path: Path) -> int:
    """Return `PRAGMA user_version` of the file at `path`."""
    return int(rows(path, "PRAGMA user_version")[0][0])


def build_index(path: Path) -> Path:
    """Write an index with one entry and return its path."""
    with IndexWriter(path) as writer:
        writer.add_entry(new_entry())
    return path


# 1. round trip


def test_round_trip_stores_every_child_list(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        entry_id = writer.add_entry(
            new_entry(
                "ls",
                "1",
                summary="List files.",
                path="/bin/ls",
                has_man=True,
                curated=True,
                rank=2,
                explain="Lists directory contents.",
            )
        )
        writer.add_alias(entry_id, "dir")
        writer.add_alias(entry_id, "vdir")
        writer.add_sections(entry_id, [Section("NAME", "ls - list", 0), Section("SEE ALSO", "", 1)])
        writer.add_examples(entry_id, [example("ls-a"), example("ls-b", danger="removes things")])
        writer.add_subcommands(entry_id, [Subcommand("sub", "A sub.", "ls-sub", "hyphen", "Long.")])
        writer.add_notes(entry_id, [Note("macos", "n1"), Note("safety", "n2")])
        writer.add_related(entry_id, ["cat", "find"])
        writer.add_intents(entry_id, ["list files", "show dir", "see contents"])
        writer.set_meta("content_version", "abc")

    assert user_version(path) == SCHEMA_VERSION
    assert rows(path, "SELECT * FROM entry") == [
        (
            1,
            "ls",
            "1",
            "executable",
            "macos",
            "List files.",
            "/bin/ls",
            1,
            1,
            "Lists directory contents.",
            2,
        )
    ]
    assert rows(path, "SELECT * FROM alias ORDER BY alias") == [(1, "dir"), (1, "vdir")]
    assert rows(path, "SELECT * FROM doc_section ORDER BY ord") == [
        (1, 0, "NAME", "ls - list"),
        (1, 1, "SEE ALSO", ""),
    ]
    assert rows(path, "SELECT * FROM example ORDER BY ord") == [
        (1, 0, "ls-a", "desc ls-a", "cmd ls-a", "curated", "exec", None),
        (1, 1, "ls-b", "desc ls-b", "cmd ls-b", "curated", "exec", "removes things"),
    ]
    assert rows(path, "SELECT * FROM subcommand") == [
        (1, 0, "sub", "A sub.", "ls-sub", "hyphen", "Long.")
    ]
    assert rows(path, "SELECT * FROM note ORDER BY ord") == [
        (1, 0, "macos", "n1"),
        (1, 1, "safety", "n2"),
    ]
    assert rows(path, "SELECT * FROM related ORDER BY ord") == [(1, 0, "cat"), (1, 1, "find")]
    assert rows(path, "SELECT * FROM intent ORDER BY ord") == [
        (1, 0, "list files"),
        (1, 1, "show dir"),
        (1, 2, "see contents"),
    ]
    assert rows(path, "SELECT * FROM meta") == [("content_version", "abc")]


def test_round_trip_stores_null_and_false_values(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        writer.add_entry(
            new_entry("cd", None, Origin.ZSH, kind=Kind.BUILTIN, path=None, has_man=False)
        )
        writer.add_entry(new_entry("x", None, Origin.HOMEBREW, kind=Kind.MANPAGE_ONLY))

    query = "SELECT name, section, kind, origin, path, has_man, curated, explain, rank FROM entry"
    assert rows(path, query + " ORDER BY id") == [
        ("cd", None, "builtin", "zsh", None, 0, 0, "", 0),
        ("x", None, "manpage", "homebrew", "/bin/ls", 1, 0, "", 0),
    ]


def test_subcommand_with_null_entry_name_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        entry_id = writer.add_entry(new_entry())
        writer.add_subcommands(entry_id, [Subcommand("sub", "", None, "probe")])

    assert rows(path, "SELECT name, summary, entry_name, source, body FROM subcommand") == [
        ("sub", "", None, "probe", "")
    ]


# 2. ids


def test_add_entry_returns_ids_in_call_order(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        ids = [writer.add_entry(new_entry(name)) for name in ("a", "b", "c")]

    assert ids == [1, 2, 3]


# 3. uniqueness


def test_add_entry_rejects_duplicate_with_null_section(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        writer.add_entry(new_entry("ls", None, Origin.MACOS))
        with pytest.raises(IngestError) as caught:
            writer.add_entry(new_entry("ls", None, Origin.MACOS))

    assert caught.value.message == "duplicate entry: ls - macos"


def test_add_entry_rejects_duplicate_with_section(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        writer.add_entry(new_entry("ls", "1", Origin.MACOS))
        with pytest.raises(IngestError) as caught:
            writer.add_entry(new_entry("ls", "1", Origin.MACOS))

    assert caught.value.message == "duplicate entry: ls 1 macos"


def test_add_entry_accepts_same_name_with_other_section_or_origin(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        writer.add_entry(new_entry("ls", "1", Origin.MACOS))
        writer.add_entry(new_entry("ls", None, Origin.MACOS))
        writer.add_entry(new_entry("ls", "1", Origin.HOMEBREW))

    assert rows(path, "SELECT COUNT(*) FROM entry") == [(3,)]


def test_unique_index_treats_null_section_like_empty(tmp_path: Path) -> None:
    path = build_index(tmp_path / "index.db")

    index = rows(path, "SELECT sql FROM sqlite_master WHERE name = 'entry_key'")

    assert index == [
        ("CREATE UNIQUE INDEX entry_key ON entry (name, IFNULL(section, ''), origin)",)
    ]


# 4. rollback


class BoomError(Exception):
    """Raised inside a `with` block by the rollback test."""


def write_then_raise(path: Path, failure: Exception) -> None:
    """Add an entry inside the writer, then raise `failure` before the block ends."""
    with IndexWriter(path) as writer:
        writer.add_entry(new_entry())
        raise failure


def test_exception_rolls_back_and_propagates_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    failure = BoomError("stop")

    with pytest.raises(BoomError) as caught:
        write_then_raise(path, failure)

    assert caught.value is failure
    assert path.exists()
    assert rows(path, "SELECT name FROM sqlite_master WHERE name = 'entry'") == []
    assert user_version(path) == 0
    with pytest.raises(IndexUnavailableError) as unavailable:
        open_readonly(path)
    assert unavailable.value.message == f"index schema 0 is not {SCHEMA_VERSION}: {path}"


def test_rollback_after_failed_write_keeps_the_write_error(tmp_path: Path) -> None:
    path = tmp_path / "index.db"

    with pytest.raises(IngestError, match="unknown entry id: 7"), IndexWriter(path) as writer:
        writer.add_alias(7, "x")

    assert user_version(path) == 0


# 5. lifecycle


def test_writer_rejects_existing_path(tmp_path: Path) -> None:
    path = build_index(tmp_path / "index.db")

    with pytest.raises(ValueError, match="already exists"):
        IndexWriter(path)


def test_writer_rejects_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="already exists"):
        IndexWriter(tmp_path)


def test_writer_creates_nothing_before_enter(tmp_path: Path) -> None:
    path = tmp_path / "index.db"

    IndexWriter(path)

    assert not path.exists()


def test_enter_with_missing_parent_raises_ingest_error(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "index.db"

    with pytest.raises(IngestError) as caught, IndexWriter(path):
        pass

    assert caught.value.message == f"cannot write index: {path}"
    assert isinstance(caught.value.__cause__, sqlite3.Error)


def test_enter_twice_raises_value_error(tmp_path: Path) -> None:
    writer = IndexWriter(tmp_path / "index.db")
    with writer, pytest.raises(ValueError, match="already entered"), writer:
        pass


def test_enter_after_exit_raises_value_error(tmp_path: Path) -> None:
    writer = IndexWriter(tmp_path / "index.db")
    with writer:
        pass

    with pytest.raises(ValueError, match="already entered"), writer:
        pass


ADDERS: dict[str, Callable[[IndexWriter, int], None]] = {
    "add_alias": lambda w, i: w.add_alias(i, "a"),
    "add_sections": lambda w, i: w.add_sections(i, [Section("H", "b", 0)]),
    "add_examples": lambda w, i: w.add_examples(i, [example("ls-a")]),
    "add_subcommands": lambda w, i: w.add_subcommands(i, [Subcommand("s", "", None, "probe")]),
    "add_notes": lambda w, i: w.add_notes(i, [Note("macos", "t")]),
    "add_related": lambda w, i: w.add_related(i, ["cat"]),
    "add_intents": lambda w, i: w.add_intents(i, ["do it"]),
}


def test_writes_before_enter_raise_value_error(tmp_path: Path) -> None:
    writer = IndexWriter(tmp_path / "index.db")

    with pytest.raises(ValueError, match="index writer is not open"):
        writer.add_entry(new_entry())
    with pytest.raises(ValueError, match="index writer is not open"):
        writer.set_meta("k", "v")


def test_writes_after_exit_raise_value_error(tmp_path: Path) -> None:
    writer = IndexWriter(tmp_path / "index.db")
    with writer:
        writer.add_entry(new_entry())

    with pytest.raises(ValueError, match="index writer is not open"):
        writer.add_entry(new_entry("other"))
    with pytest.raises(ValueError, match="index writer is not open"):
        ADDERS["add_alias"](writer, 1)


# 6. unknown entry id


@pytest.mark.parametrize("method", sorted(ADDERS))
def test_child_methods_reject_unknown_entry_id(tmp_path: Path, method: str) -> None:
    with IndexWriter(tmp_path / "index.db") as writer, pytest.raises(IngestError) as caught:
        ADDERS[method](writer, 99)

    assert caught.value.message == "unknown entry id: 99"


# 7. repeated lists, aliases, empty sequences


def test_second_add_sections_raises_ingest_error(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        entry_id = writer.add_entry(new_entry())
        writer.add_sections(entry_id, [Section("A", "a", 0)])
        with pytest.raises(IngestError) as caught:
            writer.add_sections(entry_id, [Section("A", "a", 0)])

    assert caught.value.message == f"cannot write index: {tmp_path / 'index.db'}"


def test_second_add_examples_raises_ingest_error(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        entry_id = writer.add_entry(new_entry())
        writer.add_examples(entry_id, [example("ls-a")])
        with pytest.raises(IngestError, match="cannot write index"):
            writer.add_examples(entry_id, [example("ls-b")])


def test_duplicate_alias_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        entry_id = writer.add_entry(new_entry())
        writer.add_alias(entry_id, "dir")
        writer.add_alias(entry_id, "dir")

    assert rows(path, "SELECT * FROM alias") == [(1, "dir")]


def test_empty_sequences_insert_nothing(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        entry_id = writer.add_entry(new_entry())
        writer.add_sections(entry_id, [])
        writer.add_examples(entry_id, [])
        writer.add_subcommands(entry_id, [])
        writer.add_notes(entry_id, [])
        writer.add_related(entry_id, [])
        writer.add_intents(entry_id, [])
        writer.add_intents(entry_id, ["after empty"])

    for table in ("doc_section", "example", "subcommand", "note", "related"):
        assert rows(path, f"SELECT COUNT(*) FROM {table}") == [(0,)]  # noqa: S608 - fixed names
    assert rows(path, "SELECT text FROM intent") == [("after empty",)]


def test_unencodable_text_raises_ingest_error(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        entry_id = writer.add_entry(new_entry())
        with pytest.raises(IngestError) as caught:
            writer.add_notes(entry_id, [Note("macos", "bad \ud800")])

    assert caught.value.message == f"cannot write index: {path}"
    assert isinstance(caught.value.__cause__, UnicodeEncodeError)
    assert rows(path, "SELECT COUNT(*) FROM note") == [(0,)]


def write_after_close(path: Path) -> None:
    """Close the writer's connection behind its back, then write."""
    with IndexWriter(path) as writer:
        writer._conn.close()  # type: ignore[union-attr]  # open inside `with`
        writer.set_meta("k", "v")


def test_other_sqlite_error_in_write_raises_ingest_error(tmp_path: Path) -> None:
    path = tmp_path / "index.db"

    with pytest.raises(IngestError) as caught:
        write_after_close(path)

    assert caught.value.message == f"cannot write index: {path}"
    assert isinstance(caught.value.__cause__, sqlite3.ProgrammingError)


def test_add_entry_ids_stay_dense_after_failed_duplicate(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        writer.add_entry(new_entry("a"))
        with pytest.raises(IngestError):
            writer.add_entry(new_entry("a"))
        assert writer.add_entry(new_entry("b")) == 2


# 8. NewEntry invariants


@pytest.mark.parametrize("name", ["", " ", "a b", "a\tb"])
def test_new_entry_rejects_bad_name(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        new_entry(name)


@pytest.mark.parametrize("section", ["", "1 x"])
def test_new_entry_rejects_bad_section(section: str) -> None:
    with pytest.raises(ValueError, match="section"):
        new_entry(section=section)


def test_new_entry_rejects_plain_string_kind() -> None:
    with pytest.raises(ValueError, match="kind"):
        new_entry(kind="executable")


def test_new_entry_rejects_plain_string_origin() -> None:
    with pytest.raises(ValueError, match="origin"):
        new_entry(origin="macos")


def test_new_entry_rejects_negative_rank() -> None:
    with pytest.raises(ValueError, match="rank"):
        new_entry(rank=-1)


def test_new_entry_defaults() -> None:
    entry = new_entry()

    assert entry.rank == 0
    assert entry.explain == ""
    assert entry.section is None


# 9. invalid texts


@pytest.mark.parametrize("alias", ["", " ", "a b"])
def test_add_alias_rejects_non_name(tmp_path: Path, alias: str) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        entry_id = writer.add_entry(new_entry())
        with pytest.raises(ValueError, match="alias"):
            writer.add_alias(entry_id, alias)


def test_add_related_rejects_non_name(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        entry_id = writer.add_entry(new_entry())
        with pytest.raises(ValueError, match="related"):
            writer.add_related(entry_id, ["cat", "a b"])


@pytest.mark.parametrize("text", ["", "   ", "a\nb", "a\rb", "a\u2028b"])
def test_add_intents_rejects_blank_or_multiline(tmp_path: Path, text: str) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        entry_id = writer.add_entry(new_entry())
        with pytest.raises(ValueError, match="intent"):
            writer.add_intents(entry_id, ["fine", text])


def test_invalid_related_inserts_nothing(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        entry_id = writer.add_entry(new_entry())
        with pytest.raises(ValueError, match="related"):
            writer.add_related(entry_id, ["cat", "a b"])

    assert rows(path, "SELECT COUNT(*) FROM related") == [(0,)]


# 10. meta


def test_set_meta_replaces_existing_key(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        writer.set_meta("k", "one")
        writer.set_meta("k", "two")

    assert rows(path, "SELECT key, value FROM meta") == [("k", "two")]


@pytest.mark.parametrize("key", ["", "  "])
def test_set_meta_rejects_blank_key(tmp_path: Path, key: str) -> None:
    with IndexWriter(tmp_path / "index.db") as writer, pytest.raises(ValueError, match="key"):
        writer.set_meta(key, "v")


# 11. schema


def test_schema_has_fts5_table_and_unique_index(tmp_path: Path) -> None:
    path = build_index(tmp_path / "index.db")

    sql = dict(rows(path, "SELECT name, sql FROM sqlite_master WHERE sql != ''"))

    assert "USING fts5" in sql["search_fts"]
    assert "entry_key" in sql
    assert {"entry_name_rank", "alias_alias", "content_item", "intent", "meta"} <= set(sql)


def test_schema_version_is_last_migration_number() -> None:
    numbers = sorted(
        int(item.name[:4])
        for item in files("leva.store").joinpath("migrations").iterdir()
        if item.name.endswith(".sql")
    )

    assert numbers == list(range(1, len(numbers) + 1))
    assert numbers[-1] == SCHEMA_VERSION
    assert len(load_migrations()) == SCHEMA_VERSION


def test_order_migrations_sorts_by_number() -> None:
    assert order_migrations({"0002_b.sql": "B;", "0001_a.sql": "A;"}) == ("A;", "B;")


@pytest.mark.parametrize(
    "names",
    [
        ["0002_b.sql"],
        ["0001_a.sql", "0003_c.sql"],
        ["0001_a.sql", "0001_b.sql"],
        ["init.sql"],
        ["0001-a.sql"],
        [],
    ],
)
def test_order_migrations_rejects_bad_names(names: list[str]) -> None:
    with pytest.raises(ValueError, match="migration"):
        order_migrations(dict.fromkeys(names, ""))


# 12. open_readonly


def test_open_readonly_returns_working_connection(tmp_path: Path) -> None:
    path = build_index(tmp_path / "index.db")

    with closing(open_readonly(path)) as conn:
        assert conn.execute("SELECT name FROM entry").fetchall() == [("ls",)]


def test_open_readonly_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "nope.db"

    with pytest.raises(IndexUnavailableError) as caught:
        open_readonly(path)

    assert caught.value.message == f"index missing: {path}"
    assert caught.value.hint == REBUILD_HINT


def test_open_readonly_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(IndexUnavailableError) as caught:
        open_readonly(tmp_path)

    assert caught.value.message == f"index missing: {tmp_path}"


def test_open_readonly_rejects_garbage_file(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    path.write_bytes(b"this is not a database" * 50)

    with pytest.raises(IndexUnavailableError) as caught:
        open_readonly(path)

    assert caught.value.message == f"index unreadable: {path}"
    assert caught.value.hint == REBUILD_HINT
    assert isinstance(caught.value.__cause__, sqlite3.Error)


def test_open_readonly_rejects_file_without_read_permission(tmp_path: Path) -> None:
    path = build_index(tmp_path / "index.db")
    path.chmod(0o000)

    try:
        with pytest.raises(IndexUnavailableError) as caught:
            open_readonly(path)
    finally:
        path.chmod(0o600)

    assert caught.value.message == f"index unreadable: {path}"
    assert isinstance(caught.value.__cause__, sqlite3.Error)


def test_open_readonly_rejects_file_in_unsearchable_directory(tmp_path: Path) -> None:
    folder = tmp_path / "locked"
    folder.mkdir()
    path = build_index(folder / "index.db")
    folder.chmod(0o000)

    try:
        with pytest.raises(IndexUnavailableError) as caught:
            open_readonly(path)
    finally:
        folder.chmod(0o700)

    assert caught.value.message == f"index unreadable: {path}"
    assert caught.value.hint == REBUILD_HINT
    assert isinstance(caught.value.__cause__, OSError)


@pytest.mark.parametrize("version", [0, 2])
def test_open_readonly_rejects_other_schema_version(tmp_path: Path, version: int) -> None:
    path = tmp_path / "index.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE t (a)")
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()

    with pytest.raises(IndexUnavailableError) as caught:
        open_readonly(path)

    assert caught.value.message == f"index schema {version} is not {SCHEMA_VERSION}: {path}"
    assert caught.value.hint == REBUILD_HINT


def test_open_readonly_accepts_path_with_special_characters(tmp_path: Path) -> None:
    folder = tmp_path / "a b#c%d"
    folder.mkdir()
    path = build_index(folder / "index.db")

    with closing(open_readonly(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM entry").fetchone() == (1,)


def test_open_readonly_connection_rejects_writes(tmp_path: Path) -> None:
    path = build_index(tmp_path / "index.db")

    with closing(open_readonly(path)) as conn, pytest.raises(sqlite3.OperationalError) as caught:
        conn.execute("DELETE FROM entry")

    assert "readonly" in str(caught.value)


def test_open_readonly_accepts_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_index(tmp_path / "index.db")
    monkeypatch.chdir(tmp_path)

    with closing(open_readonly(Path("index.db"))) as conn:
        assert conn.execute("SELECT COUNT(*) FROM entry").fetchone() == (1,)


# 13. DDL failure


def test_invalid_migration_raises_ingest_error_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("leva.store._writer.load_migrations", lambda: ("CREATE TABLE x (",))
    path = tmp_path / "index.db"

    with pytest.raises(IngestError) as caught, IndexWriter(path):
        pass

    assert caught.value.message == f"cannot write index: {path}"
    assert isinstance(caught.value.__cause__, sqlite3.Error)
    assert re.search(r"incomplete input|syntax error", str(caught.value.__cause__))


def test_unreadable_migrations_create_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> tuple[str, ...]:
        raise ValueError("bad migration series")

    monkeypatch.setattr("leva.store._writer.load_migrations", fail)
    path = tmp_path / "index.db"

    with pytest.raises(ValueError, match="bad migration series"), IndexWriter(path):
        pass

    assert not path.exists()


def commit_inside(path: Path) -> None:
    """End the writer's transaction early, so the commit at exit finds none to commit."""
    with IndexWriter(path) as writer:
        writer.add_entry(new_entry())
        writer._conn.execute("COMMIT")  # type: ignore[union-attr]  # open inside `with`


def test_failed_commit_raises_ingest_error(tmp_path: Path) -> None:
    path = tmp_path / "index.db"

    with pytest.raises(IngestError) as caught:
        commit_inside(path)

    assert caught.value.message == f"cannot write index: {path}"
    assert isinstance(caught.value.__cause__, sqlite3.Error)
