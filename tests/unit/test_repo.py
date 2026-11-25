"""Tests for `Repository` against the fixture index."""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from leva.model import IndexUnavailableError, Kind, Origin
from leva.repo import FTS_WEIGHTS, MAX_FTS_TOKENS, FtsHit, IndexStats, NameRow, Repository
from leva.store import open_readonly
from tests.support.index_factory import FixtureData, build_fixture_index, load_fixture

REBUILD_HINT = "run leva --rebuild"


def open_repo(path: Path) -> Repository:
    return Repository(open_readonly(path))


def ids_by_key(data: FixtureData) -> dict[tuple[str, str | None, str], int]:
    """Map ``(name, section, origin)`` to the entry id (ids are 1-based write positions)."""
    return {
        (item.entry.name, item.entry.section, item.entry.origin.value): position
        for position, item in enumerate(data.entries, start=1)
    }


def entry_id(name: str, section: str | None = "1", origin: str = "macos") -> int:
    return ids_by_key(load_fixture())[(name, section, origin)]


@pytest.fixture
def repo(fixture_index: Path) -> Iterator[Repository]:
    repository = open_repo(fixture_index)
    yield repository
    repository.close()


# --- get_entry -------------------------------------------------------------------------------


def test_get_entry_returns_primary_entry_of_a_shared_name(repo: Repository) -> None:
    entry = repo.get_entry("echo")

    assert entry is not None
    assert entry.id == entry_id("echo", "1")
    assert (entry.section, entry.kind, entry.origin) == ("1", Kind.EXECUTABLE, Origin.MACOS)
    assert repo.get_entry("echo", section=None) == entry


def test_get_entry_returns_the_builtin_ranked_first(repo: Repository) -> None:
    entry = repo.get_entry("cd")

    assert entry is not None
    assert entry.id == entry_id("cd", None, "zsh")
    assert (entry.kind, entry.origin) == (Kind.BUILTIN, Origin.ZSH)


def test_get_entry_filters_by_section(repo: Repository) -> None:
    entry = repo.get_entry("sync", "8")

    assert entry is not None
    assert entry.id == entry_id("sync", "8")
    assert entry.section == "8"
    assert repo.get_entry("sync", "1") == repo.get_entry("sync")


def test_get_entry_with_unknown_section_is_none(repo: Repository) -> None:
    assert repo.get_entry("sync", "3") is None


@pytest.mark.parametrize(
    ("alias", "target"), [("[", "test"), ("gunzip", "gzip"), ("egrep", "grep")]
)
def test_get_entry_resolves_an_alias(repo: Repository, alias: str, target: str) -> None:
    entry = repo.get_entry(alias)

    assert entry is not None
    assert entry.name == target


def test_get_entry_alias_respects_section(repo: Repository) -> None:
    assert repo.get_entry("gunzip", "1") is not None
    assert repo.get_entry("gunzip", "8") is None


@pytest.mark.parametrize("name", ["nope", "", "   ", "ls "])
def test_get_entry_returns_none_when_nothing_matches(repo: Repository, name: str) -> None:
    assert repo.get_entry(name) is None


def test_get_entry_converts_columns_to_model_types(repo: Repository) -> None:
    bat = repo.get_entry("bat")
    ls = repo.get_entry("ls")

    assert bat is not None
    assert ls is not None
    assert isinstance(bat.kind, Kind)
    assert isinstance(bat.origin, Origin)
    assert (bat.origin, bat.summary, bat.has_man, bat.curated, bat.section) == (
        Origin.HOMEBREW,
        "",
        False,
        False,
        None,
    )
    assert bat.path is not None
    assert (ls.has_man, ls.curated) == (True, True)
    assert ls.has_man is True
    assert ls.curated is True


