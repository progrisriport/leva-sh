"""Turn the SHELL BUILTIN COMMANDS section of a parsed shell man page into builtin docs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from leva.manparse._definitions import DefinitionItem, definition_items
from leva.manparse._name import MAX_SUMMARY, is_name
from leva.manparse._sections import ParsedMan

_SENTENCE = re.compile(r"(.+?[.!?])(?=\s|$)")


@dataclass(frozen=True, slots=True)
class BuiltinDoc:
    """The documentation of one shell builtin.

    Attributes:
        name: The builtin's name; non-empty, no whitespace.
        synopsis: The item's term lines whose first token is `name`, joined with newlines.
        summary: One line of at most 200 characters.
        body: The item's description.

    Raises:
        ValueError: If `name` is empty or has whitespace, or `summary` is longer than 200
            characters or has a line break.
    """

    name: str
    synopsis: str
    summary: str
    body: str

    def __post_init__(self) -> None:
        if not is_name(self.name):
            raise ValueError(f"BuiltinDoc.name must be non-empty without whitespace: {self.name!r}")
        has_break = "".join(self.summary.splitlines()) != self.summary
        if len(self.summary) > MAX_SUMMARY or has_break:
            raise ValueError(f"BuiltinDoc.summary must be one line of <= {MAX_SUMMARY} chars")


def extract_builtins(
    parsed: ParsedMan, heading: str = "SHELL BUILTIN COMMANDS"
) -> list[BuiltinDoc]:
    """Extract the builtins documented in the sections titled `heading` (D-043).

    Every section whose heading equals `heading` exactly is read as a definition list. Items
    without a description (an introductory paragraph, stray prose) are skipped. Each distinct
    first token among an item's terms becomes one builtin; the first item that documents a
    name wins. Never raises.

    Pre: `parsed` comes from `parse_man`.
    Post: unique names, sorted in plain `str` order; empty when no section matches.

    Args:
        parsed: A parsed zshbuiltins(1) or bash(1) page.
        heading: The section heading to read.

    Returns:
        The builtin docs sorted by name.
    """
    found: dict[str, BuiltinDoc] = {}
    for section in parsed.sections:
        if section.heading != heading:
            continue
        for item in definition_items(section.body):
            for doc in _docs(item):
                found.setdefault(doc.name, doc)
    return [found[name] for name in sorted(found)]


def _docs(item: DefinitionItem) -> list[BuiltinDoc]:
    """Return one doc per distinct first token of `item`'s terms; none without a description."""
    if not item.description.strip():
        return []
    summary = _summary(item.description)
    names = dict.fromkeys(term.split()[0] for term in item.terms)
    return [
        BuiltinDoc(
            name=name,
            synopsis="\n".join(term for term in item.terms if term.split()[0] == name),
            summary=summary,
            body=item.description,
        )
        for name in names
    ]


def _summary(description: str) -> str:
    """Return the first sentence of `description` on one line, cut to 200 characters.

    A sentence ends at ``.``, ``!`` or ``?`` followed by whitespace or the end, so an
    abbreviation such as ``e.g.`` ends it early; without an end the whole text is used.
    """
    flat = " ".join(description.split())
    match = _SENTENCE.match(flat)
    return (match.group(1) if match else flat)[:MAX_SUMMARY].rstrip()
