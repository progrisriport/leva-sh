"""Open cards, search and keep the navigation history: the only read API the TUI uses."""

from __future__ import annotations

from leva.library._card import Card, merge_examples, subcommand_examples
from leva.library._history import History
from leva.model import Entry, Section, Subcommand
from leva.repo import Repository
from leva.search import Searcher, SearchResult


class Library:
    """Read API over an index for the UI.

    History lives in the instance: `open`, `open_result` and `open_subcommand` record the card
    they return, `card` never does. Every method raises only ``IndexUnavailableError`` for a
    database problem (hint ``run leva --rebuild``).
    """

    def __init__(self, repo: Repository, searcher: Searcher) -> None:
        self._repo = repo
        self._searcher = searcher
        self._history = History()

    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        """Rank results for `query`; see ``Searcher.search`` (``ValueError`` for ``limit < 1``)."""
        return self._searcher.search(query, limit)

    def nearest_names(self, query: str, limit: int = 3) -> list[str]:
        """Return the closest command names to `query` (D-031), for "did you mean"."""
        return self._searcher.nearest_names(query, limit)

    def card(self, entry_id: int) -> Card | None:
        """Build the card of an entry without recording it (a live preview); ``None`` if unknown."""
        entry = self._repo.get_entry_by_id(entry_id)
        return None if entry is None else self._entry_card(entry, (entry.name,))

    def open(self, name: str) -> Card | None:
        """Open a command by name or alias, or ``"git commit"``; record and return the card.

        Lookup is exact and case-sensitive. Several words try the hyphen entry ``git-commit``
        first, then the subcommand ``commit`` of ``git``. ``None`` leaves the history unchanged.
        """
        tokens = name.split()
        if not tokens:
            return None
        card = self._open_name(tokens[0]) if len(tokens) == 1 else self._open_words(tokens)
        return self._record(card)

    def open_result(self, entry_id: int) -> Card | None:
        """Open a search result: reset the history, then record the card (D-028).

        An unknown id returns ``None`` and keeps the history.
        """
        card = self.card(entry_id)
        if card is not None:
            self._history.clear()
        return self._record(card)

    def open_subcommand(self, card: Card, sub: str) -> Card | None:
        """Open the subcommand `sub` of `card` (exact name); record and return its card."""
        return self._record(self._resolve_subcommand(card, sub))

    def back(self) -> Card | None:
        """Go one card back; ``None`` at the oldest card."""
        return self._history.back()

    def forward(self) -> Card | None:
        """Go one card forward; ``None`` at the newest card."""
        return self._history.forward()

    def trail(self) -> tuple[Card, ...]:
        """Return the cards from the oldest up to and including the current one."""
        return self._history.trail()

    def attribution(self) -> str:
        """Return the attribution text of the index, ``""`` when it has none."""
        return self._repo.meta().get("attribution", "")

    def close(self) -> None:
        """Close the index; calling it again does nothing."""
        self._repo.close()

    def _record(self, card: Card | None) -> Card | None:
        if card is not None:
            self._history.push(card)
        return card

    def _open_name(self, token: str) -> Card | None:
        entry = self._repo.get_entry(token)
        return None if entry is None else self._entry_card(entry, (entry.name,))

    def _open_words(self, tokens: list[str]) -> Card | None:
        sub = "-".join(tokens[1:])
        page = self._repo.get_entry("-".join(tokens))
        if page is not None:
            return self._entry_card(page, (tokens[0], sub))
        parent = self._open_name(tokens[0])
        return None if parent is None else self._resolve_subcommand(parent, sub)

    def _resolve_subcommand(self, card: Card, sub: str) -> Card | None:
        found = next((item for item in card.subcommands if item.name == sub), None)
        if found is None:
            return None
        breadcrumb = (card.entry.name, found.name)
        page = None if found.entry_name is None else self._repo.get_entry(found.entry_name)
        if page is not None:
            return self._entry_card(page, breadcrumb)
        return _synthesized_card(card, found, breadcrumb)

    def _entry_card(self, entry: Entry, breadcrumb: tuple[str, ...]) -> Card:
        entry_id = entry.id
        return Card(
            entry=entry,
            explain=self._repo.explain(entry_id),
            notes=tuple(self._repo.notes(entry_id)),
            examples=merge_examples(self._repo.examples(entry_id)),
            subcommands=tuple(self._repo.subcommands(entry_id)),
            related=tuple(self._repo.related(entry_id)),
            sections=tuple(self._repo.sections(entry_id)),
            breadcrumb=breadcrumb,
            summary=entry.summary,
        )


def _synthesized_card(parent: Card, sub: Subcommand, breadcrumb: tuple[str, ...]) -> Card:
    """Build the card of a subcommand that has no page of its own (D-011)."""
    sections = (Section("DESCRIPTION", sub.body, 0),) if sub.body.strip() else ()
    return Card(
        entry=parent.entry,
        explain="",
        notes=(),
        examples=subcommand_examples(parent.examples, parent.entry.name, sub.name),
        subcommands=(),
        related=(),
        sections=sections,
        breadcrumb=breadcrumb,
        summary=sub.summary,
    )
