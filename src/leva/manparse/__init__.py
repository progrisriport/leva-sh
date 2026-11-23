"""Render man pages and parse them into sections, NAME, definition lists and builtins."""

from __future__ import annotations

from leva.manparse._builtins import BuiltinDoc, extract_builtins
from leva.manparse._definitions import DefinitionItem, definition_items
from leva.manparse._overstrike import strip_overstrike
from leva.manparse._render import MandocRenderer, ManRenderer
from leva.manparse._sections import ParsedMan, parse_man
from leva.manparse._stub import read_man_source, stub_target

__all__ = [
    "BuiltinDoc",
    "DefinitionItem",
    "ManRenderer",
    "MandocRenderer",
    "ParsedMan",
    "definition_items",
    "extract_builtins",
    "parse_man",
    "read_man_source",
    "strip_overstrike",
    "stub_target",
]
