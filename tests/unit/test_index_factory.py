"""Tests for the fixture index factory (``tests/support/index_factory.py``)."""

from __future__ import annotations

import dataclasses
import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

import pytest

from leva.store import SCHEMA_VERSION, open_readonly
from tests.support.index_factory import (
    FIXED_BUILT_AT,
    FIXTURE_JSON,
    build_fixture_index,
    load_fixture,
)

PLAN_NAMES = [
    *("ls", "tar", "grep", "find", "sed", "du", "df", "chmod", "curl"),
    *("pbcopy", "open", "ditto", "unzip", "zip", "gzip", "kill", "pkill", "ps"),
    *("git", "git-commit", "git-log", "diskutil", "brew"),
    *("echo", "cd", "test", "bat", "sync", "rm"),
]


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    with closing(open_readonly(path)) as conn:
        yield conn


def scalar(path: Path, sql: str, *args: object) -> Any:
    with connect(path) as conn:
        row = conn.execute(sql, args).fetchone()
    return None if row is None else row[0]


def rows(path: Path, sql: str, *args: object) -> list[tuple[Any, ...]]:
    with connect(path) as conn:
        return conn.execute(sql, args).fetchall()


def entry_ranks(path: Path, name: str) -> dict[tuple[str | None, str], int]:
    found = rows(path, "SELECT section, origin, rank FROM entry WHERE name = ?", name)
    return {(section, origin): rank for section, origin, rank in found}


def test_fixture_index_builds_and_matches_json(fixture_index: Path) -> None:
    count = len(load_fixture().entries)
    assert 55 <= count <= 65
    assert scalar(fixture_index, "PRAGMA user_version") == SCHEMA_VERSION
    assert scalar(fixture_index, "SELECT COUNT(*) FROM entry") == count


def test_plan_names_present(fixture_index: Path) -> None:
    present = {r[0] for r in rows(fixture_index, "SELECT DISTINCT name FROM entry")}
    assert set(PLAN_NAMES) <= present


def test_echo_cd_test_bat_shapes(fixture_index: Path) -> None:
    assert entry_ranks(fixture_index, "echo") == {
        ("1", "macos"): 0,
        (None, "zsh"): 1,
        (None, "bash"): 2,
    }
    assert entry_ranks(fixture_index, "cd") == {(None, "zsh"): 0, (None, "bash"): 1}
    builtin = rows(
        fixture_index, "SELECT kind, has_man, id FROM entry WHERE name = 'echo' AND origin = 'zsh'"
    )[0]
    assert builtin[:2] == ("builtin", 1)
    headings = [
        r[0]
        for r in rows(
            fixture_index,
            "SELECT heading FROM doc_section WHERE entry_id = ? ORDER BY ord",
            builtin[2],
        )
    ]
    assert headings == ["SYNOPSIS", "DESCRIPTION"]
    owner = scalar(
        fixture_index,
        "SELECT e.name FROM alias a JOIN entry e ON e.id = a.entry_id WHERE a.alias = '['",
    )
    assert owner == "test"
    bat = rows(
        fixture_index,
        "SELECT has_man, summary, kind, origin, section, id FROM entry WHERE name = 'bat'",
    )
    assert [r[:5] for r in bat] == [(0, "", "executable", "homebrew", None)]
    assert (
        scalar(fixture_index, "SELECT COUNT(*) FROM doc_section WHERE entry_id = ?", bat[0][5]) == 0
    )


def test_known_aliases(fixture_index: Path) -> None:
    sql = (
        "SELECT a.alias FROM alias a JOIN entry e ON e.id = a.entry_id"
        " WHERE e.name = ? ORDER BY a.alias"
    )
    assert [r[0] for r in rows(fixture_index, sql, "gzip")] == ["gunzip", "zcat"]
    assert [r[0] for r in rows(fixture_index, sql, "grep")] == ["egrep", "fgrep"]


def test_sync_in_two_sections(fixture_index: Path) -> None:
    assert entry_ranks(fixture_index, "sync") == {("1", "macos"): 0, ("8", "macos"): 1}


def section_order(section: str | None) -> int:
    if section == "1":
        return 0
    if section == "8":
        return 1
    return 2 if section is not None else 3


