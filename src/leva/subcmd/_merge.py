"""Merge the subcommands of several sources by name, field by field."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from leva.model import Subcommand


def merge_subcommands(by_priority: Sequence[Sequence[Subcommand]]) -> list[Subcommand]:
    """Merge subcommand lists into one, the earliest list having the highest priority.

    The result holds the union of the names. For one name the contributors are its
    occurrences in priority order (document order inside one list). `summary` and `body`
    come from the first contributor whose text is not blank, `entry_name` from the first that
    has one, and `source` from the first contributor.

    Post: unique names, sorted in plain `str` order; empty when no list has an item.

    Args:
        by_priority: Lists in priority order, e.g. curated, probe, section, hyphen.

    Returns:
        The merged subcommands sorted by name.
    """
    contributors: dict[str, list[Subcommand]] = {}
    for subs in by_priority:
        for sub in subs:
            contributors.setdefault(sub.name, []).append(sub)
    return [_merge_one(contributors[name]) for name in sorted(contributors)]


def _merge_one(subs: list[Subcommand]) -> Subcommand:
    """Merge the occurrences of one name, given in priority order."""
    return Subcommand(
        name=subs[0].name,
        summary=_first_text(sub.summary for sub in subs),
        entry_name=next((sub.entry_name for sub in subs if sub.entry_name is not None), None),
        source=subs[0].source,
        body=_first_text(sub.body for sub in subs),
    )


def _first_text(texts: Iterable[str]) -> str:
    """Return the first text that is not blank, or the empty string."""
    return next((text for text in texts if text.strip()), "")
