"""leva.ingest catalog assembly: entries, aliases, builtins, executables and D-005 ranks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from leva.ingest._catalog import (
    BASH_PAGE,
    ZSH_PAGE,
    Catalog,
    CatalogEntry,
    assign_ranks,
    build_catalog,
    rank_key,
)
from leva.ingest._pipeline import Page, StubAlias
from leva.manparse import parse_man
from leva.model import Kind, Origin
from leva.sources import Executable, ManFile
from tests.support.ingest_fakes import rendered_page


def man_file(
    name: str, section: str = "1", origin: Origin = Origin.MACOS, dir_index: int = 0
) -> ManFile:
    path = Path(f"/man/man{section}/{name}.{section}")
    return ManFile(path, name, section, origin, 0, dir_index)


def page(
    name: str,
    section: str = "1",
    summary: str = "",
    *,
    names: Sequence[str] = (),
    origin: Origin = Origin.MACOS,
    sections: Sequence[tuple[str, str]] = (),
) -> Page:
    text = rendered_page(name, section, summary, names=names, sections=sections)
    return Page(man_file(name, section, origin), parse_man(text, name_hint=name))


def builtins_page(name: str, items: Mapping[str, tuple[str, str]]) -> Page:
    """A shell page whose SHELL BUILTIN COMMANDS lists `items`: builtin -> (term, description)."""
    body = "\n".join(f"{term}\n       {desc}" for term, desc in items.values())
    return page(name, sections=[("SHELL BUILTIN COMMANDS", body)])


def zsh_page(items: Mapping[str, tuple[str, str]]) -> Page:
    return builtins_page(ZSH_PAGE[0], items)


def bash_page(items: Mapping[str, tuple[str, str]]) -> Page:
    return builtins_page(BASH_PAGE[0], items)


def exe(path: str, origin: Origin = Origin.MACOS) -> Executable:
    return Executable(Path(path).name, Path(path), origin)


def stub(name: str, target: str, section: str = "1", target_section: str = "1") -> StubAlias:
    return StubAlias(man_file(name, section), target, target_section)


def by(catalog: Catalog, name: str) -> list[CatalogEntry]:
    return [entry for entry in catalog.entries if entry.name == name]


def one(catalog: Catalog, name: str) -> CatalogEntry:
    (entry,) = by(catalog, name)
    return entry


def entry(name: str = "x", **fields: object) -> CatalogEntry:
    base: dict[str, object] = {
        "name": name,
        "section": "1",
        "kind": Kind.MANPAGE_ONLY,
        "origin": Origin.MACOS,
        "summary": "",
        "path": None,
        "has_man": True,
    }
    return CatalogEntry(**(base | fields))  # type: ignore[arg-type]  # kwargs built dynamically


ECHO_ITEMS = {"echo": ("echo [ -n ] [ arg ... ]", "Writes the arguments. Then a newline.")}


# 1. echo three ways
def test_echo_three_ways() -> None:
    catalog = build_catalog(
        [page("echo", summary="write arguments"), zsh_page(ECHO_ITEMS), bash_page(ECHO_ITEMS)],
        [],
        [exe("/bin/echo")],
    )
    bash, zsh, man = by(catalog, "echo")  # write order: (name, section, origin)
    assert (man.section, man.origin, man.kind, man.path, man.rank) == (
        "1",
        Origin.MACOS,
        Kind.EXECUTABLE,
        "/bin/echo",
        0,
    )
    assert man.summary == "write arguments"
    assert man.parsed is not None
    assert (zsh.section, zsh.origin, zsh.kind, zsh.path, zsh.rank) == (
        None,
        Origin.ZSH,
        Kind.BUILTIN,
        None,
        1,
    )
    assert (bash.origin, bash.kind, bash.path, bash.rank) == (Origin.BASH, Kind.BUILTIN, None, 2)
    for builtin in (zsh, bash):
        assert builtin.has_man is True
        assert builtin.parsed is None
        assert builtin.summary == "Writes the arguments."
        assert [(s.heading, s.ord) for s in builtin.sections] == [
            ("SYNOPSIS", 0),
            ("DESCRIPTION", 1),
        ]
        assert builtin.sections[0].body == "echo [ -n ] [ arg ... ]"
        assert builtin.sections[1].body == "Writes the arguments. Then a newline."


# 2. cd via stub plus builtin
def test_cd_stub_and_builtin_make_no_exe_only_entry() -> None:
    cd_items = {"cd": ("cd [ dir ]", "Changes the directory.")}
    catalog = build_catalog(
        [page("builtin", names=["builtin", "cd"]), zsh_page(cd_items), bash_page(cd_items)],
        [stub("cd", "builtin")],
        [exe("/usr/bin/cd")],
    )
    bash, zsh = by(catalog, "cd")  # write order: (name, section, origin)
    assert (zsh.origin, zsh.rank, zsh.path) == (Origin.ZSH, 0, None)
    assert (bash.origin, bash.rank, bash.path) == (Origin.BASH, 1, None)
    holder = one(catalog, "builtin")
    assert holder.aliases == ("cd",)
    assert holder.path is None
    assert holder.kind is Kind.MANPAGE_ONLY


# 3. `[` alias
def test_bracket_alias_attaches_to_test() -> None:
    catalog = build_catalog(
        [page("test", names=["test", "["])],
        [stub("[", "test")],
        [exe("/bin/["), exe("/bin/test")],
    )
    test = one(catalog, "test")
    assert test.aliases == ("[",)
    assert test.path == "/bin/test"
    assert by(catalog, "[") == []


# 4. exe-only
def test_exe_only_entry() -> None:
    catalog = build_catalog([], [], [exe("/opt/homebrew/bin/bat", Origin.HOMEBREW)])
    bat = one(catalog, "bat")
    assert (bat.section, bat.kind, bat.origin) == (None, Kind.EXECUTABLE, Origin.HOMEBREW)
    assert (bat.has_man, bat.summary, bat.sections, bat.parsed, bat.rank) == (
        False,
        "",
        (),
        None,
        0,
    )
    assert bat.path == "/opt/homebrew/bin/bat"


# 5. exe attached through an alias
def test_exe_attached_through_alias() -> None:
    catalog = build_catalog([page("foo", names=["foo", "bar"])], [], [exe("/usr/bin/bar")])
    foo = one(catalog, "foo")
    assert (foo.path, foo.kind, foo.aliases) == ("/usr/bin/bar", Kind.EXECUTABLE, ("bar",))
    assert by(catalog, "bar") == []


def test_own_name_executable_wins_over_alias_executable() -> None:
    catalog = build_catalog(
        [page("foo", names=["foo", "bar"])], [], [exe("/usr/bin/bar"), exe("/usr/bin/foo")]
    )
    foo = one(catalog, "foo")
    assert foo.path == "/usr/bin/foo"
    assert by(catalog, "bar") == []


def test_alias_executable_goes_to_best_ranked_owner() -> None:
    catalog = build_catalog(
        [page("zed", "8", names=["zed", "al"]), page("abc", "1", names=["abc", "al"])],
        [],
        [exe("/usr/bin/al")],
    )
    assert one(catalog, "abc").path == "/usr/bin/al"
    assert one(catalog, "zed").path is None


def test_two_alias_executables_of_one_owner_keep_the_first_path() -> None:
    catalog = build_catalog(
        [page("foo", names=["foo", "a", "b"])], [], [exe("/usr/bin/b"), exe("/usr/bin/a")]
    )
    assert one(catalog, "foo").path == "/usr/bin/a"
    assert [e.name for e in catalog.entries] == ["foo"]


# 6. section 1 vs 8
def test_section_one_and_eight_share_the_path_and_rank_one_first() -> None:
    catalog = build_catalog([page("sync", "8"), page("sync", "1")], [], [exe("/bin/sync")])
    one_, eight = by(catalog, "sync")
    assert [(e.section, e.path, e.kind, e.rank) for e in (one_, eight)] == [
        ("1", "/bin/sync", Kind.EXECUTABLE, 0),
        ("8", "/bin/sync", Kind.EXECUTABLE, 1),
    ]


# 7. origin and path come from the received page and executables
def test_origin_and_summary_come_from_the_received_page() -> None:
    catalog = build_catalog(
        [page("git", summary="tracker", origin=Origin.HOMEBREW)],
        [],
        [exe("/opt/homebrew/bin/git", Origin.HOMEBREW)],
    )
    git = one(catalog, "git")
    assert (git.section, git.origin, git.summary) == ("1", Origin.HOMEBREW, "tracker")
    assert git.path == "/opt/homebrew/bin/git"


def test_path_follows_bin_order_and_origin_follows_man_dir() -> None:
    catalog = build_catalog(
        [page("git", origin=Origin.HOMEBREW)],
        [],
        [exe("/usr/bin/git"), exe("/opt/homebrew/bin/git", Origin.HOMEBREW)],
    )
    git = one(catalog, "git")
    assert (git.origin, git.path) == (Origin.HOMEBREW, "/usr/bin/git")


# 8. rsync: a stub shadowing a real page
def test_stub_alias_absorbs_the_alias_executable() -> None:
    catalog = build_catalog(
        [page("openrsync")],
        [stub("rsync", "openrsync")],
        [exe("/usr/bin/openrsync"), exe("/usr/bin/rsync")],
    )
    openrsync = one(catalog, "openrsync")
    assert openrsync.aliases == ("rsync",)
    assert openrsync.path == "/usr/bin/openrsync"
    assert by(catalog, "rsync") == []


# 9. Xsan: a stub rendered as itself
def test_stub_rendered_as_itself_is_indexed_under_its_own_name() -> None:
    parsed = parse_man(
        rendered_page("cvadmin", names=["cvadmin"], summary="admin tool"), name_hint="cvadmin"
    )
    redirected = Page(man_file("cvadmin"), replace(parsed, redirect_to="../../x/man1/cvadmin.1"))
    catalog = build_catalog([redirected], [], [])
    cvadmin = one(catalog, "cvadmin")
    assert cvadmin.sections == parsed.sections
    assert cvadmin.parsed is redirected.parsed
    assert cvadmin.summary == "admin tool"


# 10. a stub whose target is not indexed
def test_stub_with_unindexed_target_is_skipped() -> None:
    catalog = build_catalog([page("other")], [stub("x", "gone")], [])
    assert catalog.skipped == (("x(1)", "stub target not indexed: gone(1)"),)
    assert all(e.aliases == () for e in catalog.entries)


def test_stub_chain_is_followed_to_the_page() -> None:
    catalog = build_catalog(
        [page("d")], [stub("a", "b"), stub("b", "c", target_section="8"), stub("c", "d", "8")], []
    )
    assert catalog.skipped == ()
    assert one(catalog, "d").aliases == ("a", "b", "c")


def test_stub_chain_to_a_missing_page_is_skipped() -> None:
    catalog = build_catalog([page("other")], [stub("a", "b"), stub("b", "gone")], [])
    assert catalog.skipped == (
        ("a(1)", "stub target not indexed: b(1)"),
        ("b(1)", "stub target not indexed: gone(1)"),
    )


def test_stub_cycle_is_skipped() -> None:
    catalog = build_catalog([page("other")], [stub("a", "b"), stub("b", "a")], [])
    assert [label for label, _ in catalog.skipped] == ["a(1)", "b(1)"]
    assert one(catalog, "other").aliases == ()


def test_stub_alias_equal_to_the_entry_name_adds_nothing() -> None:
    catalog = build_catalog([page("a", "1")], [stub("a", "a", section="8", target_section="1")], [])
    assert one(catalog, "a").aliases == ()
    assert catalog.skipped == ()


# 11. missing shell pages
def test_missing_shell_pages_give_no_builtins() -> None:
    catalog = build_catalog([page("ls")], [], [])
    assert [e.kind for e in catalog.entries] == [Kind.MANPAGE_ONLY]


def test_shell_pages_stay_entries_themselves() -> None:
    catalog = build_catalog([zsh_page(ECHO_ITEMS)], [], [])
    assert [(e.name, e.section) for e in catalog.entries] == [("echo", None), ("zshbuiltins", "1")]


# 12. order and determinism
def test_entries_are_sorted_by_key_and_unique() -> None:
    items = {"cd": ("cd [ dir ]", "Changes directory.")}
    catalog = build_catalog(
        [page("sync", "8"), page("sync", "1"), zsh_page(items), bash_page(items), page("ls")],
        [],
        [exe("/bin/sync"), exe("/opt/homebrew/bin/bat", Origin.HOMEBREW)],
    )
    keys = [e.key for e in catalog.entries]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)
    assert ("cd", "", "zsh") in keys
    assert keys.index(("cd", "", "bash")) < keys.index(("sync", "1", "macos"))


def test_same_input_twice_and_shuffled_input_give_equal_catalogs() -> None:
    items = {"echo": ("echo [ arg ]", "Writes.")}
    pages = [page("echo"), page("test", names=["test", "["]), zsh_page(items), bash_page(items)]
    aliases = [stub("[", "test")]
    exes = [exe("/bin/echo"), exe("/bin/["), exe("/bin/test"), exe("/usr/bin/zz")]
    first = build_catalog(pages, aliases, exes)
    assert build_catalog(pages, aliases, exes) == first
    assert build_catalog(pages[::-1], aliases[::-1], exes[::-1]) == first


# 13. rank_key / assign_ranks
def test_rank_key_orders_section_kind_origin_and_position() -> None:
    sec1 = entry(section="1")
    sec8 = entry(section="8")
    sec5 = entry(section="5")
    none = entry(section=None, kind=Kind.BUILTIN, origin=Origin.ZSH)
    bash = entry(section=None, kind=Kind.BUILTIN, origin=Origin.BASH)
    keys = [rank_key(e, 0) for e in (sec1, sec8, sec5, none, bash)]
    assert keys[0] < keys[1] < keys[2] < keys[3] < keys[4]
    assert rank_key(sec1, 0) < rank_key(sec1, 1)


def test_rank_key_puts_entries_without_man_last() -> None:
    exe_only = entry(section=None, kind=Kind.EXECUTABLE, has_man=False)
    assert rank_key(exe_only, 0) > rank_key(entry(section=None, kind=Kind.BUILTIN), 5)


def test_curated_beats_section_only_with_use_curated() -> None:
    curated8 = entry(section="8", curated=True)
    plain1 = entry(section="1")
    assert rank_key(curated8, 1) < rank_key(plain1, 0)
    assert rank_key(curated8, 1, use_curated=False) > rank_key(plain1, 0, use_curated=False)


def test_assign_ranks_is_per_name_and_keeps_order() -> None:
    entries = [
        entry("a", section="8"),
        entry("a", section="1", origin=Origin.HOMEBREW),
        entry("b", section="1"),
    ]
    ranked = assign_ranks(entries)
    assert [(e.name, e.section) for e in ranked] == [("a", "8"), ("a", "1"), ("b", "1")]
    assert [e.rank for e in ranked] == [1, 0, 0]


def test_assign_ranks_puts_curated_entry_first() -> None:
    ranked = assign_ranks([entry("a", section="1"), entry("a", section="8", curated=True)])
    assert [e.rank for e in ranked] == [1, 0]


# 14. CatalogEntry invariants
@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"name": "a b"}, "name must be a valid name"),
        ({"name": ""}, "name must be a valid name"),
        ({"section": "1 2"}, "section must be a valid name"),
        ({"aliases": ("x",), "name": "x"}, "aliases must be valid names other than"),
        ({"aliases": ("b", "a")}, "sorted and unique"),
        ({"aliases": ("a", "a")}, "sorted and unique"),
        ({"aliases": ("a b",)}, "aliases must be valid names other than"),
        ({"rank": -1}, "rank must be >= 0"),
        ({"kind": "builtin"}, "kind must be a Kind member"),
        ({"origin": "zsh"}, "origin must be an Origin member"),
    ],
)
def test_catalog_entry_rejects_invalid_fields(fields: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        entry(**fields)


def test_catalog_entry_key() -> None:
    assert entry("n", section=None, origin=Origin.ZSH, kind=Kind.BUILTIN).key == ("n", "", "zsh")
    assert entry("n", section="8").key == ("n", "8", "macos")
    assert entry(aliases=("a", "b")).aliases == ("a", "b")