def test_get_entry_prefers_name_match_over_alias_match(tmp_path: Path) -> None:
    data = load_fixture()
    gzip = next(item for item in data.entries if item.entry.name == "gzip")
    # `ls` becomes an alias of gzip (ranked 0) while an entry named `ls` exists.
    variant = replace(
        data,
        entries=tuple(
            replace(item, aliases=(*item.aliases, "ls")) if item is gzip else item
            for item in data.entries
        ),
    )
    repository = open_repo(build_fixture_index(tmp_path / "variant.db", variant))
    try:
        entry = repository.get_entry("ls")
    finally:
        repository.close()

    assert entry is not None
    assert entry.name == "ls"


def test_get_entry_alias_ties_resolve_by_rank_name_then_id(tmp_path: Path) -> None:
    data = load_fixture()
    names = {"awk", "cat"}
    variant = replace(
        data,
        entries=tuple(
            replace(item, aliases=("twin",)) if item.entry.name in names else item
            for item in data.entries
        ),
    )
    repository = open_repo(build_fixture_index(tmp_path / "variant.db", variant))
    try:
        entry = repository.get_entry("twin")
    finally:
        repository.close()

    assert entry is not None
    assert entry.name == "awk"


def test_get_entry_by_id_round_trips(repo: Repository) -> None:
    for name in ("ls", "sync", "bat", "cd"):
        entry = repo.get_entry(name)
        assert entry is not None
        assert repo.get_entry_by_id(entry.id) == entry


def test_get_entry_by_id_unknown_is_none(repo: Repository) -> None:
    assert repo.get_entry_by_id(0) is None
    assert repo.get_entry_by_id(10_000) is None


def test_explain_returns_text_for_curated_and_empty_otherwise(repo: Repository) -> None:
    data = load_fixture()
    tar = next(item for item in data.entries if item.entry.name == "tar")

    assert repo.explain(entry_id("tar", "1")) == tar.entry.explain
    assert tar.entry.explain != ""
    assert repo.explain(entry_id("cat", "1")) == ""
    assert repo.explain(10_000) == ""


# --- names -----------------------------------------------------------------------------------


def test_names_has_one_row_per_entry_in_order(repo: Repository) -> None:
    data = load_fixture()
    ids = ids_by_key(data)
    rows = repo.names()

    assert len(rows) == len(data.entries)
    assert all(isinstance(row, NameRow) for row in rows)
    expected = sorted(
        data.entries,
        key=lambda item: (
            item.entry.name,
            item.entry.rank,
            ids[(item.entry.name, item.entry.section, item.entry.origin.value)],
        ),
    )
    assert [row.entry_id for row in rows] == [
        ids[(item.entry.name, item.entry.section, item.entry.origin.value)] for item in expected
    ]


def test_names_rows_carry_entry_fields_aliases_and_intents(repo: Repository) -> None:
    by_id = {row.entry_id: row for row in repo.names()}
    data = load_fixture()

    for position, item in enumerate(data.entries, start=1):
        row = by_id[position]
        assert (row.name, row.section, row.kind, row.origin) == (
            item.entry.name,
            item.entry.section,
            item.entry.kind,
            item.entry.origin,
        )
        assert (row.summary, row.curated) == (item.entry.summary, item.entry.curated)
        assert row.aliases == tuple(sorted(item.aliases))
        assert row.intents == item.intents


def test_names_orders_intents_by_stored_order(repo: Repository) -> None:
    tar = next(row for row in repo.names() if row.name == "tar")

    assert tar.intents == (
        "compress a folder",
        "extract an archive",
        "list archive contents",
        "bundle files into one file",
    )
    assert tar.curated is True


def test_names_sorts_aliases(repo: Repository) -> None:
    gzip = next(row for row in repo.names() if row.name == "gzip")

    assert gzip.aliases == ("gunzip", "zcat")


def test_names_has_no_children_for_plain_entries(repo: Repository) -> None:
    bat = next(row for row in repo.names() if row.name == "bat")

    assert (bat.aliases, bat.intents, bat.summary) == ((), (), "")


