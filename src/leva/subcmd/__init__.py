"""Extract subcommands from parsed man pages and help text, and merge them."""

from __future__ import annotations

from leva.subcmd._help_text import HelpTextExtractor
from leva.subcmd._hyphen import HyphenPageExtractor
from leva.subcmd._merge import merge_subcommands
from leva.subcmd._section_list import SectionListExtractor
from leva.subcmd._types import HELP_PROFILES, KnownPage, SubcommandExtractor

__all__ = [
    "HELP_PROFILES",
    "HelpTextExtractor",
    "HyphenPageExtractor",
    "KnownPage",
    "SectionListExtractor",
    "SubcommandExtractor",
    "merge_subcommands",
]
