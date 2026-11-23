"""Strip nroff overstrike (backspace) sequences from rendered man text."""

from __future__ import annotations

import re
from typing import Final

_OVERSTRIKE: Final = re.compile(r"[^\n]\x08")


def strip_overstrike(text: str) -> str:
    r"""Remove bold (``X\bX``) and underline (``_\bX``) overstrike from `text`.

    Every character immediately followed by a backspace is removed together with that
    backspace, left to right and without overlap; a backspace left over (at the start of
    the text or of a line) is removed too.

    Post: the result contains no backspace; text without a backspace is unchanged.
    """
    return _OVERSTRIKE.sub("", text).replace("\x08", "")
