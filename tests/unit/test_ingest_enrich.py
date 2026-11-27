"""leva.ingest enrichment: curated attachment, tldr, known pages, subcommands and probes."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

from leva.content import (
    CuratedCommand,
    ExampleSpec,
    HelpProbe,
    TldrExample,
    TldrPage,
    VerifyMode,
    VerifySpec,
)
from leva.ingest._catalog import BASH_PAGE, ZSH_PAGE, CatalogEntry, build_catalog
from leva.ingest._enrich import (
    NOT_INSTALLED,
    Enrichment,
    enrich,
    known_pages,
    probe_allowlist,
)
from leva.ingest._pipeline import Page
from leva.manparse import parse_man
from leva.model import Example, Note, Origin, Subcommand
from leva.sources import Executable, ManFile
from tests.support.ingest_fakes import FakeProber, RecordingProgress, rendered_page


def page(
    name: str,
    section: str = "1",
    summary: str = "",
    *,
    names: Sequence[str] = (),
    sections: Sequence[tuple[str, str]] = (),
) -> Page:
    text = rendered_page(name, section, summary, names=names, sections=sections)
    man = ManFile(Path(f"/man/man{section}/{name}.{section}"), name, section, Origin.MACOS, 0, 0)
    return Page(man, parse_man(text, name_hint=name))


def shell_page(name: str, items: Mapping[str, str]) -> Page:
    """A shell page listing `items` (builtin -> description) under SHELL BUILTIN COMMANDS."""
    body = "\n".join(f"{term}\n       {desc}" for term, desc in items.items())
    return page(name, sections=[("SHELL BUILTIN COMMANDS", body)])


def exe(path: str) -> Executable:
    return Executable(Path(path).name, Path(path), Origin.MACOS)


def catalog(
    pages: Sequence[Page], executables: Sequence[Executable] = ()
) -> tuple[CatalogEntry, ...]:
    return build_catalog(pages, [], executables).entries


def curated(
    name: str,
    *,
    section: str | None = None,
    notes: tuple[Note, ...] = (),
    examples: tuple[ExampleSpec, ...] = (),
    subcommands: tuple[Subcommand, ...] = (),
    related: tuple[str, ...] = (),
    help_probe: HelpProbe | None = None,
) -> CuratedCommand:
    return CuratedCommand(
        name=name,
        section=section,
        summary=f"curated {name}",
        explain=f"explain {name}",
        intents=(f"use {name}",),
        tags=(),
        notes=notes,
        examples=examples,
        subcommands=subcommands,
        related=related,
        help_probe=help_probe,
    )


def spec(
    example_id: str, cmd: str, mode: VerifyMode = "exec", danger: str | None = None
) -> ExampleSpec:
    return ExampleSpec(example_id, f"desc {example_id}", cmd, VerifySpec(mode), danger)


def tldr(name: str, *commands: str) -> TldrPage:
    return TldrPage(name, "common", "", tuple(TldrExample(f"do {c}", c) for c in commands))


def run(
    entries: Sequence[CatalogEntry],
    *,
    commands: Sequence[CuratedCommand] = (),
    pages: Sequence[TldrPage] = (),
    executables: Sequence[Executable] = (),
    prober: FakeProber | None = None,
    progress: RecordingProgress | None = None,
) -> Enrichment:
    fake = prober or FakeProber({})
    return enrich(
        entries,
        curated=commands,
        tldr=pages,
        executables=executables,
        probe_factory=fake.factory,
        progress=progress or RecordingProgress(),
    )


def get(
    result: Enrichment | Sequence[CatalogEntry], name: str, section: str | None
) -> CatalogEntry:
    entries = result.entries if isinstance(result, Enrichment) else result
    (found,) = (e for e in entries if e.name == name and e.section == section)
    return found


def subs(entry: CatalogEntry) -> dict[str, Subcommand]:
    return {sub.name: sub for sub in entry.subcommands}


# 1. curated attachment
def test_curated_content_replaces_the_man_entry_fields() -> None:
    entries = catalog([page("ls", summary="list files")])
    command = curated(
        "ls",
        section="1",
        notes=(Note("macos", "BSD ls"),),
        examples=(
            spec("ls-long", "ls -l"),
            spec("ls-rm", "rm -r {{dir}}", mode="skip", danger="deletes the directory"),
        ),
    )

    result = run(entries, commands=[command])

    ls = get(result, "ls", "1")
    assert result.curated == 1
    assert result.skipped == ()
    assert ls.curated is True
    assert (ls.summary, ls.explain, ls.intents) == ("curated ls", "explain ls", ("use ls",))
    assert ls.notes == (Note("macos", "BSD ls"),)
    assert ls.examples == (
        Example("ls-long", "desc ls-long", "ls -l", "curated", "exec"),
        Example("ls-rm", "desc ls-rm", "rm -r {{dir}}", "curated", "skip", "deletes the directory"),
    )
    assert ls.parsed is not None
    assert ls.rank == 0


def test_man_only_entries_stay_untouched() -> None:
    entries = catalog([page("ls", summary="list files"), page("cat", summary="join files")])

    result = run(entries, commands=[curated("ls")])

    assert get(result, "cat", "1") == get(entries, "cat", "1")
    assert get(result, "cat", "1").curated is False


# 2. target choice
def test_target_without_section_is_the_best_ranked_entry() -> None:
    entries = catalog([page("sync", "1"), page("sync", "8")])

    result = run(entries, commands=[curated("sync")])

    assert get(result, "sync", "1").curated is True
    assert get(result, "sync", "8").curated is False


def test_target_with_section_re_ranks_it_first() -> None:
    entries = catalog([page("sync", "1"), page("sync", "8")])
    assert (get(entries, "sync", "1").rank, get(entries, "sync", "8").rank) == (0, 1)

    result = run(entries, commands=[curated("sync", section="8")])

    assert get(result, "sync", "8").curated is True
    assert (get(result, "sync", "8").rank, get(result, "sync", "1").rank) == (0, 1)
    assert get(result, "sync", "1").curated is False


def test_curated_echo_goes_to_the_man_page_not_the_builtins() -> None:
    items = {"echo": "echo [ -n ] [ arg ... ]"}
    entries = catalog(
        [page("echo"), shell_page(ZSH_PAGE[0], items), shell_page(BASH_PAGE[0], items)]
    )

    result = run(entries, commands=[curated("echo")])

    assert [e.curated for e in result.entries if e.name == "echo"] == [False, False, True]
    assert get(result, "echo", "1").curated is True


# 3. builtins
def test_curated_builtin_goes_to_the_zsh_entry() -> None:
    items = {"cd": "cd [ arg ]"}
    entries = catalog([shell_page(ZSH_PAGE[0], items), shell_page(BASH_PAGE[0], items)])

    result = run(entries, commands=[curated("cd")])

    flags = {e.origin: e.curated for e in result.entries if e.name == "cd"}
    assert flags == {Origin.ZSH: True, Origin.BASH: False}


# 4. not installed
def test_missing_command_is_skipped_and_reported() -> None:
    entries = catalog([page("ls")])

    result = run(entries, commands=[curated("nosuch")])

    assert result.skipped == (("nosuch", "curated command not installed"),)
    assert result.skipped == (("nosuch", NOT_INSTALLED),)
    assert result.curated == 0
    assert result.entries == entries


def test_section_mismatch_is_skipped() -> None:
    entries = catalog([page("ls")])

    result = run(entries, commands=[curated("ls", section="8")])

    assert result.skipped == (("ls", NOT_INSTALLED),)
    assert get(result, "ls", "1").curated is False


def test_skipped_follow_the_curated_order() -> None:
    result = run(catalog([page("ls")]), commands=[curated("zz"), curated("ls"), curated("aa")])

    assert result.skipped == (("zz", NOT_INSTALLED), ("aa", NOT_INSTALLED))
    assert result.curated == 1


# 5. related
def test_related_keeps_names_and_aliases_that_resolve() -> None:
    entries = catalog([page("gzip", names=("gzip", "zcat")), page("grep"), page("ls")])

    result = run(entries, commands=[curated("ls", related=("grep", "zcat", "nothere"))])

    assert get(result, "ls", "1").related == ("grep", "zcat")


# 6. tldr
def test_tldr_examples_follow_the_curated_ones() -> None:
    entries = catalog([page("ls")])
    command = curated("ls", examples=(spec("ls-long", "ls -l"),))

    result = run(entries, commands=[command], pages=[tldr("ls", "ls -a", "ls -R")])

    assert [(e.id, e.source, e.verified, e.cmd) for e in get(result, "ls", "1").examples] == [
        ("ls-long", "curated", "exec", "ls -l"),
        ("ls-tldr-1", "tldr", "none", "ls -a"),
        ("ls-tldr-2", "tldr", "none", "ls -R"),
    ]


def test_tldr_goes_to_the_rank_zero_entry_only() -> None:
    entries = catalog([page("sync", "1"), page("sync", "8")])

    result = run(entries, commands=[curated("sync", section="8")], pages=[tldr("sync", "sync")])

    assert [e.id for e in get(result, "sync", "8").examples] == ["sync-tldr-1"]
    assert get(result, "sync", "1").examples == ()


def test_tldr_for_a_missing_command_is_ignored_silently() -> None:
    progress = RecordingProgress()
    entries = catalog([page("ls")])

    result = run(entries, pages=[tldr("nothere", "nothere -x")], progress=progress)

    assert result.skipped == ()
    assert result.entries == entries
    assert [name for name, _ in progress.events if name == "warn"] == []


# 7. known pages
def test_known_pages_use_the_synopsis_body() -> None:
    entries = catalog(
        [
            page("git", summary="vcs", sections=[("SYNOPSIS", "git [options] command")]),
            page("plain", summary="no synopsis"),
        ]
    )

    known = known_pages(entries)

    assert known["git"].name == "git"
    assert known["git"].summary == "vcs"
    assert known["git"].synopsis.split() == ["git", "[options]", "command"]
    assert known["plain"].summary == "no synopsis"
    assert known["plain"].synopsis == ""


def test_known_pages_skip_builtins_and_executables_without_a_page() -> None:
    items = {"cd": "cd [ arg ]"}
    entries = catalog(
        [page("ls"), shell_page(ZSH_PAGE[0], items)], executables=[exe("/usr/bin/tool")]
    )
    assert {e.name for e in entries} >= {"cd", "tool", "ls"}

    assert set(known_pages(entries)) == {"ls", ZSH_PAGE[0]}


def test_known_pages_take_the_lowest_rank_entry() -> None:
    entries = catalog(
        [
            page("sync", "1", summary="one", sections=[("SYNOPSIS", "sync one")]),
            page("sync", "8", summary="eight", sections=[("SYNOPSIS", "sync eight")]),
        ]
    )

    assert known_pages(entries)["sync"].summary == "one"
    ranked_first = run(entries, commands=[curated("sync", section="8")]).entries
    assert known_pages(ranked_first)["sync"].summary == "curated sync"


def test_synopsis_heading_is_matched_case_insensitively() -> None:
    entries = catalog([page("ls", sections=[("Synopsis", "ls [file]")])])

    assert known_pages(entries)["ls"].synopsis.split() == ["ls", "[file]"]


# 8. extractors
def test_hyphen_page_gives_a_hyphen_subcommand() -> None:
    entries = catalog(
        [
            page("git", summary="vcs"),
            page(
                "git-commit", summary="record changes", sections=[("SYNOPSIS", "git commit [-a]")]
            ),
        ]
    )

    result = run(entries)

    assert subs(get(result, "git", "1")) == {
        "commit": Subcommand("commit", "record changes", "git-commit", "hyphen")
    }
    assert get(result, "git-commit", "1").subcommands == ()


def test_commands_section_gives_section_subcommands() -> None:
    body = "alpha\n    Does alpha.\nbeta\n    Does beta."
    entries = catalog([page("tool", sections=[("COMMANDS", body)])])

    result = run(entries)

    found = subs(get(result, "tool", "1"))
    assert {n: (s.summary, s.source) for n, s in found.items()} == {
        "alpha": ("Does alpha.", "section"),
        "beta": ("Does beta.", "section"),
    }


# 9. merge priority
def test_curated_subcommand_wins_over_the_hyphen_page() -> None:
    entries = catalog(
        [
            page("git"),
            page("git-commit", summary="man summary", sections=[("SYNOPSIS", "git commit")]),
        ]
    )
    own = Subcommand("commit", "my summary", None, "curated")

    result = run(entries, commands=[curated("git", subcommands=(own,))])

    assert subs(get(result, "git", "1")) == {
        "commit": Subcommand("commit", "my summary", "git-commit", "curated")
    }


# 10. probe
def test_probe_subcommands_land_on_the_curated_entry_only() -> None:
    command = curated("brew", help_probe=HelpProbe(("commands",), "brew-commands"))
    entries = catalog([page("brew"), page("other")])
    prober = FakeProber({"brew": "install\nlist\n"})

    result = run(
        entries,
        commands=[command],
        executables=[exe("/opt/homebrew/bin/brew")],
        prober=prober,
    )

    assert prober.allowlists == [{"brew": ("/opt/homebrew/bin/brew", "commands")}]
    assert prober.calls == ["brew"]
    found = subs(get(result, "brew", "1"))
    assert {n: s.source for n, s in found.items()} == {"install": "probe", "list": "probe"}
    assert get(result, "other", "1").subcommands == ()


def test_probes_run_in_sorted_name_order() -> None:
    probe = HelpProbe(("commands",), "brew-commands")
    entries = catalog([page("b"), page("a")])
    prober = FakeProber({"a": "x\n", "b": "y\n"})

    run(
        entries,
        commands=[curated("b", help_probe=probe), curated("a", help_probe=probe)],
        executables=[exe("/bin/a"), exe("/bin/b")],
        prober=prober,
    )

    assert prober.calls == ["a", "b"]


# 11. probe failure
def test_failed_probe_warns_and_enrichment_continues() -> None:
    command = curated(
        "brew",
        help_probe=HelpProbe(("commands",), "brew-commands"),
        subcommands=(Subcommand("own", "mine", None, "curated"),),
    )
    entries = catalog([page("brew", sections=[("COMMANDS", "sect\n    From section.")])])
    prober = FakeProber({}, failing={"brew"})
    progress = RecordingProgress()

    result = run(
        entries,
        commands=[command],
        executables=[exe("/opt/homebrew/bin/brew")],
        prober=prober,
        progress=progress,
    )

    assert [e for e in progress.events if e[0] == "warn"] == [("warn", "probe failed: brew")]
    brew = get(result, "brew", "1")
    assert brew.curated is True
    assert {n: s.source for n, s in subs(brew).items()} == {"own": "curated", "sect": "section"}


# 12. allowlist
def test_allowlist_needs_a_probe_and_an_executable() -> None:
    probe = HelpProbe(("--help",), "two-col")
    commands = [
        curated("a", help_probe=probe),
        curated("b"),
        curated("c", help_probe=probe),
    ]

    allowed = probe_allowlist(commands, [exe("/bin/a"), exe("/bin/b")])

    assert allowed == {"a": ("/bin/a", "--help")}


def test_allowlist_uses_the_first_executable_in_the_given_order() -> None:
    commands = [curated("a", help_probe=HelpProbe(("-h", "x"), "two-col"))]

    allowed = probe_allowlist(commands, [exe("/opt/bin/a"), exe("/usr/bin/a")])

    assert allowed == {"a": ("/opt/bin/a", "-h", "x")}


def test_factory_is_called_once_even_with_an_empty_allowlist() -> None:
    prober = FakeProber({})

    run(catalog([page("ls"), page("cat")]), commands=[curated("ls")], prober=prober)

    assert prober.allowlists == [{}]
    assert prober.calls == []


def test_unmatched_probe_command_is_not_allowlisted() -> None:
    probe = HelpProbe(("commands",), "brew-commands")
    prober = FakeProber({})

    result = run(
        catalog([page("ls")]),
        commands=[curated("brew", help_probe=probe)],
        executables=[exe("/opt/homebrew/bin/brew")],
        prober=prober,
    )

    assert prober.allowlists == [{}]
    assert result.skipped == (("brew", NOT_INSTALLED),)


# 13. progress
def test_progress_reports_one_phase_and_one_advance_per_entry() -> None:
    progress = RecordingProgress()
    entries = catalog([page("ls"), page("cat"), page("grep")])

    run(entries, progress=progress)

    assert progress.events[0] == ("phase", ("enrich", 3))
    assert progress.events[1:] == [("advance", 1)] * 3


def test_empty_catalog_enriches_to_nothing() -> None:
    progress = RecordingProgress()

    result = run([], commands=[curated("ls")], progress=progress)

    assert result == Enrichment((), (("ls", NOT_INSTALLED),), 0)
    assert progress.events == [("phase", ("enrich", 0))]


# 14. order and determinism
def _scenario(extra: Collection[str] = ()) -> Enrichment:
    entries = catalog(
        [
            page("sync", "1"),
            page("sync", "8"),
            page("ls", summary="list"),
            page("git"),
            page("git-add", summary="stage", sections=[("SYNOPSIS", "git add")]),
            *(page(name) for name in extra),
        ]
    )
    return run(
        entries,
        commands=[curated("sync", section="8"), curated("ls", related=("git",))],
        pages=[tldr("ls", "ls -a")],
    )


def test_output_keeps_the_input_key_order() -> None:
    entries = catalog([page("sync", "1"), page("sync", "8"), page("ls"), page("git")])

    result = run(entries, commands=[curated("sync", section="8")])

    assert [e.key for e in result.entries] == [e.key for e in entries]


def test_two_runs_are_equal() -> None:
    assert _scenario() == _scenario()
    assert _scenario().entries != _scenario(extra=["zzz"]).entries