def d005_key(row: tuple[Any, ...]) -> tuple[Any, ...]:
    entry_id, section, kind, origin, has_man, curated = row
    return (
        not curated,
        not has_man,
        section_order(section),
        kind == "builtin",
        origin == "bash",
        entry_id,
    )


def test_ranks_follow_d005_for_every_name(fixture_index: Path) -> None:
    found = rows(
        fixture_index,
        "SELECT name, id, section, kind, origin, has_man, curated, rank FROM entry",
    )
    by_name: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for name, *rest in found:
        by_name[name].append(tuple(rest))
    for name, group in by_name.items():
        expected = sorted(group, key=lambda r: d005_key(r[:6]))
        ranks = [r[6] for r in expected]
        assert ranks == list(range(len(group))), name


def dedup_key(cmd: str) -> str:
    return re.sub(r"\{\{.*?\}\}", "{}", " ".join(cmd.split()))


def test_examples_danger_and_tldr_duplicate(fixture_index: Path) -> None:
    assert scalar(fixture_index, "SELECT COUNT(*) FROM example WHERE danger IS NOT NULL") >= 2
    tar = rows(
        fixture_index,
        "SELECT x.source, x.cmd FROM example x JOIN entry e ON e.id = x.entry_id"
        " WHERE e.name = 'tar'",
    )
    curated = {dedup_key(cmd) for source, cmd in tar if source == "curated"}
    tldr = {dedup_key(cmd) for source, cmd in tar if source == "tldr"}
    assert curated & tldr


def test_tldr_examples_are_unverified_with_numbered_ids(fixture_index: Path) -> None:
    found = rows(
        fixture_index,
        "SELECT e.name, x.id, x.verified, x.ord FROM example x JOIN entry e ON e.id = x.entry_id"
        " WHERE x.source = 'tldr' ORDER BY e.id, x.ord",
    )
    assert found
    counters: dict[str, int] = defaultdict(int)
    for name, example_id, verified, _ in found:
        counters[name] += 1
        assert verified == "none"
        assert example_id == f"{name}-tldr-{counters[name]}"
    assert any(
        r[0] == "ps"
        for r in rows(
            fixture_index,
            "SELECT e.name, e.curated FROM example x JOIN entry e ON e.id = x.entry_id"
            " WHERE x.source = 'tldr' AND e.curated = 0",
        )
    )


def test_tar_intents_keep_json_order(fixture_index: Path) -> None:
    texts = [
        r[0]
        for r in rows(
            fixture_index,
            "SELECT i.text FROM intent i JOIN entry e ON e.id = i.entry_id"
            " WHERE e.name = 'tar' ORDER BY i.ord",
        )
    ]
    tar = next(e for e in load_fixture().entries if e.entry.name == "tar")
    assert texts == list(tar.intents)
    assert texts[:3] == ["compress a folder", "extract an archive", "list archive contents"]


def test_find_has_long_section_with_long_line(fixture_index: Path) -> None:
    bodies = [
        r[0]
        for r in rows(
            fixture_index,
            "SELECT s.body FROM doc_section s JOIN entry e ON e.id = s.entry_id"
            " WHERE e.name = 'find'",
        )
    ]
    lines = max((b.split("\n") for b in bodies), key=len)
    assert len(lines) >= 120
    assert any(len(line) > 80 for line in lines)


def test_fts_has_one_row_per_entry(fixture_index: Path) -> None:
    assert scalar(fixture_index, "SELECT COUNT(*) FROM search_fts") == scalar(
        fixture_index, "SELECT COUNT(*) FROM entry"
    )


def test_build_is_deterministic(tmp_path: Path) -> None:
    first = build_fixture_index(tmp_path / "a" / "index.db")
    second = build_fixture_index(tmp_path / "b" / "index.db")
    sql = "SELECT value FROM meta WHERE key = ?"
    assert scalar(first, sql, "index_digest") == scalar(second, sql, "index_digest")
    assert scalar(first, sql, "built_at") == "2026-01-01T00:00:00+00:00"
    assert FIXED_BUILT_AT.isoformat() == "2026-01-01T00:00:00+00:00"