# --- children --------------------------------------------------------------------------------


def test_sections_follow_the_fixture_in_order(repo: Repository) -> None:
    data = load_fixture()
    for position, item in enumerate(data.entries, start=1):
        assert repo.sections(position) == list(item.sections)


def test_examples_follow_the_fixture_in_order(repo: Repository) -> None:
    data = load_fixture()
    for position, item in enumerate(data.entries, start=1):
        assert repo.examples(position) == list(item.examples)


def test_examples_carry_danger_only_where_set(repo: Repository) -> None:
    rm = {example.id: example for example in repo.examples(entry_id("rm"))}
    diskutil = {example.id: example for example in repo.examples(entry_id("diskutil", "8"))}

    assert rm["rm-folder"].danger
    assert diskutil["diskutil-erase"].danger
    assert any(example.danger is None for example in repo.examples(entry_id("ls")))
    assert all(example.danger is None for example in repo.examples(entry_id("tar")))


def test_examples_of_tldr_pages_are_unverified(repo: Repository) -> None:
    examples = repo.examples(entry_id("ps"))

    assert examples
    assert {(example.source, example.verified) for example in examples} == {("tldr", "none")}


def test_tar_keeps_curated_and_tldr_examples(repo: Repository) -> None:
    sources = {example.id: example.source for example in repo.examples(entry_id("tar"))}

    assert sources["tar-create-gzip"] == "curated"
    assert sources["tar-tldr-1"] == "tldr"


def test_notes_follow_the_fixture_in_order(repo: Repository) -> None:
    data = load_fixture()
    for position, item in enumerate(data.entries, start=1):
        assert repo.notes(position) == list(item.notes)


def test_subcommands_follow_the_fixture_in_order(repo: Repository) -> None:
    data = load_fixture()
    for position, item in enumerate(data.entries, start=1):
        assert repo.subcommands(position) == list(item.subcommands)
    assert [sub.name for sub in repo.subcommands(entry_id("git"))] == [
        sub.name for sub in next(i for i in data.entries if i.entry.name == "git").subcommands
    ]


def test_related_follows_the_fixture_in_order(repo: Repository) -> None:
    data = load_fixture()
    for position, item in enumerate(data.entries, start=1):
        assert repo.related(position) == list(item.related)
    assert "cd" in repo.related(entry_id("ls"))


@pytest.mark.parametrize("method", ["sections", "examples", "notes", "subcommands", "related"])
def test_children_of_an_unknown_id_are_empty(repo: Repository, method: str) -> None:
    assert getattr(repo, method)(10_000) == []


# --- meta and stats --------------------------------------------------------------------------


def test_meta_has_the_finalize_keys_and_fixture_items(repo: Repository) -> None:
    meta = repo.meta()

    assert {"schema_version", "index_digest", "built_at", "attribution"} <= set(meta)
    assert meta["schema_version"] == "1"
    assert meta["built_at"] == "2026-01-01T00:00:00+00:00"
    assert meta["attribution"] == load_fixture().meta["attribution"]
    assert list(meta) == sorted(meta)


def test_meta_returns_a_fresh_dict(repo: Repository) -> None:
    first = dict(repo.meta())
    mutable = repo.meta()
    assert isinstance(mutable, dict)
    mutable["schema_version"] = "tampered"

    assert repo.meta() == first


def test_stats_match_the_fixture(repo: Repository) -> None:
    items = load_fixture().entries

    assert repo.stats() == IndexStats(
        entries=len(items),
        man_pages=sum(1 for i in items if i.entry.has_man and i.entry.kind is not Kind.BUILTIN),
        builtins=sum(1 for i in items if i.entry.kind is Kind.BUILTIN),
        curated=sum(1 for i in items if i.entry.curated),
        examples=sum(len(i.examples) for i in items),
        subcommands=sum(len(i.subcommands) for i in items),
    )


