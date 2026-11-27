"""Tests for `Library`, `Card` and the card helpers against the fixture index."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from leva.library import HISTORY_LIMIT, Card, Library
from leva.library._card import example_key, merge_examples, subcommand_examples
from leva.model import Example, ExampleSource, IndexUnavailableError, Section, Subcommand
from leva.repo import Repository
from leva.search import Searcher
from leva.store import open_readonly
from tests.support.index_factory import FixtureData, build_fixture_index, load_fixture


def ids_by_key(data: FixtureData) -> dict[tuple[str, str | None, str], int]:
    return {
        (item.entry.name, item.entry.section, item.entry.origin.value): position
        for position, item in enumerate(data.entries, start=1)
    }


def entry_id(name: str, section: str | None = "1", origin: str = "macos") -> int:
    return ids_by_key(load_fixture())[(name, section, origin)]


def make_library(path: Path) -> Library:
    repo = Repository(open_readonly(path))
    return Library(repo, Searcher(repo))


@pytest.fixture
def repo(fixture_index: Path) -> Iterator[Repository]:
    repository = Repository(open_readonly(fixture_index))
    yield repository
    repository.close()


@pytest.fixture
def lib(repo: Repository) -> Library:
    return Library(repo, Searcher(repo))


def example(cmd: str, source: ExampleSource = "curated", ident: str = "x-ex") -> Example:
    return Example(ident, "d", cmd, source, "none")


def ids(examples: tuple[Example, ...]) -> list[str]:
    return [item.id for item in examples]


def crumbs(cards: tuple[Card, ...]) -> list[tuple[str, ...]]:
    return [card.breadcrumb for card in cards]


# --- open: single names --------------------------------------------------------------------


def test_open_builds_the_full_card_of_a_name(lib: Library, repo: Repository) -> None:
    card = lib.open("ls")

    assert card is not None
    entry = repo.get_entry("ls")
    assert entry is not None
    assert card.entry == entry
    assert card.breadcrumb == ("ls",)
    assert card.summary == entry.summary
    assert card.explain != ""
    assert card.explain == repo.explain(entry.id)
    assert card.notes == tuple(repo.notes(entry.id))
    assert card.related == tuple(repo.related(entry.id))
    assert card.sections == tuple(repo.sections(entry.id))
    assert card.subcommands == tuple(repo.subcommands(entry.id))
    assert card.examples == merge_examples(repo.examples(entry.id))


def test_open_resolves_an_alias_to_the_primary_entry(lib: Library) -> None:
    zcat = lib.open("zcat")
    bracket = lib.open("[")

    assert zcat is not None
    assert (zcat.entry.name, zcat.breadcrumb) == ("gzip", ("gzip",))
    assert bracket is not None
    assert bracket.entry.name == "test"


def test_open_a_shared_name_gives_the_primary_rank(lib: Library) -> None:
    card = lib.open("echo")

    assert card is not None
    assert card.entry.id == entry_id("echo", "1", "macos")


@pytest.mark.parametrize("name", ["nope", "", "   ", "LS"])
def test_open_returns_none_and_keeps_history(lib: Library, name: str) -> None:
    first = lib.open("ls")

    assert lib.open(name) is None
    assert lib.trail() == (first,)


def test_open_an_executable_without_a_page_gives_an_empty_card(lib: Library) -> None:
    card = lib.open("bat")

    assert card is not None
    assert (card.sections, card.examples, card.summary) == ((), (), "")
    assert card.breadcrumb == ("bat",)


# --- open: several words -------------------------------------------------------------------


@pytest.mark.parametrize("text", ["git commit", "git  commit"])
def test_open_two_words_prefers_the_hyphen_entry(lib: Library, text: str) -> None:
    card = lib.open(text)

    assert card is not None
    assert card.entry.name == "git-commit"
    assert card.breadcrumb == ("git", "commit")


def test_open_two_words_opens_another_hyphen_entry(lib: Library) -> None:
    card = lib.open("git log")

    assert card is not None
    assert (card.entry.name, card.breadcrumb) == ("git-log", ("git", "log"))


def test_open_a_subcommand_without_page_synthesizes_a_card(lib: Library) -> None:
    card = lib.open("git status")

    assert card is not None
    assert card.entry.name == "git"
    assert card.summary == "show the working tree state"
    assert card.sections == ()
    assert ids(card.examples) == ["git-status"]
    assert card.breadcrumb == ("git", "status")
    assert card.explain == ""
    assert (card.notes, card.subcommands, card.related) == ((), (), ())
    assert lib.trail() == (card,)


def test_open_a_subcommand_with_body_has_a_description_section(lib: Library) -> None:
    listing = lib.open("diskutil list")
    erase = lib.open("diskutil eraseDisk")

    assert listing is not None
    assert listing.sections == (
        Section("DESCRIPTION", "Prints every attached disk with its partitions and sizes.", 0),
    )
    assert ids(listing.examples) == ["diskutil-list"]
    assert erase is not None
    assert ids(erase.examples) == ["diskutil-erase"]
    assert erase.examples[0].danger is not None


@pytest.mark.parametrize("text", ["git nope", "nope commit"])
def test_open_unknown_two_words_returns_none(lib: Library, text: str) -> None:
    assert lib.open(text) is None
    assert lib.trail() == ()


# --- open_subcommand -----------------------------------------------------------------------


def test_open_subcommand_synthesizes_and_records(lib: Library) -> None:
    git = lib.open("git")
    assert git is not None

    card = lib.open_subcommand(git, "status")

    assert card is not None
    assert (card.entry, card.breadcrumb) == (git.entry, ("git", "status"))
    assert crumbs(lib.trail()) == [("git",), ("git", "status")]
    assert lib.back() == git


def test_open_subcommand_opens_the_page_of_a_hyphen_entry(lib: Library) -> None:
    git = lib.open("git")
    assert git is not None

    card = lib.open_subcommand(git, "commit")

    assert card is not None
    assert (card.entry.name, card.breadcrumb) == ("git-commit", ("git", "commit"))


@pytest.mark.parametrize("sub", ["nope", "Status", ""])
def test_open_subcommand_matches_exactly(lib: Library, sub: str) -> None:
    git = lib.open("git")
    assert git is not None

    assert lib.open_subcommand(git, sub) is None
    assert lib.trail() == (git,)


def test_open_subcommand_with_a_missing_page_falls_back(lib: Library) -> None:
    git = lib.open("git")
    assert git is not None
    broken = replace(
        git,
        subcommands=(Subcommand("x", "s", "missing-page", "hyphen", "body"),),
        examples=(example("git x --flag"),),
    )

    card = lib.open_subcommand(broken, "x")

    assert card is not None
    assert card.entry == git.entry
    assert card.summary == "s"
    assert card.sections == (Section("DESCRIPTION", "body", 0),)
    assert [item.cmd for item in card.examples] == ["git x --flag"]
    assert card.breadcrumb == ("git", "x")


# --- card / open_result --------------------------------------------------------------------


def test_card_builds_without_touching_history(lib: Library) -> None:
    card = lib.card(entry_id("ls"))

    assert card is not None
    assert card.breadcrumb == ("ls",)
    assert lib.trail() == ()
    assert lib.back() is None


def test_card_of_an_unknown_id_is_none(lib: Library) -> None:
    assert lib.card(999_999) is None


def test_open_result_resets_history(lib: Library) -> None:
    lib.open("ls")
    lib.open("tar")

    card = lib.open_result(entry_id("grep"))

    assert card is not None
    assert lib.trail() == (card,)
    assert lib.back() is None


def test_open_result_of_an_unknown_id_keeps_history(lib: Library) -> None:
    ls = lib.open("ls")
    tar = lib.open("tar")

    assert lib.open_result(999_999) is None
    assert lib.trail() == (ls, tar)


# --- history -------------------------------------------------------------------------------


def test_history_moves_like_a_browser(lib: Library) -> None:
    a, b, c = lib.open("ls"), lib.open("tar"), lib.open("grep")

    assert lib.trail() == (a, b, c)
    assert lib.back() == b
    assert lib.back() == a
    assert lib.back() is None
    assert lib.trail() == (a,)
    assert lib.forward() == b

    d = lib.open("find")

    assert lib.forward() is None
    assert lib.trail() == (a, b, d)


def test_history_of_an_empty_library_is_empty(lib: Library) -> None:
    assert (lib.back(), lib.forward(), lib.trail()) == (None, None, ())


def test_forward_stops_at_the_newest_card(lib: Library) -> None:
    lib.open("ls")
    lib.open("tar")

    assert lib.forward() is None
    assert len(lib.trail()) == 2


def test_history_keeps_the_last_fifty_cards(lib: Library) -> None:
    for index in range(55):
        lib.open("ls" if index % 2 == 0 else "tar")

    assert HISTORY_LIMIT == 50
    assert len(lib.trail()) == 50
    for _ in range(49):
        assert lib.back() is not None
    assert lib.back() is None


def test_history_drops_the_oldest_cards_first(lib: Library) -> None:
    names = ["ls", "tar", "grep", "find", "du"]
    for index in range(55):
        lib.open(names[index % len(names)])

    expected = [(names[index % len(names)],) for index in range(5, 55)]

    assert crumbs(lib.trail()) == expected


@pytest.fixture(scope="module")
def module_library(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Library]:
    library = make_library(build_fixture_index(tmp_path_factory.mktemp("library") / "index.db"))
    yield library
    library.close()


@given(
    name=st.text(
        alphabet=st.sampled_from(
            ["g", "i", "t", "c", " ", "\t", "-", "\x00", "\ud800", "\U0001f642", "ß", '"', "*"]
        ),
        max_size=40,
    )
)
def test_open_is_total_over_hostile_text(module_library: Library, name: str) -> None:
    before = module_library.trail()

    card = module_library.open(name)

    if card is None:
        assert module_library.trail() == before
    else:
        assert module_library.trail()[-1] == card


@pytest.mark.parametrize(
    "name",
    [
        "a" * 10_000,
        "git " * 2_500,
        "\x00",
        "\ud800 commit",
        "!!!",
        "\U0001f642",
        "git \x00",
        "-" * 50,
    ],
)
def test_open_returns_none_for_hostile_text_without_touching_history(
    lib: Library, name: str
) -> None:
    assert lib.open(name) is None
    assert lib.trail() == ()


# --- delegation, attribution, close --------------------------------------------------------


def test_search_and_nearest_names_delegate(lib: Library) -> None:
    assert lib.search("compress a folder")[0].name == "tar"
    assert len(lib.search("compress a folder", limit=1)) == 1
    assert "grep" in lib.nearest_names("gerp")


def test_search_and_nearest_names_reject_a_zero_limit(lib: Library) -> None:
    with pytest.raises(ValueError, match="limit"):
        lib.search("tar", limit=0)
    with pytest.raises(ValueError, match="limit"):
        lib.nearest_names("tar", limit=0)


def test_attribution_reads_the_meta_text(lib: Library) -> None:
    assert lib.attribution() == load_fixture().meta["attribution"]


def test_attribution_is_empty_without_meta(tmp_path: Path) -> None:
    data = load_fixture()
    meta = {key: value for key, value in data.meta.items() if key != "attribution"}
    path = build_fixture_index(tmp_path / "v" / "index.db", replace(data, meta=meta))
    library = make_library(path)

    try:
        assert library.attribution() == ""
    finally:
        library.close()


def test_close_is_idempotent_and_ends_reads(fixture_index: Path) -> None:
    library = make_library(fixture_index)

    library.close()
    library.close()

    with pytest.raises(IndexUnavailableError):
        library.open("ls")


def test_errors_of_a_closed_repository_propagate(repo: Repository) -> None:
    library = Library(repo, Searcher(repo))
    repo.close()

    with pytest.raises(IndexUnavailableError):
        library.open("ls")
    with pytest.raises(IndexUnavailableError):
        library.card(1)
    with pytest.raises(IndexUnavailableError):
        library.search("ls")


# --- Card ----------------------------------------------------------------------------------


@pytest.mark.parametrize("breadcrumb", [(), ("git", ""), ("  ",)])
def test_card_rejects_an_empty_or_blank_breadcrumb(
    lib: Library, breadcrumb: tuple[str, ...]
) -> None:
    card = lib.open("ls")
    assert card is not None

    with pytest.raises(ValueError, match="breadcrumb"):
        replace(card, breadcrumb=breadcrumb)


# --- example helpers -----------------------------------------------------------------------


def test_merge_examples_drops_the_tldr_duplicate(lib: Library, repo: Repository) -> None:
    raw = repo.examples(entry_id("tar"))
    card = lib.open("tar")

    assert card is not None
    assert len(raw) == 5
    assert ids(card.examples) == ["tar-create-gzip", "tar-extract", "tar-list", "tar-tldr-2"]


def test_merge_examples_lets_curated_win_when_tldr_comes_first() -> None:
    tldr = example("tar -czf {{a}} {{b}}", "tldr", "tar-tldr")
    curated = example("tar  -czf {{x}} {{y}}", "curated", "tar-cur")
    other = example("tar -tf {{f}}", "curated", "tar-list")

    assert ids(merge_examples([tldr, curated, other])) == ["tar-cur", "tar-list"]


def test_merge_examples_keeps_the_first_of_a_repeated_key_in_one_source() -> None:
    first = example("ls -l", ident="ls-a")
    second = example("ls  -l", ident="ls-b")

    assert ids(merge_examples([first, second])) == ["ls-a"]


def test_merge_examples_keeps_curated_order_and_returns_a_tuple() -> None:
    items = [example(f"ls -{flag}", ident=f"ls-{flag}") for flag in "zyx"]

    merged = merge_examples(items)

    assert isinstance(merged, tuple)
    assert ids(merged) == ["ls-z", "ls-y", "ls-x"]


@pytest.mark.parametrize(
    ("cmd", "key"),
    [
        ("tar  -czf {{a}} {{b}}", "tar -czf {} {}"),
        ("ls \\\n  -l", "ls \\ -l"),
        ("cp {{src}} {{dst}}", "cp {} {}"),
        ("cp {{from}} {{to}}", "cp {} {}"),
        ("", ""),
    ],
)
def test_example_key_normalises_placeholders_and_whitespace(cmd: str, key: str) -> None:
    assert example_key(cmd) == key


@pytest.mark.parametrize(
    ("cmd", "kept"),
    [
        ("git status", True),
        ("git status -s", True),
        ("git  status", True),
        ("{{git}} status", True),
        ("git statusx", False),
        ("git stat", False),
        ("git log --oneline", False),
        ("gitt status", False),
    ],
)
def test_subcommand_examples_match_on_a_word_boundary(cmd: str, kept: bool) -> None:
    item = example(cmd)

    result = subcommand_examples((item,), "git", "status")

    assert (result == (item,)) is kept
