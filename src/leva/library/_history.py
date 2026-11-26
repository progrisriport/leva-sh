"""Browser-style navigation history of cards."""

from __future__ import annotations

from typing import Final

from leva.library._card import Card

HISTORY_LIMIT: Final = 50


class History:
    """A list of cards with a cursor; opening after going back drops the forward part."""

    def __init__(self) -> None:
        self._cards: list[Card] = []
        self._cursor = -1

    def push(self, card: Card) -> None:
        """Append `card` after the cursor and make it current; keep the newest `HISTORY_LIMIT`."""
        del self._cards[self._cursor + 1 :]
        self._cards.append(card)
        del self._cards[: max(0, len(self._cards) - HISTORY_LIMIT)]
        self._cursor = len(self._cards) - 1

    def back(self) -> Card | None:
        """Move one card left and return it; ``None`` (and no move) at the oldest or when empty."""
        if self._cursor <= 0:
            return None
        self._cursor -= 1
        return self._cards[self._cursor]

    def forward(self) -> Card | None:
        """Move one card right and return it; ``None`` (and no move) at the newest."""
        if self._cursor + 1 >= len(self._cards):
            return None
        self._cursor += 1
        return self._cards[self._cursor]

    def clear(self) -> None:
        """Forget every card."""
        self._cards.clear()
        self._cursor = -1

    def trail(self) -> tuple[Card, ...]:
        """Return the cards from the oldest up to and including the current one."""
        return tuple(self._cards[: self._cursor + 1])
