"""Tests for the FTS5 query sanitiser (`fts_query`)."""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from leva.repo import MAX_FTS_TOKENS
from leva.repo._fts import fts_query

# An FTS5 string: double quotes around text whose own quotes are doubled.
QUOTED_STRING = re.compile(r'"(?:[^"]|"")*"')
QUOTED_STRINGS = re.compile(r'"(?:[^"]|"")*"(?: "(?:[^"]|"")*")*')


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("git commit", '"git" "commit"'),
        ("git  \t commit\n", '"git" "commit"'),
        ("ls", '"ls"'),
        ('a"b', '"a""b"'),
        ('"', '""""'),
        ('""', '""""""'),
        ("x*", '"x*"'),
        ("git-commit", '"git-commit"'),
        ("name:ls", '"name:ls"'),
        ("NEAR(a b)", '"NEAR(a" "b)"'),
        ("a OR b", '"a" "OR" "b"'),
        ("^ls", '"^ls"'),
        ("café ☕", '"café" "☕"'),
        ("ls\x00cat", '"ls" "cat"'),
    ],
)
def test_fts_query_quotes_every_token(text: str, expected: str) -> None:
    assert fts_query(text) == expected


@pytest.mark.parametrize("text", ["", " ", "\t\n  ", "\N{NO-BREAK SPACE}", "\x00", " \x00 "])
def test_fts_query_returns_none_without_tokens(text: str) -> None:
    assert fts_query(text) is None


@pytest.mark.parametrize("text", ["\ud800", "ls\udfff", "git \ud800 commit", '"\ud800"'])
def test_fts_query_returns_none_for_text_that_cannot_be_encoded(text: str) -> None:
    assert fts_query(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("NEAR/3", '"NEAR/3"'),
        ("{name}: x", '"{name}:" "x"'),
        ("x OR", '"x" "OR"'),
        ("“x”", '"“x”"'),
        ("a\\b", '"a\\b"'),
    ],
)
def test_fts_query_keeps_operator_look_alikes_as_plain_text(text: str, expected: str) -> None:
    assert fts_query(text) == expected


def test_fts_query_keeps_only_the_first_tokens() -> None:
    words = [f"w{i}" for i in range(MAX_FTS_TOKENS + 20)]

    result = fts_query(" ".join(words))

    assert result == " ".join(f'"{word}"' for word in words[:MAX_FTS_TOKENS])


def test_fts_query_keeps_exactly_the_cap() -> None:
    words = [f"w{i}" for i in range(MAX_FTS_TOKENS)]

    assert fts_query(" ".join(words)) == " ".join(f'"{word}"' for word in words)


@given(st.text())
def test_fts_query_is_none_exactly_when_no_tokens(text: str) -> None:
    assert (fts_query(text) is None) == (text.replace("\x00", " ").split() == [])


@given(st.text(min_size=1))
def test_fts_query_is_only_quoted_strings(text: str) -> None:
    result = fts_query(text)
    if result is None:
        return
    assert QUOTED_STRINGS.fullmatch(result)
    assert 1 <= len(QUOTED_STRING.findall(result)) <= MAX_FTS_TOKENS
