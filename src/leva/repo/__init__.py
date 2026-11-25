"""Typed read-only queries over the index."""

from __future__ import annotations

from leva.repo._fts import MAX_FTS_TOKENS
from leva.repo._repository import Repository
from leva.repo._rows import FTS_WEIGHTS, FtsHit, IndexStats, NameRow

__all__ = [
    "FTS_WEIGHTS",
    "MAX_FTS_TOKENS",
    "FtsHit",
    "IndexStats",
    "NameRow",
    "Repository",
]
