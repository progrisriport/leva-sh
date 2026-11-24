"""Parse the NAME section of a man page into names and a one-line summary."""

from __future__ import annotations

import re
from typing import Final

from leva.model import is_name

MAX_SUMMARY: Final = 200
_SEPARATOR: Final = re.compile(r"\s+(?:--|-|\u2013|\u2014)\s+")
_SENTENCE: Final = re.compile(r"(.+?[.!?])(?=\s|$)")


def parse_name(body: str, name_hint: str) -> tuple[tuple[str, ...], str]:
    """Split a NAME body into the command names and the summary.

    The body is collapsed to one line, then cut at the first dash separator (` - `, ` -- `,
    an en dash or an em dash, each between whitespace). Names are the comma-separated parts
    before it that are valid names, without duplicates, in order.

    Pre: `name_hint` is a valid name.
    Post: names are never empty (`(name_hint,)` when none is valid); the summary is one line
    of at most `MAX_SUMMARY` characters, empty when there is no separator.

    Args:
        body: Body of the NAME section as rendered; may be empty.
        name_hint: Fallback name used when the body yields no valid name.

    Returns:
        The names and the summary.
    """
    text = " ".join(body.split())
    match = _SEPARATOR.search(text)
    names_part, summary = (
        (text, "") if match is None else (text[: match.start()], text[match.end() :])
    )
    names = _names(names_part)
    return (names or (name_hint,)), summary[:MAX_SUMMARY].rstrip()


def first_sentence(text: str) -> str:
    """Return the first sentence of `text` on one line, cut to `MAX_SUMMARY` characters.

    A sentence ends at ``.``, ``!`` or ``?`` followed by whitespace or the end, so an
    abbreviation such as ``e.g.`` ends it early; without an end the whole text is used.

    Post: one line of at most `MAX_SUMMARY` characters, right-stripped; empty for blank `text`.

    Args:
        text: Prose that may span several lines.

    Returns:
        The first sentence, whitespace-flattened.
    """
    flat = " ".join(text.split())
    match = _SENTENCE.match(flat)
    return (match.group(1) if match else flat)[:MAX_SUMMARY].rstrip()


def _names(part: str) -> tuple[str, ...]:
    """Return the valid comma-separated names of `part`, deduplicated in order."""
    candidates = (item.strip() for item in part.split(","))
    return tuple(dict.fromkeys(item for item in candidates if is_name(item)))
