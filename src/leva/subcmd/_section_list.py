"""Find subcommands in the COMMANDS, SUBCOMMANDS and VERBS sections of a parsed man page."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from leva.manparse import DefinitionItem, ParsedMan, definition_items, first_sentence
from leva.model import Subcommand
from leva.subcmd._types import SOURCE_SECTION, KnownPage, is_term_name, sorted_unique

_HEADING: Final = re.compile(r"(?:SUB)?COMMANDS|VERBS")
_SENTENCE_END: Final = re.compile(r"[A-Za-z0-9)\]][.!?](?:\s|$)")


class SectionListExtractor:
    """Read the definition lists of the sections whose heading is a subcommand list."""

    def extract(
        self,
        parent: str,
        parsed: ParsedMan | None,
        known: Mapping[str, KnownPage],  # noqa: ARG002 - part of the SubcommandExtractor signature
    ) -> list[Subcommand]:
        """Return the subcommands listed in `parsed`; `known` is ignored.

        Every section whose whole heading is ``COMMANDS``, ``SUBCOMMANDS`` or ``VERBS`` is
        scanned, repeated headings included. An item without a description is skipped. Each
        term's first token that satisfies the name rule becomes a subcommand whose `body` is
        the item's description and whose `entry_name` is None. A term is skipped when its first
        token is `parent` (a command is not its own subcommand) or when it reads as prose, that
        is it contains a sentence end: a letter, digit, ``)`` or ``]`` followed by ``.``, ``!``
        or ``?`` and then whitespace or the end of the term. Never raises.

        Post: unique names, sorted; the first item that documents a name wins.

        Args:
            parent: Name of the command whose page is parsed.
            parsed: The parsed man page of the command; None gives no subcommands.
            known: Ignored.

        Returns:
            The subcommands sorted by name.
        """
        if parsed is None:
            return []
        found: list[Subcommand] = []
        for section in parsed.sections:
            if _HEADING.fullmatch(section.heading):
                for item in definition_items(section.body):
                    found.extend(_subcommands(item, parent))
        return sorted_unique(found)


def _subcommands(item: DefinitionItem, parent: str) -> list[Subcommand]:
    """Return one subcommand per distinct valid first token of `item`'s non-prose terms."""
    if not item.description.strip():
        return []
    summary = first_sentence(item.description)
    terms = [term for term in item.terms if not _SENTENCE_END.search(term)]
    tokens = dict.fromkeys(term.split()[0] for term in terms)
    tokens.pop(parent, None)
    return [
        Subcommand(token, summary, None, SOURCE_SECTION, item.description)
        for token in tokens
        if is_term_name(token)
    ]
