"""The `Card` shown for a command and the pure helpers that order and filter its examples."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from leva.model import Entry, Example, Note, Section, Subcommand
from leva.placeholders import parse, to_plain


@dataclass(frozen=True, slots=True)
class Card:
    """Everything a card screen shows for one command or one subcommand.

    Attributes:
        entry: The entry; for a synthesized subcommand card, the parent entry.
        explain: Curated explanation, ``""`` when absent.
        notes: Notes in index order.
        examples: Curated examples first, then tldr, duplicates merged.
        subcommands: Subcommands in index order.
        related: Names of related commands in index order.
        sections: Man page sections in page order.
        breadcrumb: Path of the card, such as ``("git", "commit")``.
        summary: Lead line: the entry summary, or the subcommand summary when synthesized.

    Raises:
        ValueError: If ``breadcrumb`` is empty or holds a blank item.
    """

    entry: Entry
    explain: str
    notes: tuple[Note, ...]
    examples: tuple[Example, ...]
    subcommands: tuple[Subcommand, ...]
    related: tuple[str, ...]
    sections: tuple[Section, ...]
    breadcrumb: tuple[str, ...]
    summary: str

    def __post_init__(self) -> None:
        if not self.breadcrumb or any(not item.strip() for item in self.breadcrumb):
            raise ValueError(f"Card.breadcrumb must hold non-blank items: {self.breadcrumb!r}")


def example_key(cmd: str) -> str:
    """Return the duplicate key of a command: every placeholder as ``{}``, whitespace collapsed."""
    text = "".join("{}" if segment.is_placeholder else segment.text for segment in parse(cmd))
    return " ".join(text.split())


def merge_examples(examples: Iterable[Example]) -> tuple[Example, ...]:
    """Order examples curated first, then tldr, dropping those whose `example_key` was seen.

    The order inside each source is kept, so the curated example wins over a tldr duplicate and
    the first of a repeated key within one source wins.
    """
    items = list(examples)
    ordered = [item for item in items if item.source == "curated"]
    ordered += [item for item in items if item.source != "curated"]
    seen: set[str] = set()
    merged: list[Example] = []
    for item in ordered:
        key = example_key(item.cmd)
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return tuple(merged)


def subcommand_examples(examples: Iterable[Example], parent: str, sub: str) -> tuple[Example, ...]:
    """Keep the examples whose plain command is ``parent sub`` or starts with it as whole words."""
    prefix = f"{parent} {sub}"
    kept: list[Example] = []
    for item in examples:
        plain = " ".join(to_plain(item.cmd).split())
        if plain == prefix or plain.startswith(prefix + " "):
            kept.append(item)
    return tuple(kept)
