"""Tests for `leva.search` against the fixture index."""

from __future__ import annotations

import json
from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from rapidfuzz import fuzz

from leva.model import IndexUnavailableError, Kind, Origin
from leva.repo import FtsHit, NameRow, Repository
from leva.search import DEFAULT_WEIGHTS, STOPWORDS, MatchReason, Searcher, SearchResult, Weights
from leva.search._ranking import MAX_ORD, intent_match
from leva.store import open_readonly
from tests.support.index_factory import FIXTURE_JSON, build_fixture_index

GOLD_JSON = FIXTURE_JSON.parent / "gold_mini.json"
SUB_LIMIT = 950.0  # sub-score (< 900) plus bonuses (<= 50)


def open_repo(path: Path) -> Repository:
    return Repository(open_readonly(path))


@pytest.fixture
def repo(fixture_index: Path) -> Iterator[Repository]:
    repository = open_repo(fixture_index)
    yield repository
    repository.close()


@pytest.fixture
def searcher(repo: Repository) -> Searcher:
    return Searcher(repo)


def first(results: list[SearchResult]) -> SearchResult:
    assert results, "expected at least one result"
    return results[0]


def key_of(result: SearchResult) -> tuple[str, str | None, str]:
    return (result.name, result.section, result.origin.value)


def band_of(score: float) -> str:
    """Name of the weights tier whose band ``[base, base + 950)`` holds ``score``."""
    bases = {
        name: getattr(DEFAULT_WEIGHTS, name)
        for name in ("exact", "prefix", "fuzzy", "intent", "summary", "partial", "body")
    }
    for name, base in bases.items():
        if base <= score < base + SUB_LIMIT:
            return name
    raise AssertionError(f"score {score} is in no tier band")


# --- blank input, limits --------------------------------------------------------------------


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_blank_query_gives_no_results(searcher: Searcher, query: str) -> None:
    assert searcher.search(query) == []
    assert searcher.nearest_names(query) == []


@pytest.mark.parametrize("limit", [0, -1])
def test_limit_below_one_is_rejected(searcher: Searcher, limit: int) -> None:
    with pytest.raises(ValueError, match=f"limit must be >= 1: {limit}"):
        searcher.search("ls", limit=limit)
    with pytest.raises(ValueError, match=f"limit must be >= 1: {limit}"):
        searcher.nearest_names("ls", limit=limit)


# --- exact, alias, multi-word ---------------------------------------------------------------


def test_exact_name_is_first_with_why_name(searcher: Searcher) -> None:
    result = first(searcher.search("ls"))

    assert (result.name, result.why, result.via) == ("ls", "name", None)
    assert result.score == 7000 + 800 + 20  # exact tier + name + curated bonus


def test_exact_name_ignores_case_and_surrounding_whitespace(searcher: Searcher) -> None:
    expected = first(searcher.search("ls"))

    assert first(searcher.search("LS")) == expected
    assert first(searcher.search("  ls  ")) == expected


@pytest.mark.parametrize(
    ("query", "name", "why"),
    [("zcat", "gzip", "alias"), ("[", "test", "alias"), ("egrep", "grep", "alias")],
)
def test_exact_alias_finds_its_entry(searcher: Searcher, query: str, name: str, why: str) -> None:
    result = first(searcher.search(query))

    assert (result.name, result.why) == (name, why)


def test_multi_word_query_matches_hyphenated_name(searcher: Searcher) -> None:
    result = first(searcher.search("git commit"))

    assert (result.name, result.why) == ("git-commit", "name")
    assert searcher.search("git  commit") == searcher.search("git commit")


# --- prefix ---------------------------------------------------------------------------------


def test_prefix_beats_fuzzy_alias(searcher: Searcher) -> None:
    result = first(searcher.search("gre"))  # WRatio("gre", "egrep") is 90, still below prefix

    assert (result.name, result.why) == ("grep", "name")
    assert band_of(result.score) == "prefix"


