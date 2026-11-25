"""Tests for `IndexWriter.finalize`: FTS rows, meta, digest, integrity and writer state."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from leva.model import Example, IngestError, Kind, Note, Origin, Section, Subcommand
from leva.store import SCHEMA_VERSION, IndexWriter, NewEntry, open_readonly
from leva.store._finalize import check_integrity

BUILT_AT = datetime(2026, 1, 1, tzinfo=UTC)


def entry(name: str, summary: str = "", **fields: Any) -> NewEntry:
    """Return a valid `NewEntry` with the given name and summary."""
    values: dict[str, Any] = {
        "section": None,
        "kind": Kind.EXECUTABLE,
        "origin": Origin.MACOS,
        "path": None,
        "has_man": False,
        "curated": False,
    }
    values.update(fields)
    return NewEntry(name=name, summary=summary, **values)


def populate(
    writer: IndexWriter,
    *,
    summary: str = "List files.",
    alias: str = "dir",
    body: str = "Lists the contents of directories.",
    danger: str | None = None,
    note: str = "a note",
    sub_body: str = "sub body",
    related: str = "cat",
    intents: tuple[str, ...] = ("list files", "show folder"),
    meta: dict[str, str] | None = None,
) -> None:
    """Write four entries; the first one carries every kind of child row."""
    first = writer.add_entry(entry("ls", summary, section="1", has_man=True, explain="Explain."))
    writer.add_alias(first, alias)
    writer.add_alias(first, "vdir")
    writer.add_sections(first, [Section("NAME", "ls - list", 0), Section("DESCRIPTION", body, 1)])
    writer.add_examples(first, [Example("ls-a", "all", "ls -a", "curated", "exec", danger)])
    writer.add_subcommands(first, [Subcommand("sub", "A sub.", None, "hyphen", sub_body)])
    writer.add_notes(first, [Note("macos", note)])
    writer.add_related(first, [related])
    writer.add_intents(first, list(intents))
    writer.add_entry(entry("cat", "Concatenate and print files."))
    writer.add_entry(entry("find", "Walk a directory tree."))
    writer.add_entry(entry("tar", "Archive utility.", origin=Origin.HOMEBREW))
    for key, value in (meta or {}).items():
        writer.set_meta(key, value)


def write_index(path: Path, built_at: datetime = BUILT_AT, **options: Any) -> str:
    """Write a populated, finalized index and return the digest."""
    with IndexWriter(path) as writer:
        populate(writer, **options)
        return writer.finalize(built_at=built_at)


def query(path: Path, sql: str, *params: object) -> list[tuple[Any, ...]]:
    """Run a query on the file at `path` and return every row."""
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(sql, params).fetchall()


def meta(path: Path) -> dict[str, str]:
    """Return the meta table of the file at `path`."""
    return dict(query(path, "SELECT key, value FROM meta"))


def match(path: Path, expression: str) -> list[int]:
    """Return the rowids matching an FTS5 expression, in rowid order."""
    sql = "SELECT rowid FROM search_fts WHERE search_fts MATCH ? ORDER BY rowid"
    return [row[0] for row in query(path, sql, expression)]


# 1. meta


def test_finalize_writes_meta_and_returns_digest(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    digest = write_index(path)

    stored = meta(path)
    assert stored["schema_version"] == str(SCHEMA_VERSION) == "1"
    assert stored["built_at"] == "2026-01-01T00:00:00+00:00"
    assert re.fullmatch(r"[0-9a-f]{64}", stored["index_digest"])
    assert stored["index_digest"] == digest


def test_finalize_converts_built_at_to_utc(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    local = datetime(2026, 1, 1, 12, 30, 45, 999, tzinfo=timezone(timedelta(hours=2)))
    write_index(path, built_at=local)

    assert meta(path)["built_at"] == "2026-01-01T10:30:45+00:00"


# 2. determinism


def test_digest_is_independent_of_built_at(tmp_path: Path) -> None:
    first = write_index(tmp_path / "a.db", built_at=BUILT_AT)
    second = write_index(tmp_path / "b.db", built_at=BUILT_AT + timedelta(days=40, seconds=7))

    assert first == second
    assert meta(tmp_path / "a.db")["built_at"] != meta(tmp_path / "b.db")["built_at"]


# 3. sensitivity


@pytest.mark.parametrize(
    "change",
    [
        {"summary": "Other summary."},
        {"alias": "other"},
        {"body": "Another body."},
        {"danger": "removes files"},
        {"note": "another note"},
        {"sub_body": "other sub body"},
        {"related": "find"},
        {"intents": ("show folder", "list files")},
        {"meta": {"content_version": "abc"}},
    ],
    ids=[
        "summary",
        "alias",
        "section-body",
        "example-danger",
        "note",
        "subcommand-body",
        "related",
        "intent-order",
        "extra-meta",
    ],
)
def test_digest_changes_when_content_changes(tmp_path: Path, change: dict[str, Any]) -> None:
    base = write_index(tmp_path / "base.db")
    changed = write_index(tmp_path / "changed.db", **change)

    assert changed != base


# 4. recipe pin


DIGEST_TABLES = (
    "meta",
    "entry",
    "alias",
    "doc_section",
    "example",
    "note",
    "subcommand",
    "related",
    "intent",
    "content_item",
)


def recipe_digest(rows: dict[str, list[list[Any]]]) -> str:
    """Hash the rows by hand as D-048 describes: a `#table` line, then one JSON line per row."""
    text = ""
    for table in DIGEST_TABLES:
        text += f"#{table}\n"
        for row in rows.get(table, []):
            text += json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_digest_follows_the_documented_recipe(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        writer.add_entry(entry("ls", "List files.", section="1", path="/bin/ls", has_man=True))
        digest = writer.finalize(built_at=BUILT_AT)

    assert digest == recipe_digest(
        {
            "meta": [["schema_version", "1"]],
            "entry": [[1, "ls", "1", "executable", "macos", "List files.", "/bin/ls", 1, 0, "", 0]],
        }
    )


def test_digest_recipe_covers_every_child_table(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        first = writer.add_entry(
            entry(
                "ls",
                "List files.",
                section="1",
                path="/bin/ls",
                has_man=True,
                curated=True,
                explain="Explain.",
                rank=3,
            )
        )
        writer.add_alias(first, "vdir")
        writer.add_alias(first, "dir")
        writer.add_sections(first, [Section("NAME", "ls - list", 0), Section("BODY", "ünï", 1)])
        writer.add_examples(
            first,
            [
                Example("ls-a", "all", "ls -a", "curated", "exec", "removes nothing"),
                Example("ls-b", "b", "ls -b", "tldr", "none"),
            ],
        )
        writer.add_subcommands(
            first,
            [
                Subcommand("sub", "A sub.", None, "hyphen", "sub body"),
                Subcommand("c", "C", "cat", "hyphen", "body"),
            ],
        )
        writer.add_notes(first, [Note("macos", "a note")])
        writer.add_related(first, ["cat", "find"])
        writer.add_intents(first, ["list files", "show folder"])
        writer.set_meta("content_version", "abc")
        digest = writer.finalize(built_at=BUILT_AT)

    assert digest == recipe_digest(
        {
            "meta": [["content_version", "abc"], ["schema_version", "1"]],
            "entry": [
                [1, "ls", "1", "executable", "macos", "List files.", "/bin/ls", 1, 1, "Explain.", 3]
            ],
            "alias": [[1, "dir"], [1, "vdir"]],
            "doc_section": [[1, 0, "NAME", "ls - list"], [1, 1, "BODY", "ünï"]],
            "example": [
                [1, 0, "ls-a", "all", "ls -a", "curated", "exec", "removes nothing"],
                [1, 1, "ls-b", "b", "ls -b", "tldr", "none", None],
            ],
            "subcommand": [
                [1, 0, "sub", "A sub.", None, "hyphen", "sub body"],
                [1, 1, "c", "C", "cat", "hyphen", "body"],
            ],
            "note": [[1, 0, "macos", "a note"]],
            "related": [[1, 0, "cat"], [1, 1, "find"]],
            "intent": [[1, 0, "list files"], [1, 1, "show folder"]],
        }
    )


# 5. FTS


@pytest.mark.parametrize(
    ("expression", "rowid"),
    [
        ("vdir", 1),
        ("folder", 1),
        ("concatenate", 2),
        ("directories", 1),
        ("tree", 3),
        ("ls", 1),
    ],
    ids=["alias", "intent", "summary", "body", "summary-other", "name"],
)
def test_fts_finds_entry_by_each_column(tmp_path: Path, expression: str, rowid: int) -> None:
    path = tmp_path / "index.db"
    write_index(path)

    assert match(path, expression) == [rowid]


def test_fts_does_not_index_section_headings(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    write_index(path)

    assert match(path, "description") == []
    assert match(path, "name") == []


def test_fts_has_one_row_per_entry_including_childless_ones(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    write_index(path)

    assert query(path, "SELECT COUNT(*) FROM search_fts_docsize") == [(4,)]
    assert match(path, "archive") == [4]


# 6. bm25


def test_bm25_ranks_name_hit_above_body_hit(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        named = writer.add_entry(entry("zeta", "Short."))
        in_body = writer.add_entry(entry("other", "Short."))
        writer.add_sections(in_body, [Section("DESCRIPTION", "uses zeta internally", 0)])
        for index in range(6):
            writer.add_entry(entry(f"filler{index}", "Filler words only."))
        writer.finalize(built_at=BUILT_AT)

    sql = (
        "SELECT rowid, bm25(search_fts, 10.0, 5.0, 2.0, 1.0) AS score FROM search_fts"
        " WHERE search_fts MATCH 'zeta' ORDER BY score"
    )
    ranked = [row[0] for row in query(path, sql)]
    assert ranked == [named, in_body]


# 7. integrity and ANALYZE


def test_finalized_index_passes_integrity_check_and_is_analyzed(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    write_index(path)

    conn = open_readonly(path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert conn.execute("SELECT COUNT(*) FROM sqlite_stat1").fetchone()[0] > 0
    finally:
        conn.close()


# 8. writer state


def test_finalize_twice_raises(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        writer.finalize(built_at=BUILT_AT)
        with pytest.raises(ValueError, match="index writer is already finalized"):
            writer.finalize(built_at=BUILT_AT)


def test_writes_after_finalize_raise(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        entry_id = writer.add_entry(entry("ls"))
        writer.finalize(built_at=BUILT_AT)
        with pytest.raises(ValueError, match="index writer is already finalized"):
            writer.add_entry(entry("cat"))
        with pytest.raises(ValueError, match="index writer is already finalized"):
            writer.add_alias(entry_id, "dir")
        with pytest.raises(ValueError, match="index writer is already finalized"):
            writer.set_meta("key", "value")


def test_exit_after_finalize_still_commits(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        writer.add_entry(entry("ls"))
        writer.finalize(built_at=BUILT_AT)

    assert query(path, "SELECT name FROM entry") == [("ls",)]


def test_finalize_outside_with_raises(tmp_path: Path) -> None:
    writer = IndexWriter(tmp_path / "index.db")

    with pytest.raises(ValueError, match="index writer is not open"):
        writer.finalize(built_at=BUILT_AT)


def test_finalize_after_exit_raises(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        pass

    with pytest.raises(ValueError, match="index writer is not open"):
        writer.finalize(built_at=BUILT_AT)


def test_finalize_rejects_naive_built_at(tmp_path: Path) -> None:
    with IndexWriter(tmp_path / "index.db") as writer:
        with pytest.raises(ValueError, match="built_at must be timezone-aware"):
            writer.finalize(built_at=datetime(2026, 1, 1))
        writer.finalize(built_at=BUILT_AT)


# 9. rollback


def fail_after_finalize(path: Path) -> None:
    """Finalize an index, then raise inside the `with` block."""
    with IndexWriter(path) as writer:
        writer.add_entry(entry("ls"))
        writer.finalize(built_at=BUILT_AT)
        raise RuntimeError("boom")


def test_exception_after_finalize_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with pytest.raises(RuntimeError, match="boom"):
        fail_after_finalize(path)

    assert query(path, "PRAGMA user_version") == [(0,)]
    assert query(path, "SELECT name FROM sqlite_master") == []


# 10. integrity failure


def test_check_integrity_accepts_ok_row(tmp_path: Path) -> None:
    check_integrity([("ok",)], tmp_path / "index.db")


@pytest.mark.parametrize(
    "result",
    [[], [("ok",), ("ok",)], [("row 3 missing from index x",)], [("*** in database main ***",)]],
    ids=["empty", "two-rows", "message", "banner"],
)
def test_check_integrity_rejects_anything_but_one_ok_row(
    tmp_path: Path, result: list[tuple[str]]
) -> None:
    path = tmp_path / "index.db"

    with pytest.raises(IngestError) as caught:
        check_integrity(result, path)

    assert caught.value.message == f"index integrity check failed: {path}"


def test_finalize_maps_sqlite_error_and_stays_unfinalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "index.db"

    def broken(conn: sqlite3.Connection, path: Path, built_at: datetime) -> str:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr("leva.store._writer.finalize_index", broken)
    with IndexWriter(path) as writer:
        with pytest.raises(IngestError) as caught:
            writer.finalize(built_at=BUILT_AT)
        writer.set_meta("still", "writable")

    assert caught.value.message == f"cannot write index: {path}"
    assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
    assert meta(path) == {"still": "writable"}


# 11. empty index


def test_empty_index_finalizes(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with IndexWriter(path) as writer:
        digest = writer.finalize(built_at=BUILT_AT)

    assert query(path, "SELECT COUNT(*) FROM search_fts_docsize") == [(0,)]
    assert meta(path)["index_digest"] == digest
    assert set(meta(path)) == {"schema_version", "built_at", "index_digest"}