def test_stats_of_an_empty_index_are_zero(tmp_path: Path) -> None:
    empty = replace(load_fixture(), entries=())
    repository = open_repo(build_fixture_index(tmp_path / "empty.db", empty))
    try:
        assert repository.stats() == IndexStats(0, 0, 0, 0, 0, 0)
        assert repository.names() == []
    finally:
        repository.close()


# --- fts -------------------------------------------------------------------------------------


def test_fts_weights_rank_name_over_intents_over_summary_over_body() -> None:
    assert tuple(sorted(FTS_WEIGHTS, reverse=True)) == FTS_WEIGHTS
    assert len(FTS_WEIGHTS) == 4


def test_fts_finds_an_entry_by_intent(repo: Repository) -> None:
    hits = repo.fts("archive", 10)

    assert all(isinstance(hit, FtsHit) for hit in hits)
    assert hits[0].entry_id == entry_id("tar")


def test_fts_ranks_a_name_hit_above_a_body_only_hit(repo: Repository) -> None:
    hits = repo.fts("zip", 10)
    ranks = {hit.entry_id: hit.score for hit in hits}

    assert hits[0].entry_id == entry_id("zip")
    assert entry_id("unzip") in ranks
    assert ranks[entry_id("zip")] > ranks[entry_id("unzip")]


def test_fts_matches_an_alias_through_the_name_column(repo: Repository) -> None:
    assert repo.fts("gunzip", 5)[0].entry_id == entry_id("gzip")


def test_fts_combines_tokens_with_and(repo: Repository) -> None:
    both = {hit.entry_id for hit in repo.fts("zip archive", 10)}
    first = {hit.entry_id for hit in repo.fts("zip", 10)}

    assert both
    assert both <= first


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_fts_with_a_blank_query_is_empty(repo: Repository, query: str) -> None:
    assert repo.fts(query, 5) == []


def test_fts_respects_the_limit(repo: Repository) -> None:
    everything = repo.fts("files", 100)

    assert len(everything) > 3
    assert repo.fts("files", 3) == everything[:3]
    assert len(repo.fts("files", 1)) == 1