def test_prefix_ranks_by_share_of_the_name_matched(searcher: Searcher) -> None:
    top = searcher.search("di")[:3]

    assert [result.name for result in top] == ["diff", "ditto", "diskutil"]
    assert [result.why for result in top] == ["name"] * 3
    assert [result.score for result in top] == [
        pytest.approx(6000 + 800 * 2 / 4),
        pytest.approx(6000 + 800 * 2 / 5),
        pytest.approx(6000 + 800 * 2 / 8 + 20),
    ]


# --- fuzzy ----------------------------------------------------------------------------------


def test_swapped_letters_find_the_name_through_the_distance_rule(searcher: Searcher) -> None:
    assert fuzz.WRatio("gerp", "grep") < 80  # why the optimal-string-alignment rule exists

    result = first(searcher.search("gerp"))

    assert (result.name, result.why) == ("grep", "name")
    assert band_of(result.score) == "fuzzy"


@pytest.mark.parametrize(
    ("query", "name"), [("chmdo", "chmod"), ("dikutil", "diskutil"), ("unzpi", "unzip")]
)
def test_typos_find_the_command(searcher: Searcher, query: str, name: str) -> None:
    assert first(searcher.search(query)).name == name


def test_fuzzy_is_off_for_short_queries(searcher: Searcher) -> None:
    results = searcher.search("l")  # WRatio("l", "sleep") would be 90

    assert [result for result in results if result.why == "name"]
    assert all(result.name.startswith("l") for result in results if result.why == "name")


def test_fuzzy_is_off_for_multi_word_queries(searcher: Searcher) -> None:
    results = searcher.search("find text in files")  # WRatio against "find" would be 90

    assert results
    assert all(result.why != "name" for result in results)


def test_fuzzy_is_off_for_very_long_queries(searcher: Searcher) -> None:
    assert [result for result in searcher.search("a" * 65) if result.why in {"name", "alias"}] == []


# --- intents --------------------------------------------------------------------------------


def test_intent_phrase_matches_with_via(searcher: Searcher) -> None:
    result = first(searcher.search("compress a folder"))

    assert (result.name, result.why, result.via) == ("tar", "intent", "compress a folder")
    assert first(searcher.search("Compress  A Folder")) == result


def test_earlier_intent_scores_ten_points_higher(searcher: Searcher) -> None:
    later = first(searcher.search("delete a folder"))
    earlier = first(searcher.search("delete a file"))

    assert (later.name, later.via) == ("rm", "delete a folder")
    assert (earlier.name, earlier.via) == ("rm", "delete a file")
    assert earlier.score - later.score == 10


def test_all_words_beat_partial_and_summary_hits(searcher: Searcher) -> None:
    result = first(searcher.search("compress folder"))

    assert (result.name, result.why, result.via) == ("tar", "intent", "compress a folder")
    assert band_of(result.score) == "intent"


def test_partial_intent_still_finds_the_command(searcher: Searcher) -> None:
    result = first(searcher.search("extract tar"))

    assert (result.name, result.why, result.via) == ("tar", "intent", "extract an archive")
    assert band_of(result.score) == "partial"


def test_summary_beats_partial_intent(searcher: Searcher) -> None:
    results = searcher.search("list running processes")

    assert (first(results).name, first(results).why) == ("ps", "summary")
    names = [result.name for result in results]
    for later in ("ls", "tar", "diskutil"):  # their intents share only "list"
        assert names.index(later) > names.index("ps")


def test_stopword_only_query_matches_only_an_exact_phrase(searcher: Searcher) -> None:
    assert "a" in STOPWORDS
    assert all(result.why != "intent" for result in searcher.search("a the"))


# --- tiers, bonus ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "ls",
        "gre",
        "gerp",
        "compress folder",
        "extract tar",
        "list running processes",
        "files",
        "text",
    ],
)
def test_scores_stay_inside_their_tier_and_sorted(searcher: Searcher, query: str) -> None:
    results = searcher.search(query)
    name_tiers = {"exact", "prefix", "fuzzy"}
    allowed = {
        "name": name_tiers,
        "alias": name_tiers,
        "intent": {"intent", "partial"},
        "summary": {"summary"},
        "body": {"body"},
    }

    assert results
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
    for result in results:
        assert band_of(result.score) in allowed[result.why], (query, result)


