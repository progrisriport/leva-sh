"""Find subcommands among the hyphen man pages (``git-commit`` for ``git``)."""

from __future__ import annotations

from collections.abc import Mapping

from leva.manparse import ParsedMan
from leva.model import Subcommand
from leva.subcmd._types import SOURCE_HYPHEN, KnownPage, sorted_unique


class HyphenPageExtractor:
    """Take the pages named ``<parent>-<sub>`` whose SYNOPSIS starts with ``<parent> <sub>``."""

    def extract(
        self,
        parent: str,
        parsed: ParsedMan | None,  # noqa: ARG002 - part of the SubcommandExtractor signature
        known: Mapping[str, KnownPage],
    ) -> list[Subcommand]:
        """Return the hyphen subcommands of `parent`; `parsed` is ignored.

        The SYNOPSIS must start with the tokens `parent` and the part of the page name after
        ``<parent>-``, so ``ssh-keygen`` is not a subcommand of ``ssh`` and ``git commitx``
        does not match ``git-commit``.

        Pre: `known` maps entry names to their pages.
        Post: unique names, sorted; `entry_name` is the page name, `body` is empty.

        Args:
            parent: Name of the command.
            parsed: Ignored; may be None.
            known: Every man page known to ingest, by entry name.

        Returns:
            The subcommands sorted by name.
        """
        prefix = parent + "-"
        found: list[Subcommand] = []
        for key, page in known.items():
            if not key.startswith(prefix):
                continue
            sub = key[len(prefix) :]
            if page.synopsis.split(None, 2)[:2] == [parent, sub]:
                found.append(Subcommand(sub, page.summary, key, SOURCE_HYPHEN))
        return sorted_unique(found)
