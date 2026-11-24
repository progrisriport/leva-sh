"""Tests for `leva.manparse.parse_man`: header/footer, sections and NAME."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from leva.manparse import ParsedMan, parse_man
from leva.model import Section

FIXTURES = Path(__file__).parent.parent / "fixtures" / "man"
GOLDEN = sorted(FIXTURES.glob("parse_*.json"))
HEADER = "LEVA-T(1)        General Commands Manual        LEVA-T(1)"
FOOTER = "macOS 27.0           November 1, 2026           macOS 27.0"


def _page(*inner: str) -> str:
    """Wrap `inner` lines in a header, a blank line and a footer."""
    return "\n".join([HEADER, "", *inner, "", FOOTER, ""])


def _name_page(*name_lines: str) -> str:
    return _page("NAME", *(f"     {line}" for line in name_lines), "", "DESCRIPTION", "     Text.")


def _headings(parsed: ParsedMan) -> list[str]:
    return [section.heading for section in parsed.sections]


def test_golden_fixtures_exist() -> None:
    assert len(GOLDEN) >= 10


@pytest.mark.parametrize("expected_file", GOLDEN, ids=lambda path: path.stem)
def test_parse_man_matches_golden_fixture(expected_file: Path) -> None:
    expected = json.loads(expected_file.read_text(encoding="utf-8"))
    text = expected_file.with_suffix(".txt").read_text(encoding="utf-8")

    parsed = parse_man(text, name_hint=expected["name_hint"])

    assert list(parsed.names) == expected["names"]
    assert parsed.summary == expected["summary"]
    assert parsed.redirect_to == expected["redirect_to"]
    assert [dataclasses.asdict(section) for section in parsed.sections] == expected["sections"]


# --- header, footer and section splitting ---------------------------------------------------


def test_header_and_footer_dropped_even_though_they_look_like_headings() -> None:
    parsed = parse_man(_page("NAME", "     x - y"), name_hint="x")

    assert _headings(parsed) == ["NAME"]
    assert HEADER not in parsed.sections[0].body
    assert FOOTER not in parsed.sections[0].body


@pytest.mark.parametrize("text", ["only one line", "first\nsecond", "\n\nonly\n\n"])
def test_text_too_short_for_header_and_body_gives_empty_description(text: str) -> None:
    parsed = parse_man(text, name_hint="x")

    assert parsed.sections == (Section("DESCRIPTION", "", 0),)


def test_blank_only_text_gives_empty_description() -> None:
    assert parse_man("\n   \n\n", name_hint="x").sections == (Section("DESCRIPTION", "", 0),)


def test_preamble_before_first_heading_becomes_leading_description() -> None:
    parsed = parse_man(_page("     intro line", "NAME", "     x - y"), name_hint="x")

    assert parsed.sections == (
        Section("DESCRIPTION", "     intro line", 0),
        Section("NAME", "     x - y", 1),
    )


def test_blank_preamble_is_dropped() -> None:
    parsed = parse_man(_page("", "  ", "NAME", "     x - y"), name_hint="x")

    assert _headings(parsed) == ["NAME"]
    assert parsed.sections[0].ord == 0


def test_text_without_headings_is_one_description_of_the_inner_text() -> None:
    parsed = parse_man(_page("     one", "", "       two"), name_hint="x")

    assert parsed.sections == (Section("DESCRIPTION", "     one\n\n       two", 0),)


def test_body_keeps_indentation_and_internal_blank_lines_and_trims_edges() -> None:
    parsed = parse_man(_page("SYNOPSIS", "", "     a", "", "         b   ", ""), name_hint="x")

    assert parsed.sections[0].body == "     a\n\n         b"


def test_section_with_no_body_lines_has_empty_body() -> None:
    parsed = parse_man(_page("EMPTY", "NEXT", "     text"), name_hint="x")

    assert parsed.sections == (Section("EMPTY", "", 0), Section("NEXT", "     text", 1))


def test_letterless_column_zero_line_is_body() -> None:
    parsed = parse_man(_page("HEAD", "-----", "     text"), name_hint="x")

    assert parsed.sections == (Section("HEAD", "-----\n     text", 0),)


def test_headings_are_stripped_of_trailing_space() -> None:
    parsed = parse_man(_page("NAME   ", "     x - y"), name_hint="x")

    assert parsed.sections[0].heading == "NAME"


def test_unicode_line_separators_split_lines_without_error() -> None:
    parsed = parse_man(f"{HEADER}\n\nNAME\x0c     x - y\n\n{FOOTER}", name_hint="x")

    assert parsed.names == ("x",)


# --- NAME -----------------------------------------------------------------------------------


@pytest.mark.parametrize("separator", ["-", "--", "\N{EN DASH}", "\N{EM DASH}"])
def test_name_separators(separator: str) -> None:
    parsed = parse_man(_name_page(f"foo {separator} does a thing"), name_hint="hint")

    assert (parsed.names, parsed.summary) == (("foo",), "does a thing")


def test_hyphen_inside_a_name_is_not_a_separator() -> None:
    parsed = parse_man(_name_page("a-b - c"), name_hint="hint")

    assert (parsed.names, parsed.summary) == (("a-b",), "c")


def test_dash_without_following_space_is_not_a_separator() -> None:
    parsed = parse_man(_name_page("a -b"), name_hint="hint")

    assert parsed.names == ("hint",)  # "a -b" has whitespace, so no valid name remains
    assert parsed.summary == ""


@pytest.mark.parametrize("heading", ["Name", "name", "NaMe"])
def test_name_heading_is_case_insensitive(heading: str) -> None:
    parsed = parse_man(_page(heading, "     foo - bar"), name_hint="hint")

    assert (parsed.names, parsed.summary) == (("foo",), "bar")


def test_summary_longer_than_200_chars_is_cut_and_rstripped() -> None:
    summary = "w" * 199 + " " + "z" * 50
    parsed = parse_man(_name_page(f"foo - {summary}"), name_hint="hint")

    assert parsed.summary == "w" * 199
    assert len(parsed.summary) <= 200


def test_summary_of_exactly_200_chars_is_kept() -> None:
    parsed = parse_man(_name_page(f"foo - {'s' * 200}"), name_hint="hint")

    assert parsed.summary == "s" * 200


def test_summary_whitespace_is_collapsed_across_lines() -> None:
    parsed = parse_man(_name_page("foo - first   part", "second\tpart"), name_hint="hint")

    assert parsed.summary == "first part second part"


def test_names_with_inner_whitespace_are_dropped() -> None:
    parsed = parse_man(_name_page("foo bar, baz - x"), name_hint="hint")

    assert parsed.names == ("baz",)


def test_duplicate_names_are_deduplicated_keeping_order() -> None:
    parsed = parse_man(_name_page("b, a, b, a, c - x"), name_hint="hint")

    assert parsed.names == ("b", "a", "c")


def test_all_names_invalid_falls_back_to_name_hint() -> None:
    parsed = parse_man(_name_page("foo bar, , baz qux - x"), name_hint="hint")

    assert parsed.names == ("hint",)
    assert parsed.summary == "x"


def test_name_hint_is_not_added_when_names_are_valid() -> None:
    parsed = parse_man(_name_page("foo - x"), name_hint="hint")

    assert parsed.names == ("foo",)


def test_first_name_section_wins() -> None:
    page = _page("NAME", "     first - one", "Name", "     second - two")

    parsed = parse_man(page, name_hint="hint")

    assert (parsed.names, parsed.summary) == (("first",), "one")
    assert _headings(parsed) == ["NAME", "Name"]


def test_empty_name_section_falls_back_to_name_hint() -> None:
    parsed = parse_man(_page("NAME", "DESCRIPTION", "     text"), name_hint="hint")

    assert (parsed.names, parsed.summary) == (("hint",), "")


def test_page_without_name_section_uses_name_hint() -> None:
    parsed = parse_man(_page("DESCRIPTION", "     text - not a name"), name_hint="hint")

    assert (parsed.names, parsed.summary) == (("hint",), "")


# --- invariants and errors ------------------------------------------------------------------


@pytest.mark.parametrize("hint", ["", "a b", "a\tb", " "])
def test_parse_man_rejects_invalid_name_hint(hint: str) -> None:
    with pytest.raises(ValueError, match="name_hint"):
        parse_man(_page("NAME", "     x - y"), name_hint=hint)


def test_redirect_to_is_never_set() -> None:
    assert parse_man(_page("NAME", "     x - y"), name_hint="x").redirect_to is None


def _valid(**changes: object) -> ParsedMan:
    base = ParsedMan(names=("x",), summary="s", sections=(Section("A", "", 0),), redirect_to=None)
    return dataclasses.replace(base, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"names": ()},
        {"names": ("",)},
        {"names": ("a b",)},
        {"names": ("ok", "a\nb")},
        {"summary": "s" * 201},
        {"summary": "a\nb"},
        {"summary": "a\rb"},
        {"summary": "a\x0bb"},
        {"summary": "trailing newline\n"},
        {"summary": "trailing return\r"},
        {"summary": "next line\x85"},
        {"summary": "line" + chr(0x2028) + "separator"},
        {"sections": (Section("A", "", 1),)},
        {"sections": (Section("A", "", 0), Section("B", "", 2))},
        {"sections": (Section("A", "", 1), Section("B", "", 0))},
    ],
)
def test_parsed_man_rejects_broken_invariants(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="ParsedMan"):
        _valid(**changes)


def test_parsed_man_accepts_summary_of_200_chars_and_no_sections() -> None:
    parsed = _valid(summary="s" * 200, sections=())

    assert len(parsed.summary) == 200


def test_parsed_man_is_frozen_and_slotted() -> None:
    parsed = _valid()

    with pytest.raises(dataclasses.FrozenInstanceError):
        parsed.summary = "other"  # type: ignore[misc]  # frozen on purpose
    assert not hasattr(parsed, "__dict__")


# --- scale and robustness -------------------------------------------------------------------


def test_input_over_one_megabyte_is_split_correctly() -> None:
    count = 20_000
    inner: list[str] = []
    for index in range(count):
        inner.extend([f"SECTION {index}", f"     body line {index} with some padding text", ""])
    text = "\n".join([HEADER, "", *inner, FOOTER])
    assert len(text) > 1_000_000

    parsed = parse_man(text, name_hint="x")

    assert len(parsed.sections) == count
    assert parsed.sections[0].heading == "SECTION 0"
    assert parsed.sections[-1].heading == f"SECTION {count - 1}"
    assert parsed.sections[-1].ord == count - 1
    assert parsed.sections[5].body == "     body line 5 with some padding text"


def _check_invariants(parsed: ParsedMan) -> None:
    assert parsed.names
    assert all(name and not any(c.isspace() for c in name) for name in parsed.names)
    assert len(parsed.summary) <= 200
    assert len(parsed.summary.splitlines()) <= 1
    assert "\n" not in parsed.summary
    assert "\r" not in parsed.summary
    assert parsed.sections
    assert [section.ord for section in parsed.sections] == list(range(len(parsed.sections)))
    assert parsed.redirect_to is None


TEXT = st.text(alphabet=st.characters(exclude_categories=("Cs",)))
HINT = st.text(alphabet=st.characters(exclude_categories=("Cs", "Z", "Cc")), min_size=1).filter(
    lambda value: not any(char.isspace() for char in value)
)
MANDOC_LINES = st.lists(
    st.one_of(
        st.sampled_from(["", "NAME", "DESCRIPTION", "Name", "____", "   Sub heading"]),
        st.builds("{}{}".format, st.sampled_from(["", " " * 3, " " * 5, " " * 10]), TEXT),
        st.builds("     {} - {}".format, TEXT, TEXT),
    ),
    max_size=40,
).map("\n".join)


@given(text=TEXT, hint=HINT)
@example(text="", hint="x")
@example(text="a\x0cb\x0b\x1c\x85\N{LINE SEPARATOR}c", hint="x")
@example(text="NAME\n     a - b\n\nlast", hint="x")
def test_parse_man_never_raises_on_arbitrary_text(text: str, hint: str) -> None:
    _check_invariants(parse_man(text, name_hint=hint))


@given(text=MANDOC_LINES, hint=HINT)
def test_parse_man_never_raises_on_mandoc_like_text(text: str, hint: str) -> None:
    _check_invariants(parse_man(f"{HEADER}\n\n{text}\n\n{FOOTER}", name_hint=hint))