def test_builtin_bonus_and_position_break_exact_ties(searcher: Searcher) -> None:
    results = searcher.search("cd")[:2]

    assert [key_of(result) for result in results] == [("cd", None, "zsh"), ("cd", None, "bash")]
    assert [result.score for result in results] == [7000 + 800 + 10] * 2


def test_builtin_echo_ranks_above_the_executable(searcher: Searcher) -> None:
    results = searcher.search("echo")[:3]

    assert [key_of(result) for result in results] == [
        ("echo", None, "zsh"),
        ("echo", None, "bash"),
        ("echo", "1", "macos"),
    ]
    assert [result.score for result in results] == [7810, 7810, 7800]


def test_custom_weights_are_honoured(repo: Repository) -> None:
    weights = Weights(curated_bonus=20.0, builtin_bonus=30.0)

    assert first(Searcher(repo, weights=weights).search("cd")).score == 7000 + 800 + 30
    assert first(Searcher(repo, weights=weights).search("ls")).score == 7000 + 800 + 20


@pytest.mark.parametrize("bonuses", [(50.0, 0.0), (0.0, 50.0), (25.0, 25.0), (0.0, 0.0)])
@pytest.mark.parametrize("query", ["ls", "cd", "gerp", "compress a folder", "files", "echo"])
def test_the_largest_bonuses_never_lift_a_result_into_a_better_tier(
    repo: Repository, query: str, bonuses: tuple[float, float]
) -> None:
    weights = Weights(curated_bonus=bonuses[0], builtin_bonus=bonuses[1])
    results = Searcher(repo, weights=weights).search(query)
    name_tiers = {"exact", "prefix", "fuzzy"}
    allowed = {
        "name": name_tiers,
        "alias": name_tiers,
        "intent": {"intent", "partial"},
        "summary": {"summary"},
        "body": {"body"},
    }

    assert results
    for result in results:
        assert band_of(result.score) in allowed[result.why], (query, bonuses, result)


def test_intent_sub_scores_keep_phrase_above_all_words_above_partial() -> None:
    """D-029: no ord penalty and no bonus (<= 50) can invert phrase > all words > partial."""
    positions = range(MAX_ORD * 2)  # past MAX_ORD the penalty stops growing
    phrase = [intent_match(("a", "b"), ("a", "b"), ("a", "b"), pos) for pos in positions]
    every = [intent_match(("a", "b"), ("a", "b"), ("a", "b", "c"), pos) for pos in positions]
    some = [intent_match(("a", "b"), ("a", "b"), ("a", "c"), pos) for pos in positions]

    assert all(m is not None and m.tier == "intent" for m in phrase + every)
    assert all(m is not None and m.tier == "partial" for m in some)
    lowest_phrase = min(m.sub for m in phrase if m)
    highest_all_words = max(m.sub for m in every if m)
    assert lowest_phrase > highest_all_words + 50
    assert all(0 <= m.sub < 900 for m in phrase + every + some if m)
    assert [m.sub for m in phrase if m] == sorted((m.sub for m in phrase if m), reverse=True)


# --- dedup, limit, stability ----------------------------------------------------------------


QUERIES = [
    "ls", "grep", "files", "a", "gre", "gerp", "echo", "cd", "compress a folder", "list",
    "text", "delete", "git", "zip", "archive", "folder", "print", "x", "sync", "lines",
]  # fmt: skip


@pytest.mark.parametrize("query", QUERIES)
def test_results_have_unique_ids(searcher: Searcher, query: str) -> None:
    ids = [result.entry_id for result in searcher.search(query)]

    assert len(ids) == len(set(ids))


def test_limit_cuts_the_result_list(searcher: Searcher) -> None:
    assert len(searcher.search("files", limit=3)) == 3
    assert len(searcher.search("files", limit=1)) == 1
    assert searcher.search("files", limit=1) == searcher.search("files")[:1]


def test_same_query_gives_equal_lists(repo: Repository) -> None:
    one, other = Searcher(repo), Searcher(repo)

    assert one.search("files") == one.search("files")
    assert one.search("files") == other.search("files")


