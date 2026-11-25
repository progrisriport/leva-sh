"""Turn free user text into a safe FTS5 query: every token quoted, nothing else."""

from __future__ import annotations

from typing import Final

from leva.repo._text import is_encodable

MAX_FTS_TOKENS: Final = 32


def fts_query(text: str) -> str | None:
    """Build an FTS5 ``MATCH`` expression from user text.

    The text is split on whitespace (a NUL character counts as whitespace: SQLite rejects it in a
    bound string) and the first ``MAX_FTS_TOKENS`` tokens are kept. Each token
    becomes an FTS5 string (double quotes, embedded ``"`` doubled) and the strings are joined by a
    space (implicit AND), so no operator, prefix ``*``, column filter or ``NEAR`` can be spelled.

    Args:
        text: Raw query as typed by the user.

    Returns:
        The expression, or ``None`` when the text holds no token or cannot be encoded to UTF-8
        (a lone surrogate: nothing in the index can match it, and SQLite could not bind it).
    """
    if not is_encodable(text):
        return None
    tokens = text.replace("\x00", " ").split()[:MAX_FTS_TOKENS]
    if not tokens:
        return None
    return " ".join('"' + token.replace('"', '""') + '"' for token in tokens)
