"""The entry-name rule shared by the sources that produce command names."""

from __future__ import annotations


def is_entry_name(name: str) -> bool:
    """Tell whether `name` can become an `Entry.name` (D-033).

    Post: true exactly when `name` is non-empty and holds no `str.isspace()` character.
    """
    return name != "" and not any(char.isspace() for char in name)