# --- odd input ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query", ["🙂", "ls🙂", "ü", "\x00", "\ud800", '"', "*", "NEAR(ls)", "name:ls", "a" * 10_000]
)
def test_odd_input_never_raises(searcher: Searcher, query: str) -> None:
    results = searcher.search(query)

    assert len(results) <= 50
    assert len({result.entry_id for result in results}) == len(results)
    assert len(searcher.nearest_names(query)) <= 3


def test_emoji_only_query_has_no_results(searcher: Searcher) -> None:
    assert searcher.search("🙂") == []


def test_very_many_words_still_answer(searcher: Searcher) -> None:
    results = searcher.search(" ".join(["files"] * 500), limit=5)

    assert len(results) <= 5
    assert all(result.why != "name" for result in results)


@pytest.fixture(scope="module")
def module_index(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Searcher]:
    repository = open_repo(build_fixture_index(tmp_path_factory.mktemp("search") / "index.db"))
    yield Searcher(repository)
    repository.close()


@given(query=st.text(max_size=80), limit=st.integers(min_value=1, max_value=20))
def test_search_invariants_hold_for_any_text(
    module_index: Searcher, query: str, limit: int
) -> None:
    results = module_index.search(query, limit=limit)

    assert len(results) <= limit
    assert len({result.entry_id for result in results}) == len(results)
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
    for result in results:
        assert result.why in get_args(MatchReason)
        assert (result.via is not None) == (result.why == "intent")


HOSTILE = st.text(
    alphabet=st.sampled_from(
        [
            "a",
            "g",
            "l",
            "s",
            " ",
            "\t",
            "-",
            "\x00",
            "\ud800",
            "\udfff",
            "\U0001f642",
            "ß",
            '"',
            "*",
        ]
    ),
    max_size=40,
)


@given(query=HOSTILE, limit=st.integers(min_value=1, max_value=5))
def test_search_and_nearest_names_are_total_over_hostile_text(
    module_index: Searcher, query: str, limit: int
) -> None:
    results = module_index.search(query, limit=limit)

    assert len(results) <= limit
    assert len({result.entry_id for result in results}) == len(results)
    assert len(module_index.nearest_names(query, limit=limit)) <= limit


# --- FTS candidates -------------------------------------------------------------------------


class StubRepo:
    """Minimal stand-in for `Repository`: fixed names and fixed FTS hits."""

    def __init__(self, rows: list[NameRow], hits: list[FtsHit]) -> None:
        self._rows = rows
        self._hits = hits
        self.fts_queries: list[str] = []

    def names(self) -> list[NameRow]:
        return self._rows

    def fts(self, query: str, limit: int) -> list[FtsHit]:
        self.fts_queries.append(query)
        return self._hits


def name_row(entry_id: int, name: str, summary: str = "") -> NameRow:
    return NameRow(entry_id, name, "1", Kind.EXECUTABLE, Origin.MACOS, summary, False, (), ())


def test_unknown_fts_ids_are_skipped_and_negative_scores_clamped() -> None:
    stub = StubRepo(
        [name_row(1, "alpha", "tidy things"), name_row(2, "beta")],
        [FtsHit(99, 5.0), FtsHit(1, -2.0), FtsHit(2, 10.0)],
    )

    results = Searcher(stub).search("tidy")  # type: ignore[arg-type]  # duck-typed stub

    assert [(r.name, r.why, r.score) for r in results] == [
        ("alpha", "summary", 3000),  # score -2 is clamped to 0
        ("beta", "body", 1000 + 400),
    ]


def test_stopwords_neither_restrict_fts_nor_make_a_summary_match() -> None:
    stub = StubRepo(
        [name_row(1, "alpha", "the tool"), name_row(2, "beta", "copy things")],
        [FtsHit(1, 10.0), FtsHit(2, 10.0)],
    )

    results = Searcher(stub).search("how do I copy the file")  # type: ignore[arg-type]  # stub

    assert stub.fts_queries == ["copy file"]
    assert [(r.name, r.why) for r in results] == [("beta", "summary"), ("alpha", "body")]


def test_stopword_only_query_reaches_fts_unchanged() -> None:
    stub = StubRepo([name_row(1, "alpha", "the tool")], [FtsHit(1, 10.0)])

    results = Searcher(stub).search("The  a")  # type: ignore[arg-type]  # duck-typed stub

    assert stub.fts_queries == ["The a"]
    assert [(r.name, r.why) for r in results] == [("alpha", "summary")]


