"""Locate the numbered SQL migration files of the index schema and order them."""

from __future__ import annotations

import re
from collections.abc import Mapping
from importlib.resources import files
from typing import Final

SCHEMA_VERSION: Final[int] = 1
"""Number of the last migration file; stored in ``PRAGMA user_version``."""

_MIGRATION_NAME: Final = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")


def order_migrations(scripts: Mapping[str, str]) -> tuple[str, ...]:
    """Order migration scripts by their number.

    Args:
        scripts: Script text by file name; names read ``NNNN_<slug>.sql``.

    Returns:
        The scripts in ascending number order.

    Raises:
        ValueError: If a name does not match the pattern or the numbers are not 1..n.
    """
    numbered: list[tuple[int, str]] = []
    for name in scripts:
        match = _MIGRATION_NAME.fullmatch(name)
        if match is None:
            raise ValueError(f"bad migration file name: {name!r}")
        numbered.append((int(match.group(1)), name))
    numbered.sort()
    if not numbered or [number for number, _ in numbered] != list(range(1, len(numbered) + 1)):
        raise ValueError(f"migration numbers must be 1..n without gaps: {sorted(scripts)}")
    return tuple(scripts[name] for _, name in numbered)


def load_migrations() -> tuple[str, ...]:
    """Read the bundled migration scripts, in order.

    Raises:
        ValueError: If the bundled file names are not a contiguous numbered series.
    """
    folder = files("leva.store").joinpath("migrations")
    scripts = {
        item.name: item.read_text(encoding="utf-8")
        for item in folder.iterdir()
        if item.name.endswith(".sql")
    }
    return order_migrations(scripts)
