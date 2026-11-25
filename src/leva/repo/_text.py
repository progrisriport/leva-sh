"""Tell whether user text can be bound to a SQLite statement."""

from __future__ import annotations


def is_encodable(text: str) -> bool:
    """Return whether `text` encodes to UTF-8, which SQLite needs to bind it.

    A lone surrogate does not; the writer rejects such text, so no stored value can equal it and
    a lookup by it matches nothing.
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True
