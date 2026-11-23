"""Shared types, constants and helpers of the subcommand extractors."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Protocol

from leva.manparse import ParsedMan
from leva.model import Subcommand

HELP_PROFILES: Final[tuple[str, ...]] = ("two-col", "git-list", "brew-commands")

SOURCE_HYPHEN: Final = "hyphen"
SOURCE_SECTION: Final = "section"
SOURCE_PROBE: Final = "probe"

_TERM_NAME: Final = re.compile(r"[a-z][A-Za-z0-9_.-]*")


@dataclass(frozen=True, slots=True)
class KnownPage:
    """A man page that may be a hyphen subcommand page.

    No invariants: ingest builds it from valid entries.

    Attributes:
        name: Entry name, e.g. ``git-commit``.
        summary: Its NAME summary; empty when it has none.
        synopsis: The rendered SYNOPSIS section body; empty when the page has none.
    """

    name: str
    summary: str
    synopsis: str


class SubcommandExtractor(Protocol):
    """A source of the subcommands of one command."""

    def extract(
        self, parent: str, parsed: ParsedMan | None, known: Mapping[str, KnownPage]
    ) -> list[Subcommand]:
        """Return the subcommands of `parent` found by this extractor.

        Post: unique names, sorted in plain `str` order.

        Args:
            parent: Name of the command.
            parsed: Its parsed man page, if it has one.
            known: Every man page known to ingest, by entry name.

        Returns:
            The subcommands sorted by name.
        """
        ...


def is_term_name(token: str) -> bool:
    """Tell whether `token` can name a subcommand (D-008, amended by D-044).

    A lowercase ASCII letter followed by ASCII letters of any case, digits, ``_``, ``.`` or
    ``-``; camelCase verbs such as ``eraseDisk`` pass, ``APFS``, ``-k`` and
    ``system/[service]`` do not.
    """
    return _TERM_NAME.fullmatch(token) is not None


def sorted_unique(subs: Iterable[Subcommand]) -> list[Subcommand]:
    """Return `subs` without repeated names (the first occurrence wins), sorted by name."""
    first: dict[str, Subcommand] = {}
    for sub in subs:
        first.setdefault(sub.name, sub)
    return [first[name] for name in sorted(first)]
