"""Placeholder tokenizer: segments, escapes, unclosed and empty placeholders, properties."""

from __future__ import annotations

import itertools
from dataclasses import FrozenInstanceError

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

import leva.placeholders as placeholders
from leva.placeholders import (
    EMPTY_PLACEHOLDER,
    UNCLOSED_PLACEHOLDER,
    Segment,
    names,
    parse,
    problems,
    to_plain,
)


def test_parse_splits_placeholder_from_text() -> None:
    assert parse("tar -xzf {{archive.tar.gz}}") == [
        Segment("tar -xzf ", False),
        Segment("archive.tar.gz", True),
    ]


def test_parse_empty_string_gives_no_segments() -> None:
    assert parse("") == []


def test_parse_plain_text_is_one_literal() -> None:
    assert parse("ls -la") == [Segment("ls -la", False)]


def test_parse_placeholder_only() -> None:
    assert parse("{{file}}") == [Segment("file", True)]


def test_parse_adjacent_placeholders() -> None:
    assert parse("{{a}}{{b}}") == [Segment("a", True), Segment("b", True)]
    assert parse("x{{a}}{{b}}y") == [
        Segment("x", False),
        Segment("a", True),
        Segment("b", True),
        Segment("y", False),
    ]


def test_names_are_unique_in_order_of_first_appearance() -> None:
    cmd = "cp {{f}} {{f}}.bak {{g}}"
    assert names(cmd) == ["f", "g"]
    assert [s.text for s in parse(cmd) if s.is_placeholder] == ["f", "f", "g"]


def test_escaped_opening_is_literal() -> None:
    cmd = r"echo \{{x}}"
    assert parse(cmd) == [Segment("echo {{x}}", False)]
    assert to_plain(cmd) == "echo {{x}}"
    assert names(cmd) == []
    assert problems(cmd) == []


def test_escape_then_placeholder() -> None:
    assert parse(r"\{{a}} {{b}}") == [Segment("{{a}} ", False), Segment("b", True)]


def test_lone_backslash_is_literal() -> None:
    assert parse(r"a\b") == [Segment(r"a\b", False)]


def test_double_backslash_before_braces_keeps_one_backslash_and_escapes() -> None:
    assert parse("\\\\{{a}}") == [Segment("\\{{a}}", False)]


def test_unclosed_placeholder_is_literal() -> None:
    assert parse("echo {{x") == [Segment("echo {{x", False)]
    assert problems("echo {{x") == [UNCLOSED_PLACEHOLDER]
    assert parse("{{a}} {{b") == [Segment("a", True), Segment(" {{b", False)]


def test_unclosed_swallows_the_rest_as_literal() -> None:
    assert parse("x {{ y") == [Segment("x {{ y", False)]
    assert parse(r"{{a \{{b") == [Segment(r"{{a \{{b", False)]
    assert problems(r"{{a \{{b") == [UNCLOSED_PLACEHOLDER]


def test_inner_opening_belongs_to_the_placeholder() -> None:
    assert parse("{{a {{b}}") == [Segment("a {{b", True)]
    assert problems("{{a {{b}}") == []


def test_empty_placeholder_stays_literal() -> None:
    assert parse("a {{}} b") == [Segment("a {{}} b", False)]
    assert problems("a {{}} b {{ }}") == [EMPTY_PLACEHOLDER, EMPTY_PLACEHOLDER]


def test_blank_placeholder_keeps_its_whitespace() -> None:
    assert parse("{{ }}") == [Segment(" ", True)]


def test_problems_in_source_order() -> None:
    assert problems("{{}} {{c") == [EMPTY_PLACEHOLDER, UNCLOSED_PLACEHOLDER]
    assert problems("ok {{x}}") == []


def test_problem_messages_are_stable_contract() -> None:
    assert EMPTY_PLACEHOLDER == "empty placeholder"
    assert UNCLOSED_PLACEHOLDER == "unclosed placeholder"


def test_stray_closers_are_literal() -> None:
    assert parse("awk '{print}}'") == [Segment("awk '{print}}'", False)]
    assert parse("}} {{a}}") == [Segment("}} ", False), Segment("a", True)]