def test_json_is_sorted_and_unique() -> None:
    keys = [
        (e.entry.name, e.entry.section or "", e.entry.origin.value) for e in load_fixture().entries
    ]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))


def write_json(tmp_path: Path, mutate: Any) -> Path:
    data = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    mutate(data)
    target = tmp_path / "bad.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


def test_load_rejects_unknown_entry_key(tmp_path: Path) -> None:
    path = write_json(tmp_path, lambda d: d["entries"][0].update(sumary="typo"))
    with pytest.raises(ValueError, match=r"sumary"):
        load_fixture(path)


def test_load_rejects_unknown_example_key(tmp_path: Path) -> None:
    def mutate(data: dict[str, Any]) -> None:
        target = next(e for e in data["entries"] if e.get("examples"))
        target["examples"][0]["comand"] = "typo"

    with pytest.raises(ValueError, match=r"comand"):
        load_fixture(write_json(tmp_path, mutate))


def test_load_rejects_missing_required_key(tmp_path: Path) -> None:
    path = write_json(tmp_path, lambda d: d["entries"][0].pop("summary"))
    with pytest.raises(ValueError, match=r"summary"):
        load_fixture(path)


def test_load_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    path = write_json(tmp_path, lambda d: d.update(extra=1))
    with pytest.raises(ValueError, match=r"extra"):
        load_fixture(path)


def test_load_rejects_unknown_section_and_subcommand_keys(tmp_path: Path) -> None:
    def section(data: dict[str, Any]) -> None:
        target = next(e for e in data["entries"] if e.get("sections"))
        target["sections"][0]["title"] = "typo"

    def subcommand(data: dict[str, Any]) -> None:
        target = next(e for e in data["entries"] if e.get("subcommands"))
        target["subcommands"][0]["kind"] = "typo"

    with pytest.raises(ValueError, match=r"title"):
        load_fixture(write_json(tmp_path, section))
    with pytest.raises(ValueError, match=r"kind"):
        load_fixture(write_json(tmp_path, subcommand))


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("summary", None, ": 'summary' must be a string"),
        ("has_man", "false", ": 'has_man' must be a boolean"),
        ("rank", "0", ": 'rank' must be an integer"),
        ("rank", True, ": 'rank' must be an integer"),
        ("aliases", "zcat", ": 'aliases' must be a list"),
        ("intents", [1], ": 'intents' must be a list of strings"),
        ("sections", [{"heading": "NAME", "body": 3}], " section 0: 'body' must be a string"),
        ("examples", ["ls -l"], " examples: expected an object"),
    ],
)
def test_load_rejects_wrong_value_types(
    tmp_path: Path, key: str, value: object, message: str
) -> None:
    path = write_json(tmp_path, lambda d: d["entries"][0].update({key: value}))
    with pytest.raises(ValueError, match=re.escape(f"entry awk{message}")):
        load_fixture(path)


def test_load_rejects_non_string_meta_value(tmp_path: Path) -> None:
    path = write_json(tmp_path, lambda d: d["meta"].update(leva_version=1))
    with pytest.raises(ValueError, match=r"meta: 'leva_version' must be a string"):
        load_fixture(path)


def test_load_joins_body_lines(tmp_path: Path) -> None:
    def mutate(data: dict[str, Any]) -> None:
        data["entries"][0]["sections"] = [{"heading": "NAME", "body": ["one", "two"]}]

    data = load_fixture(write_json(tmp_path, mutate))
    assert data.entries[0].sections[0].body == "one\ntwo"
    assert data.entries[0].sections[0].ord == 0


def test_build_with_modified_data_writes_that_data(tmp_path: Path) -> None:
    data = load_fixture()
    smaller = dataclasses.replace(data, entries=data.entries[1:])
    target = build_fixture_index(tmp_path / "x" / "index.db", smaller)
    assert scalar(target, "SELECT COUNT(*) FROM entry") == len(data.entries) - 1


def test_attribution_meta_is_set(fixture_index: Path) -> None:
    value = scalar(fixture_index, "SELECT value FROM meta WHERE key = 'attribution'")
    assert value.strip()
    assert "tldr-pages" in value
    assert "CC BY 4.0" in value