# --- nearest_names --------------------------------------------------------------------------


def test_nearest_names_offers_the_intended_command(searcher: Searcher) -> None:
    assert "grep" in searcher.nearest_names("gerp")


def test_nearest_names_are_distinct_and_cut_to_the_limit(searcher: Searcher) -> None:
    names = searcher.nearest_names("x", limit=5)  # no threshold: always filled

    assert len(names) == 5
    assert len(set(names)) == 5
    assert searcher.nearest_names("x", limit=1) == names[:1]


def test_nearest_names_return_names_and_aliases_as_stored(searcher: Searcher) -> None:
    assert searcher.nearest_names("zcat", limit=1) == ["zcat"]
    assert searcher.nearest_names("ECHO", limit=1) == ["echo"]
    assert searcher.nearest_names("echo", limit=10).count("echo") == 1  # three entries, one string


def test_nearest_names_break_ties_by_string(searcher: Searcher) -> None:
    names = searcher.nearest_names("ls", limit=50)
    scores = [fuzz.WRatio("ls", name.casefold()) for name in names]

    assert scores == sorted(scores, reverse=True)
    pairs = list(zip(names, scores, strict=True))
    for (a, score_a), (b, score_b) in pairwise(pairs):
        assert score_a > score_b or a < b


# --- Weights, SearchResult, lazy load -------------------------------------------------------


def test_default_weights_are_valid_and_ordered() -> None:
    w = DEFAULT_WEIGHTS

    assert w.exact > w.prefix > w.fuzzy > w.intent > w.summary > w.partial > w.body >= 1000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prefix": 7000.0},
        {"fuzzy": 5500.0},
        {"body": 500.0, "partial": 1500.0},
        {"curated_bonus": -1.0},
        {"builtin_bonus": -0.5},
        {"curated_bonus": 40.0, "builtin_bonus": 20.0},
        {"exact": float("nan")},
        {"exact": float("inf")},
        {"exact": 1e18, "prefix": 1e18 - 1e4},
        {"curated_bonus": float("nan")},
    ],
)
def test_invalid_weights_are_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must"):
        Weights(**kwargs)


def make_result(why: str, via: str | None) -> SearchResult:
    return SearchResult(1, "ls", "1", Kind.EXECUTABLE, Origin.MACOS, "", 1.0, why, via)  # type: ignore[arg-type]  # invalid literal on purpose


def test_via_is_only_allowed_with_intent() -> None:
    assert make_result("intent", "list files").via == "list files"
    assert make_result("name", None).via is None
    with pytest.raises(ValueError, match="via must be set exactly when why is 'intent'"):
        make_result("name", "list files")
    with pytest.raises(ValueError, match="via must be set exactly when why is 'intent'"):
        make_result("intent", None)


def test_constructing_a_searcher_does_no_io(fixture_index: Path) -> None:
    repository = open_repo(fixture_index)
    repository.close()

    searcher = Searcher(repository)

    with pytest.raises(IndexUnavailableError):
        searcher.search("ls")


def test_name_list_is_loaded_once(fixture_index: Path) -> None:
    repository = open_repo(fixture_index)
    searcher = Searcher(repository)
    expected = searcher.search("ls")
    original = repository.names
    calls: list[int] = []
    repository.names = lambda: calls.append(1) or original()  # type: ignore[method-assign]  # spy

    assert searcher.search("ls") == expected
    assert calls == []
    repository.close()


# --- gold set -------------------------------------------------------------------------------


def test_gold_mini_expects_are_in_the_top_three(searcher: Searcher) -> None:
    gold = json.loads(GOLD_JSON.read_text(encoding="utf-8"))
    misses = [
        (item["query"], item["expect"], [r.name for r in searcher.search(item["query"])[:3]])
        for item in gold
        if item["expect"] not in {r.name for r in searcher.search(item["query"])[:3]}
    ]

    assert len(gold) == 30
    assert len(gold) - len(misses) >= 27, f"misses: {misses}"
