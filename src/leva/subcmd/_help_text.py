"""Find subcommands in the text of an allowlisted help probe, by output profile."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Final

from leva.manparse import ParsedMan, first_sentence
from leva.model import Subcommand
from leva.subcmd._types import (
    HELP_PROFILES,
    SOURCE_PROBE,
    KnownPage,
    is_term_name,
    sorted_unique,
)

_TWO_COL_ROW: Final = re.compile(r"(\S.*?) {2,}(\S.*)")
_GIT_ROW: Final = re.compile(r"(\S+)(?: {2,}(\S.*))?")
_PARENTHESISED: Final = re.compile(r"\((.*)\)")
_ALIASES_HEADING: Final = "command aliases"


class HelpTextExtractor:
    """Parse the text of a help probe with one of the `HELP_PROFILES`."""

    def __init__(self, profile: str, text: str) -> None:
        """Select the parser for `profile` and keep the probe `text`.

        Args:
            profile: One of `HELP_PROFILES`.
            text: The probe output; any string.

        Raises:
            ValueError: If `profile` is not one of `HELP_PROFILES`.
        """
        if profile not in HELP_PROFILES:
            raise ValueError(f"unknown help profile: {profile!r}")
        self._parse = _PARSERS[profile]
        self._text = text

    def extract(
        self,
        parent: str,  # noqa: ARG002 - part of the SubcommandExtractor signature
        parsed: ParsedMan | None,  # noqa: ARG002 - part of the SubcommandExtractor signature
        known: Mapping[str, KnownPage],  # noqa: ARG002 - part of the SubcommandExtractor signature
    ) -> list[Subcommand]:
        """Return the subcommands named in the probe text; all arguments are ignored.

        Each line is tab-expanded and right-stripped; blank lines are ignored. The profile
        decides which lines name a subcommand (D-044). Never raises.

        Post: unique names, sorted; the first occurrence of a name wins; `source` is
        ``probe``, `entry_name` is None and `body` is empty.

        Args:
            parent: Ignored.
            parsed: Ignored.
            known: Ignored.

        Returns:
            The subcommands sorted by name.
        """
        lines = (line.expandtabs(8).rstrip() for line in self._text.splitlines())
        return sorted_unique(self._parse([line for line in lines if line]))


def _probe(name: str, summary: str) -> Subcommand:
    """Return the probe subcommand `name` with the first sentence of `summary`."""
    return Subcommand(name, first_sentence(summary), None, SOURCE_PROBE)


def _parse_two_col(lines: list[str]) -> list[Subcommand]:
    """Read indented ``name [args]  (summary)`` rows; column-0 lines are banners."""
    found: list[Subcommand] = []
    for line in lines:
        match = _TWO_COL_ROW.fullmatch(line.strip()) if line.startswith(" ") else None
        if match is None or not is_term_name(token := match.group(1).split()[0]):
            continue
        enclosed = _PARENTHESISED.fullmatch(match.group(2))
        found.append(_probe(token, enclosed.group(1) if enclosed else match.group(2)))
    return found


def _parse_git_list(lines: list[str]) -> list[Subcommand]:
    """Read indented rows under column-0 headings, except under ``Command aliases``."""
    found: list[Subcommand] = []
    in_aliases = False
    for line in lines:
        if not line.startswith(" "):
            in_aliases = line.strip().casefold() == _ALIASES_HEADING
            continue
        match = None if in_aliases else _GIT_ROW.fullmatch(line.strip())
        if match is not None and is_term_name(match.group(1)):
            found.append(_probe(match.group(1), match.group(2) or ""))
    return found


def _parse_brew_commands(lines: list[str]) -> list[Subcommand]:
    """Read bare command names; ``==>`` headings, options and prose fail the name rule."""
    names = (line.strip() for line in lines)
    return [_probe(name, "") for name in names if is_term_name(name)]


_PARSERS: Final[Mapping[str, Callable[[list[str]], list[Subcommand]]]] = {
    "two-col": _parse_two_col,
    "git-list": _parse_git_list,
    "brew-commands": _parse_brew_commands,
}
