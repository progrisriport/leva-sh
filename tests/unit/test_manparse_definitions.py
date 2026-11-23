"""Tests for `leva.manparse.definition_items`: layout-driven definition lists (D-027)."""

from __future__ import annotations

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from leva.manparse import DefinitionItem, definition_items


def _body(*lines: str) -> str:
    return "\n".join(lines)


def test_simple_list_gives_stripped_terms_and_dedented_descriptions() -> None:
    body = _body(
        "     -a",
        "            Show all.",
        "",
        "     -b",
        "            Be brief.",
    )

    assert definition_items(body) == [
        DefinitionItem(("-a",), "Show all."),
        DefinitionItem(("-b",), "Be brief."),
    ]


def test_indents_are_relative_to_the_body() -> None:
    shifted = _body(
        "       -a",
        "                Show all.",
        "",
        "       -b",
        "                Be brief.",
    )
    plain = _body(
        "     -a",
        "            Show all.",
        "",
        "     -b",
        "            Be brief.",
    )

    assert definition_items(shifted) == definition_items(plain)


def test_consecutive_term_lines_are_grouped() -> None:
    body = _body(
        "     . file [ arg ... ]",
        "     source file [ arg ... ]",
        "            Read commands from file.",
    )

    assert definition_items(body) == [
        DefinitionItem(
            (". file [ arg ... ]", "source file [ arg ... ]"), "Read commands from file."
        )
    ]


def test_blank_line_between_base_lines_splits_items() -> None:
    body = _body("     one", "", "     two", "            About two.")

    assert definition_items(body) == [
        DefinitionItem(("one",), ""),
        DefinitionItem(("two",), "About two."),
    ]


def test_inline_term_starts_the_description_on_its_line() -> None:
    body = _body(
        "     -a      show all",
        "            continued text",
        "     -b",
        "            Be brief.",
    )

    assert definition_items(body) == [
        DefinitionItem(("-a",), "show all\ncontinued text"),
        DefinitionItem(("-b",), "Be brief."),
    ]


def test_base_line_after_an_inline_term_starts_a_new_item() -> None:
    body = _body("     -a  first", "     -b  second")

    assert definition_items(body) == [
        DefinitionItem(("-a",), "first"),
        DefinitionItem(("-b",), "second"),
    ]


def test_inline_term_is_right_stripped() -> None:
    body = _body("     -a\t  show all")

    assert definition_items(body) == [DefinitionItem(("-a",), "show all")]


def test_grouped_terms_may_end_with_an_inline_term() -> None:
    body = _body("     one", "     two  text")

    assert definition_items(body) == [DefinitionItem(("one", "two"), "text")]


def test_nested_list_and_paragraphs_stay_in_the_description() -> None:
    body = _body(
        "     alias",
        "            text",
        "",
        "            more text",
        "            -x       nested",
        "                     deeper",
    )

    assert definition_items(body) == [
        DefinitionItem(
            ("alias",),
            "text\n\nmore text\n-x       nested\n         deeper",
        )
    ]


def test_deeper_lines_before_the_first_term_are_ignored() -> None:
    body = _body("            stray", "", "     -a", "            Show all.")

    assert definition_items(body) == [DefinitionItem(("-a",), "Show all.")]


@pytest.mark.parametrize("body", ["", "\n\n", "   \n \t \n"])
def test_blank_body_gives_no_items(body: str) -> None:
    assert definition_items(body) == []


def test_base_lines_separated_by_blanks_give_empty_descriptions() -> None:
    body = _body("     one", "", "     two", "", "     three")

    assert definition_items(body) == [
        DefinitionItem(("one",), ""),
        DefinitionItem(("two",), ""),
        DefinitionItem(("three",), ""),
    ]


def test_single_spaces_do_not_make_a_term_inline() -> None:
    body = _body("     print [ -abc ] [ arg ... ]", "            Print things.")

    assert definition_items(body) == [
        DefinitionItem(("print [ -abc ] [ arg ... ]",), "Print things.")
    ]


def test_trailing_blank_lines_and_trailing_spaces_are_trimmed() -> None:
    body = _body("     -a", "            Show all.   ", "", "")

    assert definition_items(body) == [DefinitionItem(("-a",), "Show all.")]


def test_blank_line_after_an_inline_first_line_is_a_paragraph_break() -> None:
    body = _body("     -a  first", "", "            second")

    assert definition_items(body) == [DefinitionItem(("-a",), "first\n\nsecond")]


@example("\x0b\x0c a")
@example("a  b\r\n  c")
@given(st.text(alphabet=st.characters(exclude_categories=("Cs",))))
def test_definition_items_never_raises_and_terms_are_not_blank(text: str) -> None:
    for item in definition_items(text):
        assert item.terms
        assert all(term.strip() for term in item.terms)


@pytest.mark.parametrize(
    ("terms", "description"),
    [((), ""), (("  ",), ""), (("ok", ""), "")],
)
def test_definition_item_rejects_empty_or_blank_terms(
    terms: tuple[str, ...], description: str
) -> None:
    with pytest.raises(ValueError, match="terms"):
        DefinitionItem(terms, description)
