"""Tests for `leva.manparse.strip_overstrike`."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from leva.manparse import strip_overstrike


def test_strip_overstrike_bold_becomes_plain() -> None:
    assert strip_overstrike("N\bNA\bAM\bME\bE") == "NAME"


def test_strip_overstrike_underline_becomes_plain() -> None:
    assert strip_overstrike("_\bf_\bi_\bl_\be") == "file"


def test_strip_overstrike_mixed_line_keeps_plain_chars() -> None:
    assert strip_overstrike("a B\bB c _\bd e") == "a B c d e"


def test_strip_overstrike_triple_overstrike_keeps_last_char() -> None:
    assert strip_overstrike("X\bX\bX") == "X"


def test_strip_overstrike_backspace_at_text_start_is_removed() -> None:
    assert strip_overstrike("\bab") == "ab"


def test_strip_overstrike_backspace_after_newline_is_removed_and_newline_kept() -> None:
    assert strip_overstrike("a\n\bb") == "a\nb"


def test_strip_overstrike_keeps_newlines_between_overstruck_lines() -> None:
    assert strip_overstrike("A\bA\nB\bB\n") == "A\nB\n"


def test_strip_overstrike_plain_text_is_unchanged() -> None:
    text = "  plain text\n\tsecond line\n"
    assert strip_overstrike(text) == text


def test_strip_overstrike_empty_text_is_empty() -> None:
    assert strip_overstrike("") == ""


@given(st.text().filter(lambda text: "\x08" not in text))
def test_strip_overstrike_text_without_backspace_is_identity(text: str) -> None:
    assert strip_overstrike(text) == text


@given(st.text(alphabet=st.sampled_from(["a", "_", "\b", "\n", " "])))
def test_strip_overstrike_result_never_contains_backspace(text: str) -> None:
    assert "\x08" not in strip_overstrike(text)