def test_triple_braces_end_at_first_closer() -> None:
    assert parse("{{{a}}}") == [Segment("{a", True), Segment("}", False)]


def test_unicode_placeholder_and_text() -> None:
    assert parse("cp {{fichier_été}} ✓") == [
        Segment("cp ", False),
        Segment("fichier_été", True),
        Segment(" ✓", False),
    ]
    assert to_plain("cp {{fichier_été}} ✓") == "cp fichier_été ✓"


def test_to_plain_removes_delimiters() -> None:
    assert to_plain("tar -czf {{archive}}.tgz {{dir}}") == "tar -czf archive.tgz dir"


def test_segment_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match=r"Segment\.text must be non-empty"):
        Segment("", False)


def test_segment_is_frozen_slotted_and_hashable() -> None:
    segment = Segment("a", True)
    with pytest.raises(FrozenInstanceError):
        segment.text = "b"  # type: ignore[misc]  # frozen dataclass: assignment is the point
    assert not hasattr(segment, "__dict__")
    assert hash(segment) == hash(Segment("a", True))
    assert {segment: 1}[Segment("a", True)] == 1


def test_public_api_is_sorted_all() -> None:
    assert placeholders.__all__ == [
        "EMPTY_PLACEHOLDER",
        "UNCLOSED_PLACEHOLDER",
        "Segment",
        "names",
        "parse",
        "problems",
        "to_plain",
    ]


SAFE_TEXT = st.text(alphabet=st.characters(exclude_characters="{}\\", exclude_categories=("Cs",)))
SAFE_NAME = st.text(
    alphabet=st.characters(exclude_characters="{}\\", exclude_categories=("Cs",)),
    min_size=1,
)
PARTS = st.lists(
    st.one_of(
        st.tuples(st.just(False), SAFE_TEXT),
        st.tuples(st.just(True), SAFE_NAME),
    )
)


def _expected_segments(parts: list[tuple[bool, str]]) -> list[Segment]:
    expected: list[Segment] = []
    for is_placeholder, text in parts:
        if not text:
            continue
        if not is_placeholder and expected and not expected[-1].is_placeholder:
            expected[-1] = Segment(expected[-1].text + text, False)
        else:
            expected.append(Segment(text, is_placeholder))
    return expected


@given(PARTS)
def test_parse_round_trips_constructed_commands(parts: list[tuple[bool, str]]) -> None:
    cmd = "".join(f"{{{{{text}}}}}" if is_placeholder else text for is_placeholder, text in parts)
    assert parse(cmd) == _expected_segments(parts)
    assert to_plain(cmd) == "".join(text for _, text in parts)


@given(st.text())
@example("{{{a}}}")
@example("\\\\{{a}}")
def test_segments_are_non_empty_and_literals_merged(text: str) -> None:
    segments = parse(text)
    assert all(s.text for s in segments)
    assert all(s.is_placeholder or t.is_placeholder for s, t in itertools.pairwise(segments))
    assert "".join(s.text for s in segments) == to_plain(text)
    placeholder_texts = {s.text for s in segments if s.is_placeholder}
    found = names(text)
    assert len(found) == len(set(found))
    assert set(found) == placeholder_texts


@given(st.text(alphabet=st.characters(exclude_characters="{}", exclude_categories=("Cs",))))
def test_brace_free_text_is_unchanged(text: str) -> None:
    assert to_plain(text) == text
    assert problems(text) == []


@given(st.text(alphabet="{}\\a "))
@example("\\{{{{}}}}\\\\{{ {{")
def test_nasty_brace_text_is_handled_totally(text: str) -> None:
    segments = parse(text)
    assert len(to_plain(text)) <= len(text)
    assert set(names(text)) <= {s.text for s in segments if s.is_placeholder}
    found = problems(text)
    assert set(found) <= {EMPTY_PLACEHOLDER, UNCLOSED_PLACEHOLDER}
    assert UNCLOSED_PLACEHOLDER not in found[:-1]
