"""Tests for `leva.subcmd`: hyphen, section and help-text extractors and the merge."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from leva.manparse import ParsedMan
from leva.model import Section, Subcommand
from leva.subcmd import (
    HELP_PROFILES,
    HelpTextExtractor,
    HyphenPageExtractor,
    KnownPage,
    SectionListExtractor,
    SubcommandExtractor,
    merge_subcommands,
)

HELP = Path(__file__).parent.parent / "fixtures" / "help"
NAME_RULE = re.compile(r"[a-z][A-Za-z0-9_.-]*")


def _parsed(*pairs: tuple[str, str]) -> ParsedMan:
    sections = tuple(Section(heading, body, i) for i, (heading, body) in enumerate(pairs))
    return ParsedMan(("x",), "", sections)


def _lines(*lines: str) -> str:
    return "\n".join(lines)


def _sections(*pairs: tuple[str, str]) -> list[Subcommand]:
    return SectionListExtractor().extract("x", _parsed(*pairs), {})


def _names(subs: list[Subcommand]) -> list[str]:
    return [sub.name for sub in subs]


def _probe(profile: str, text: str) -> list[Subcommand]:
    return HelpTextExtractor(profile, text).extract("x", None, {})


def _fixture(name: str) -> str:
    return (HELP / name).read_text(encoding="utf-8")


def _sub(name: str, summary: str = "", entry: str | None = None, body: str = "") -> Subcommand:
    return Subcommand(name, summary, entry, "src", body)


def test_extractors_satisfy_the_protocol() -> None:
    extractors: list[SubcommandExtractor] = [
        HyphenPageExtractor(),
        SectionListExtractor(),
        HelpTextExtractor("two-col", ""),
    ]

    assert [extractor.extract("x", None, {}) for extractor in extractors] == [[], [], []]


# --- hyphen -----------------------------------------------------------------------------


def _page(name: str, synopsis: str, summary: str = "s") -> KnownPage:
    return KnownPage(name, summary, synopsis)


def test_hyphen_page_becomes_a_subcommand() -> None:
    known = {
        "git-commit": _page(
            "git-commit", "     git commit [-a]\n       [--amend]", "Record changes"
        )
    }

    assert HyphenPageExtractor().extract("git", None, known) == [
        Subcommand("commit", "Record changes", "git-commit", "hyphen", "")
    ]


def test_hyphen_page_of_another_command_is_not_a_subcommand() -> None:
    known = {"ssh-keygen": _page("ssh-keygen", "ssh-keygen [-q] [-b bits]")}

    assert HyphenPageExtractor().extract("ssh", None, known) == []


@pytest.mark.parametrize(
    ("key", "synopsis"),
    [
        ("git-commit", "git commitx [-a]"),
        ("git-commit", "git"),
        ("git-commit", ""),
        ("git-", "git  [-a]"),
    ],
)
def test_hyphen_synopsis_must_start_with_parent_and_sub(key: str, synopsis: str) -> None:
    assert HyphenPageExtractor().extract("git", None, {key: _page(key, synopsis)}) == []


def test_hyphen_sub_name_may_contain_hyphens() -> None:
    known = {
        "git-credential-store": _page("git-credential-store", "git credential-store [<options>]")
    }

    assert _names(HyphenPageExtractor().extract("git", None, known)) == ["credential-store"]


def test_hyphen_ignores_other_prefixes() -> None:
    known = {
        "gitk": _page("gitk", "git k"),
        "git": _page("git", "git"),
        "gitx-commit": _page("gitx-commit", "gitx commit"),
    }

    assert HyphenPageExtractor().extract("git", None, known) == []


def test_hyphen_results_are_sorted_and_ignore_parsed() -> None:
    known = {
        "git-push": _page("git-push", "git push"),
        "git-add": _page("git-add", "git add"),
        "git-log": _page("git-log", "git log"),
    }
    parsed = _parsed(("COMMANDS", "     other\n            Does other things."))

    assert _names(HyphenPageExtractor().extract("git", parsed, known)) == ["add", "log", "push"]


# --- section lists ----------------------------------------------------------------------


def test_commands_section_yields_summary_body_and_source() -> None:
    body = _lines(
        "     alpha",
        "            Does alpha. Then more.",
        "     beta",
        "            Does beta. Even more.",
        "     gamma",
        "            Does gamma.",
        "            Second line.",
    )

    subs = _sections(("COMMANDS", body))

    assert subs == [
        Subcommand("alpha", "Does alpha.", None, "section", "Does alpha. Then more."),
        Subcommand("beta", "Does beta.", None, "section", "Does beta. Even more."),
        Subcommand("gamma", "Does gamma.", None, "section", "Does gamma.\nSecond line."),
    ]


def test_launchctl_like_sections_filter_target_specifiers_and_options() -> None:
    targets = _lines(
        "     system/[service-name]",
        "              Targets a system service.",
        "     user/<uid>/[service-name]",
        "              Targets a user service.",
    )
    real = _lines(
        "     bootstrap | bootout domain-target",
        "              Loads or unloads.",
        "     print domain-target",
        "              Prints a target.",
        "     kickstart [-kp] service-target",
        "              Starts a service.",
        "",
        "              -k      Kill it first.",
        "              -p      Print the pid.",
    )

    subs = _sections(("SUBCOMMANDS", targets), ("SUBCOMMANDS", real))

    assert _names(subs) == ["bootstrap", "kickstart", "print"]


def test_verbs_section_keeps_camel_case_and_drops_uppercase() -> None:
    body = _lines(
        "     list [-plist] [device]",
        "              Lists disks.",
        "     info | information device",
        "              Shows a disk.",
        "     eraseDisk format name device",
        "              Erases a disk.",
        "     APFS | ap apfsVerb",
        "              Manages APFS.",
    )

    assert _names(_sections(("VERBS", body))) == ["eraseDisk", "info", "list"]


@pytest.mark.parametrize(
    "heading",
    [
        "OPTIONS INHERITED FROM PARENT COMMANDS",
        "SHELL BUILTIN COMMANDS",
        "CUSTOM EXTERNAL COMMANDS",
        "DEVELOPER COMMANDS",
        "Commands",
        "SUBCOMMAND",
        "OPTIONS",
    ],
)
def test_other_headings_are_not_scanned(heading: str) -> None:
    body = "     alpha\n            Does alpha."

    assert _sections((heading, body)) == []


@pytest.mark.parametrize("term", ["--cache [options]", "-k", "Foo bar", "1st thing"])
def test_terms_failing_the_name_rule_are_dropped(term: str) -> None:
    body = f"     {term}\n            Does a thing."

    assert _sections(("COMMANDS", body)) == []


def test_term_only_item_is_skipped() -> None:
    body = _lines(
        "     This paragraph introduces",
        "     the commands below",
        "",
        "     alpha",
        "            Does alpha.",
    )

    assert _names(_sections(("COMMANDS", body))) == ["alpha"]


def test_first_occurrence_of_a_name_wins() -> None:
    first = "     alpha\n            First one."
    second = "     alpha\n            Second one."

    subs = _sections(("COMMANDS", first + "\n" + second), ("SUBCOMMANDS", second))

    assert [(sub.summary, sub.body) for sub in subs] == [("First one.", "First one.")]


def test_section_list_without_parsed_page_is_empty() -> None:
    assert SectionListExtractor().extract("x", None, {}) == []


# --- help text --------------------------------------------------------------------------


@pytest.mark.parametrize("profile", ["nope", ""])
def test_unknown_help_profile_raises(profile: str) -> None:
    with pytest.raises(ValueError, match="unknown help profile"):
        HelpTextExtractor(profile, "x")


def _probes(*rows: tuple[str, str]) -> list[Subcommand]:
    return [Subcommand(name, summary, None, "probe", "") for name, summary in rows]


def test_two_col_verbs_strips_parentheses_and_drops_unnamed_rows() -> None:
    assert _probe("two-col", _fixture("two_col_verbs.txt")) == _probes(
        ("eraseDisk", "Wipe a whole disk"),
        ("list", "List the items of a volume"),
        ("mount", "Attach a volume to the tree"),
    )


def test_two_col_tabs_are_expanded_and_specifiers_dropped() -> None:
    assert _probe("two-col", _fixture("two_col_tabs.txt")) == _probes(
        ("bootstrap", "Load a service into a domain."),
        ("kickstart", "Start a service now."),
        ("print", "Show the state of a target."),
    )


def test_two_col_first_occurrence_wins() -> None:
    assert _probe("two-col", _fixture("two_col_usage.txt")) == _probes(
        ("read", "summary a"), ("write", "summary c")
    )


def test_two_col_ignores_continuations_and_single_spaced_lines() -> None:
    text = _lines("  alpha    Does alpha.", "      continues the text here", "  beta gamma delta")

    assert _probe("two-col", text) == _probes(("alpha", "Does alpha."))


def test_git_list_skips_aliases_and_keeps_later_blocks() -> None:
    assert _probe("git-list", _fixture("git_list.txt")) == _probes(
        ("add", "Stage files for the next record"),
        ("commit", "Record staged work as a revision"),
        ("frobnicate", ""),
        ("hash-thing", "Compute an object id"),
        ("zap", ""),
    )


def test_git_list_accepts_indented_lines_before_any_heading() -> None:
    assert _probe("git-list", "  first    Does first.") == _probes(("first", "Does first."))


def test_brew_commands_keeps_bare_names_only() -> None:
    assert _probe("brew-commands", _fixture("brew_commands.txt")) == _probes(
        ("analytics", ""), ("frob", ""), ("install", "")
    )


_ROBUST_TEXT = {
    "two-col": "Usage: x\n  alpha    Does alpha � here.\n  beta    Does beta.",
    "git-list": "Heading\n  alpha    Does alpha � here.\n  beta    Does beta.",
    "brew-commands": "==> Heading\nalpha\nbeta",
}


@pytest.mark.parametrize("profile", HELP_PROFILES)
def test_line_ends_do_not_change_the_result(profile: str) -> None:
    text = _ROBUST_TEXT[profile]
    expected = _probe(profile, text)

    assert len(expected) == 2
    assert _probe(profile, text + "\n") == expected
    assert _probe(profile, text.replace("\n", "\r\n")) == expected
    assert all("\r" not in sub.summary for sub in _probe(profile, text.replace("\n", "\r\n")))


@pytest.mark.parametrize("profile", ["two-col", "git-list"])
def test_replacement_character_is_kept_in_summaries(profile: str) -> None:
    assert "�" in _probe(profile, _ROBUST_TEXT[profile])[0].summary


@pytest.mark.parametrize("profile", HELP_PROFILES)
def test_empty_text_yields_nothing(profile: str) -> None:
    assert _probe(profile, "") == []


def test_two_col_long_summary_is_cut_and_right_stripped() -> None:
    summary = ("word " * 60).strip()

    subs = _probe("two-col", f"  alpha    {summary}")

    assert subs[0].summary == ("word " * 40).rstrip()


def _assert_well_formed(subs: list[Subcommand]) -> None:
    names = _names(subs)
    assert names == sorted(set(names))
    assert all(NAME_RULE.fullmatch(name) for name in names)


@given(text=st.text(), profile=st.sampled_from(HELP_PROFILES))
def test_help_text_extraction_is_total(text: str, profile: str) -> None:
    _assert_well_formed(_probe(profile, text))


@given(body=st.text())
def test_section_extraction_is_total(body: str) -> None:
    _assert_well_formed(_sections(("COMMANDS", body)))


# --- merge ------------------------------------------------------------------------------


def test_merge_takes_each_field_from_the_first_contributor_that_has_it() -> None:
    curated = [Subcommand("commit", "", None, "curated")]
    probe = [Subcommand("commit", "from probe", None, "probe")]
    section = [Subcommand("commit", "from section", None, "section", "long")]
    hyphen = [Subcommand("commit", "from hyphen", "git-commit", "hyphen")]

    assert merge_subcommands([curated, probe, section, hyphen]) == [
        Subcommand("commit", "from probe", "git-commit", "curated", "long")
    ]


def test_merge_whitespace_only_text_does_not_count() -> None:
    first = [Subcommand("a", "  ", None, "p", " \n")]
    second = [Subcommand("a", "x", None, "q", "y")]

    assert merge_subcommands([first, second]) == [Subcommand("a", "x", None, "p", "y")]


def test_merge_is_a_sorted_union() -> None:
    top = [_sub("zeta"), _sub("beta")]
    low = [_sub("alpha"), _sub("beta", "low")]

    assert _names(merge_subcommands([top, low])) == ["alpha", "beta", "zeta"]


@pytest.mark.parametrize("lists", [[], [[], []]])
def test_merge_of_nothing_is_empty(lists: list[list[Subcommand]]) -> None:
    assert merge_subcommands(lists) == []


def test_merge_duplicates_in_one_list_prefer_the_first_occurrence() -> None:
    both = [_sub("a", "first"), _sub("a", "second", "page-a")]

    assert merge_subcommands([both]) == [Subcommand("a", "first", "page-a", "src", "")]
