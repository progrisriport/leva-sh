"""Find subcommands in the COMMANDS, SUBCOMMANDS and VERBS sections of a parsed man page."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from leva.manparse import DefinitionItem, ParsedMan, definition_items, first_sentence
from leva.model import Subcommand
from leva.subcmd._types import SOURCE_SECTION, KnownPage, is_term_name, sorted_unique

_HEADING: Final = re.compile(r"(?:SUB)?COMMANDS|VERBS")


class SectionListExtractor:
    """Read the definition lists of the sections whose heading is a subcommand list."""

    def extract(
        self,
        parent: str,  # noqa: ARG002 - part of the SubcommandExtractor signature
        parsed: ParsedMan | None,
        known: Mapping[str, KnownPage],  # noqa: ARG002 - part of the SubcommandExtractor signature
    ) -> list[Subcommand]:
        """Return the subcommands listed in `parsed`; `parent` and `known` are ignored.

        Every section whose whole heading is ``COMMANDS``, ``SUBCOMMANDS`` or ``VERBS`` is
        scanned, repeated headings included. An item without a description is skipped. Each
        term's first token that satisfies the name rule becomes a subcommand whose `body` is
        the item's description and whose `entry_name` is None. Never raises.

        Post: unique names, sorted; the first item that documents a name wins.

        Args:
            parent: Ignored.
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
                    found.extend(_subcommands(item))
        return sorted_unique(found)


def _subcommands(item: DefinitionItem) -> list[Subcommand]:
    """Return one subcommand per distinct valid first token of `item`'s terms."""
    if not item.description.strip():
        return []
    summary = first_sentence(item.description)
    tokens = dict.fromkeys(term.split()[0] for term in item.terms)
    return [
        Subcommand(token, summary, None, SOURCE_SECTION, item.description)
        for token in tokens
        if is_term_name(token)
    ]
