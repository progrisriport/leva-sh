"""Render man pages and parse them into sections, NAME, definition lists and builtins."""

from __future__ import annotations

from leva.manparse._overstrike import strip_overstrike
from leva.manparse._render import MandocRenderer, ManRenderer
from leva.manparse._stub import read_man_source, stub_target

__all__ = [
    "ManRenderer",
    "MandocRenderer",
    "read_man_source",
    "strip_overstrike",
    "stub_target",
]