@pytest.mark.parametrize("limit", [0, -1])
def test_fts_rejects_a_limit_below_one(repo: Repository, limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        repo.fts("ls", limit)


def test_fts_orders_by_descending_score_then_entry_id(repo: Repository) -> None:
    hits = repo.fts("files", 100)

    assert [(-hit.score, hit.entry_id) for hit in hits] == sorted(
        (-hit.score, hit.entry_id) for hit in hits
    )
    assert all(hit.score > 0 for hit in hits)


def test_fts_without_a_match_is_empty(repo: Repository) -> None:
    assert repo.fts("zzzznomatchzzzz", 5) == []


NEUTRALISED_QUERIES = [
    "git-commit",
    "NEAR(x",
    "NEAR(ls cat, 5)",
    "AND",
    "OR x",
    "NOT",
    "ls OR cat",
    "name:ls",
    "x*",
    "ls*",
    '"',
    '""',
    'a "b" c',
    "'; DROP TABLE entry; --",
    "*",
    "-",
    "^ls",
    "ls\x00",
    "\x00",
    "emoji 🙂 ☕",
    "a" * 10_000,
    "(" * 500,
    "{name}: ls",
    "- ls",
    "NEAR/3",
    "ls OR",
    "“ls”",
    "ls\\",
    "\ud800",
    "ls \udfff cat",
]


@pytest.mark.parametrize("query", NEUTRALISED_QUERIES)
def test_fts_never_raises_on_hostile_text(repo: Repository, query: str) -> None:
    hits = repo.fts(query, 10)

    assert isinstance(hits, list)
    assert repo.get_entry("ls") is not None
    assert repo.stats().entries == len(load_fixture().entries)


def test_fts_hyphenated_text_matches_as_a_phrase(repo: Repository) -> None:
    hits = repo.fts("git-commit", 5)

    assert [hit.entry_id for hit in hits][:1] == [entry_id("git-commit")]


@pytest.mark.parametrize("query", ["name:ls", "name : ls", "body:zip", "summary:zip"])
def test_fts_does_not_treat_a_colon_as_a_column_filter(
    fixture_index: Path, repo: Repository, query: str
) -> None:
    raw = query.replace(" ", "")
    with closing(sqlite3.connect(fixture_index)) as conn:
        column_hits = conn.execute(
            "SELECT rowid FROM search_fts WHERE search_fts MATCH ?", (raw,)
        ).fetchall()

    assert column_hits  # unsanitised, FTS5 would apply the column filter
    assert repo.fts(query, 100) == []


def test_fts_operator_words_are_plain_terms(repo: Repository) -> None:
    assert repo.fts("ls OR cat", 10) == repo.fts('ls "OR" cat', 10)
    assert repo.fts("ls AND cat", 10) == []


def test_fts_star_is_not_a_prefix_search(repo: Repository) -> None:
    assert repo.fts("arch*", 10) == []
    assert repo.fts("arch", 10) == []
    assert repo.fts("archive", 10)


def test_fts_punctuation_only_tokens_match_nothing_or_are_ignored(repo: Repository) -> None:
    assert repo.fts("-", 10) == []
    assert repo.fts('"', 10) == []
    assert repo.fts("*", 10) == []
    assert repo.fts("- zip", 10) == repo.fts("zip", 10)


def test_fts_uses_only_the_first_tokens(repo: Repository) -> None:
    words = ["files"] * MAX_FTS_TOKENS + ["zzzznomatchzzzz"] * 68
    capped = repo.fts(" ".join(words[:MAX_FTS_TOKENS]), 10)

    assert capped
    assert repo.fts(" ".join(words), 10) == capped


@pytest.fixture(scope="module")
def shared_repo(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Repository]:
    path = build_fixture_index(tmp_path_factory.mktemp("repo-property") / "index.db")
    repository = open_repo(path)
    yield repository
    repository.close()


@settings(max_examples=200)
@given(st.text())
def test_fts_property_any_text_is_safe(shared_repo: Repository, text: str) -> None:
    hits = shared_repo.fts(text, 5)

    assert len(hits) <= 5
    if not text.replace("\x00", " ").split():
        assert hits == []


# `st.text()` never draws surrogates, so these pieces add the characters that break UTF-8
# encoding next to the ones FTS5 treats as syntax.
HOSTILE_TEXT = st.lists(
    st.sampled_from(["\ud800", "\udfff", "\x00", '"', "*", "-", ":", " ", "a", "ls"])
).map("".join)


@settings(max_examples=200)
@given(HOSTILE_TEXT)
def test_fts_property_hostile_alphabet_is_total(shared_repo: Repository, text: str) -> None:
    assert len(shared_repo.fts(text, 5)) <= 5
    assert (shared_repo.get_entry(text) is not None) == (text == "ls")


@pytest.mark.parametrize("name", ["\ud800", "ls\udfff", "𐏿"])
def test_fts_and_get_entry_with_an_unencodable_name_match_nothing(
    repo: Repository, name: str
) -> None:
    assert repo.fts(name, 5) == []
    assert repo.get_entry(name) is None
    assert repo.get_entry("ls", section=name) is None


def test_get_entry_with_a_nul_in_the_name_is_none(repo: Repository) -> None:
    assert repo.get_entry("l\x00s") is None


# --- errors ----------------------------------------------------------------------------------


def corrupt_copy(fixture_index: Path, tmp_path: Path, sql: str) -> Path:
    path = tmp_path / "corrupt.db"
    shutil.copy(fixture_index, path)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(sql)
        conn.commit()
    return path


def test_get_entry_on_a_bogus_kind_is_corrupt(fixture_index: Path, tmp_path: Path) -> None:
    path = corrupt_copy(
        fixture_index, tmp_path, "UPDATE entry SET kind = 'bogus' WHERE name = 'ls'"
    )
    repository = open_repo(path)
    try:
        with pytest.raises(IndexUnavailableError, match=r"^index corrupt: entry row \d+$") as info:
            repository.get_entry("ls")
        assert info.value.hint == REBUILD_HINT
        assert isinstance(info.value.__cause__, ValueError)
        assert repository.get_entry("cat") is not None
    finally:
        repository.close()


def test_names_on_a_bogus_origin_is_corrupt(fixture_index: Path, tmp_path: Path) -> None:
    path = corrupt_copy(
        fixture_index, tmp_path, "UPDATE entry SET origin = 'bogus' WHERE name = 'ls'"
    )
    repository = open_repo(path)
    try:
        with pytest.raises(IndexUnavailableError, match="index corrupt: entry row"):
            repository.names()
    finally:
        repository.close()


@pytest.mark.parametrize(
    ("sql", "method", "table"),
    [
        ("UPDATE entry SET name = 'a b' WHERE name = 'ls'", "get_entry_by_id", "entry"),
        (
            "UPDATE doc_section SET ord = -1 WHERE entry_id = {id} AND ord = 0",
            "sections",
            "doc_section",
        ),
        ("UPDATE example SET source = 'bogus' WHERE entry_id = {id}", "examples", "example"),
        ("UPDATE example SET cmd = '  ' WHERE entry_id = {id}", "examples", "example"),
        ("UPDATE note SET kind = 'bogus' WHERE entry_id = {id}", "notes", "note"),
        ("UPDATE subcommand SET source = ' ' WHERE entry_id = {id}", "subcommands", "subcommand"),
    ],
)
def test_children_with_a_rejected_value_are_corrupt(
    fixture_index: Path, tmp_path: Path, sql: str, method: str, table: str
) -> None:
    target = entry_id("ls") if method == "get_entry_by_id" else entry_id("diskutil", "8")
    path = corrupt_copy(fixture_index, tmp_path, sql.format(id=target))
    repository = open_repo(path)
    try:
        with pytest.raises(IndexUnavailableError, match=f"index corrupt: {table} row {target}"):
            getattr(repository, method)(target)
    finally:
        repository.close()


def test_a_closed_connection_is_index_unreadable(fixture_index: Path) -> None:
    repository = open_repo(fixture_index)
    repository.close()

    with pytest.raises(IndexUnavailableError, match=r"^index unreadable$") as info:
        repository.names()
    assert info.value.hint == REBUILD_HINT
    assert isinstance(info.value.__cause__, sqlite3.Error)


@pytest.mark.parametrize(
    "call",
    [
        lambda r: r.meta(),
        lambda r: r.get_entry("ls"),
        lambda r: r.get_entry_by_id(1),
        lambda r: r.explain(1),
        lambda r: r.sections(1),
        lambda r: r.examples(1),
        lambda r: r.notes(1),
        lambda r: r.subcommands(1),
        lambda r: r.related(1),
        lambda r: r.fts("ls", 5),
        lambda r: r.stats(),
    ],
)
def test_every_query_maps_database_errors(
    fixture_index: Path, call: Callable[[Repository], object]
) -> None:
    repository = open_repo(fixture_index)
    repository.close()

    with pytest.raises(IndexUnavailableError, match="index unreadable"):
        call(repository)


def test_a_missing_table_is_index_unreadable(fixture_index: Path, tmp_path: Path) -> None:
    path = corrupt_copy(fixture_index, tmp_path, "DROP TABLE note")
    repository = open_repo(path)
    try:
        with pytest.raises(IndexUnavailableError, match="index unreadable"):
            repository.notes(1)
    finally:
        repository.close()


def test_close_is_idempotent(fixture_index: Path) -> None:
    repository = open_repo(fixture_index)

    repository.close()
    repository.close()

    with pytest.raises(IndexUnavailableError, match="index unreadable"):
        repository.stats()
